#!/usr/bin/env python3
"""
Test script for rugo parquet features:
1. Logical type extraction
"""

import glob
import sys
from pathlib import Path
import pyarrow.parquet as pq
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import rugo.parquet as parquet_meta

# these are specific to the test files only
EQUIVALENT_TYPES = {
    "array<varchar>": ["list<item: string>", "list<element: string>"],
    "binary": ["binary"],
    "boolean": ["bool"],
    "date32[day]": ["date32[day]"],
    "decimal(7,3)": ["decimal128(7, 3)"],
    "decimal(10,2)": ["decimal128(10, 2)"],
    "fixed_len_byte_array[5]": ["fixed_size_binary[5]"],
    "float16": ["halffloat"],
    "float32": ["float"],
    "float64": ["double"],
    "int16": ["int16"],
    "int32": ["int32"],
    "int64": ["int64"],
    "int96": ["timestamp[ns]"],  # Parquet INT96 is often used for timestamps
    "timestamp[ms,UTC]": ["timestamp[us]"],
    "timestamp[ns]": ["timestamp[ns]"],
    "uint16": ["uint16"],
    "varchar": ["string"],
}


def test_logical_types():
    """Test logical type extraction"""
    print("=== Testing Logical Types ===")
    
    files_to_test = glob.glob("tests/data/*.parquet")
    
    for file_path in files_to_test:
            
        print(f"\nFile: {file_path}")

        meta = parquet_meta.read_metadata(file_path)
        
        for rg_idx, rg in enumerate(meta['row_groups']):
            print(f"  Row Group {rg_idx}:")
            for col in rg['columns']:
                if "." not in col["name"]:
                    logical = col.get('logical_type', '')
                    print(f"    {col['name']:20} | physical={col['type']:12} | logical={logical or '(none)'}")
            break  # Only show first row group
            

def test_comparison_with_pyarrow():
    """Compare our logical types with PyArrow's interpretation"""
    print("\n=== Comparison with PyArrow ===")
    
    files_to_test = glob.glob("tests/data/*.parquet")
    
    for file_path in files_to_test:

        if not Path(file_path).exists():
            print(f"Skipping comparison - {file_path} not found")
            return
            
        print(f"File: {file_path}")
        
        # PyArrow interpretation
        pf = pq.ParquetFile(file_path)
        schema = pf.schema.to_arrow_schema()
        arrow_types = {field.name: str(field.type) for field in schema} 
        
        print(" PyArrow schema:", arrow_types)
        # Our interpretation
        meta = parquet_meta.read_metadata(file_path)
        print(f" Our interpretation: {[n['name'] for n in meta['row_groups'][0]['columns']]}")
        print("   schema:")
        for col in meta['row_groups'][0]['columns']:
            if "." not in col["name"]:
                logical = col.get('logical_type', '')
                print(f"    {col['name']:20} | physical={col['type']:17} | logical={logical or '(none)':<17}  | arrow={arrow_types.get(col['name'], '(missing)')}")
                assert arrow_types.get(col['name']) in EQUIVALENT_TYPES.get(logical, []), col['name']


if __name__ == "__main__":
    pytest.main([__file__])