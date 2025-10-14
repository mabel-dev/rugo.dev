#!/usr/bin/env python3
"""
Example script demonstrating rugo to orso schema conversion.

This script shows how to use rugo to read parquet metadata and convert
it to an orso RelationSchema for further processing.
"""

import glob
import sys
import time
from pathlib import Path

# Add current directory to path for running from repo
sys.path.insert(0, str(Path(__file__).parent.parent))

import rugo.parquet as parquet_meta

# Try to import orso converter (optional dependency)
try:
    from rugo.converters.orso import extract_schema_only
    from rugo.converters.orso import rugo_to_orso_schema
    ORSO_AVAILABLE = True
except ImportError:
    print("⚠️  orso package not available. Install with: pip install rugo[orso]")
    ORSO_AVAILABLE = False


def main():
    print("🚀 Rugo to Orso Schema Conversion Example\n")
    
    # Find a test parquet file
    files_to_test = glob.glob("tests/data/*.parquet")

    for test_file in files_to_test:

        test_file = Path(test_file)
        if not test_file.exists():
            print(f"❌ Test file not found: {test_file}")
            print("Please run this from the rugo repository root directory.")
            return 1
        
        print(f"📁 Reading metadata from: {test_file}")
        
        # Read parquet metadata with rugo
        start_time = time.time()
        metadata = parquet_meta.read_metadata(str(test_file))
        rugo_time = time.time() - start_time
        
        print(f"⚡ Rugo metadata extraction: {rugo_time*1000:.2f}ms")
        print(f"📊 Total rows: {metadata['num_rows']}")
        print(f"🗂️  Row groups: {len(metadata['row_groups'])}")
        print(f"📋 Columns: {len(metadata['row_groups'][0]['columns'])}")
        
        print("\n📝 Rugo Schema (first 5 columns):")
        for i, col in enumerate(metadata['row_groups'][0]['columns'][:5]):
            logical = col.get('logical_type', 'inferred')
            print(f"  {i+1}. {col['name']}: {col['physical_type']} -> {logical}")
        
        if not ORSO_AVAILABLE:
            print("\n⚠️  Orso conversion not available (orso package not installed)")
            return 0
        
        print("\n🔄 Converting to Orso schema...")
        
        # Convert to orso RelationSchema
        start_time = time.time()
        orso_schema = rugo_to_orso_schema(metadata, "planets_dataset")
        convert_time = time.time() - start_time
        
        print(f"⚡ Conversion time: {convert_time*1000:.2f}ms")
        
        print("\n🎯 Orso RelationSchema:")
        print(f"  Schema name: {orso_schema.name}")
        print(f"  Row count estimate: {orso_schema.row_count_estimate}")
        print(f"  Number of columns: {len(orso_schema.columns)}")
        
        print("\n📋 Orso Columns (first 5):")
        for i, col in enumerate(orso_schema.columns[:5]):
            nullable = "nullable" if col.nullable else "not null"
            print(f"  {i+1}. {col.name}: {col.type} ({nullable})")
        
        # Show simplified extraction
        print("\n🔍 Simplified schema extraction:")
        schema_info = extract_schema_only(metadata, "simple_schema")
        print(f"  Schema: {schema_info['schema_name']}")
        print(f"  Rows: {schema_info['row_count']}")
        print("  Column types:")
        for name, type_name in list(schema_info['columns'].items())[:5]:
            print(f"    {name}: {type_name}")
        
        print("\n✅ Conversion completed successfully!")
        
        # Performance comparison note
        print("\n📈 Performance Summary:")
        print(f"  • Rugo metadata extraction: {rugo_time*1000:.2f}ms")
        print(f"  • Schema conversion: {convert_time*1000:.2f}ms")
        print(f"  • Total time: {(rugo_time + convert_time)*1000:.2f}ms")
        print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
