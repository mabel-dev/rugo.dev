#!/usr/bin/env python3
"""
Example demonstrating the new memory-based ReadParquet API.

This shows how to:
1. Load parquet data into memory once
2. Use the new read_parquet() function to decode all columns at once
3. Work with the table structure organized by row groups and columns
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from typing import Optional
import rugo.parquet as rp

def demonstrate_new_read_parquet_api(file_path: str, column_names: Optional[list] = None):
    """Demonstrate the new memory-based read_parquet API."""
    
    print("=== NEW API: read_parquet() ===")
    print(f"Reading {file_path} with columns: {column_names}")
    
    # Step 1: Load the entire file into memory once
    try:
        with open(file_path, 'rb') as f:
            parquet_data = f.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return None
    
    print(f"Loaded {len(parquet_data)} bytes into memory")
    
    # Step 2: Check if we can decode this data
    if not rp.can_decode_from_memory(parquet_data):
        print("This parquet file cannot be decoded with our limited decoder")
        print("(Requires uncompressed, PLAIN-encoded int32/int64/string columns)")
        return None
    
    print("File can be decoded!")
    
    # Step 3: Use the new primary API to read the entire table
    table = rp.read_parquet(parquet_data, column_names)
    
    if table is None:
        print("Failed to read parquet data")
        return None
    
    print("Successfully read table:")
    print(f"  Columns: {table['column_names']}")
    print(f"  Row groups: {len(table['row_groups'])}")
    
    # Step 4: Display the structure and some data
    total_rows = 0
    for rg_idx, row_group in enumerate(table['row_groups']):
        print(f"\n  Row Group {rg_idx}:")
        
        if not row_group:
            print("    No data")
            continue
            
        # Calculate rows from first non-None column
        rg_rows = 0
        for col_idx, column_data in enumerate(row_group):
            if column_data is not None:
                rg_rows = len(column_data)
                break
        
        print(f"    Rows: {rg_rows}")
        total_rows += rg_rows
        
        # Show sample data for each column
        for col_idx, column_data in enumerate(row_group):
            col_name = table['column_names'][col_idx]
            if column_data is None:
                print(f"    Column '{col_name}': Failed to decode")
            else:
                sample = column_data[:3] if len(column_data) > 3 else column_data
                print(f"    Column '{col_name}': {len(column_data)} values, sample: {sample}")
    
    print(f"\nTotal rows across all row groups: {total_rows}")
    return table

if __name__ == "__main__":
    print("Example usage of the new memory-based ReadParquet API")
    print("\nTo test with a real parquet file, call:")
    print("  read_parquet_data('path/to/file.parquet', ['col1', 'col2'])")
    print()

    # Example call with test data
    demonstrate_new_read_parquet_api('tests/data/rugo_compatible.parquet')
    