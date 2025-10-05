#!/usr/bin/env python3
"""
Example demonstrating the comprehensive metadata now exposed by rugo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import rugo.parquet as parquet_meta


def main():
    print("=" * 70)
    print("Rugo - Comprehensive Parquet Metadata Example")
    print("=" * 70)
    
    # Read metadata
    metadata = parquet_meta.read_metadata('tests/data/planets.parquet')
    
    print("\n📊 File Statistics:")
    print(f"   Total rows: {metadata['num_rows']}")
    print(f"   Row groups: {len(metadata['row_groups'])}")
    
    # Show first row group
    rg = metadata['row_groups'][0]
    print("\n🔢 Row Group 0:")
    print(f"   Rows: {rg['num_rows']}")
    print(f"   Total bytes: {rg['total_byte_size']:,}")
    print(f"   Columns: {len(rg['columns'])}")
    
    # Show detailed metadata for first few columns
    print("\n📋 Column Details (first 3 columns):")
    print(f"{'-' * 70}")
    
    for i, col in enumerate(rg['columns'][:3], 1):
        print(f"\n{i}. {col['name']} ({col['type']} → {col['logical_type']})")
        print(f"   Values: {col.get('num_values', '?')}")
        print(f"   Null count: {col['null_count']}")
        
        if col.get('distinct_count') is not None:
            print(f"   Distinct values: {col['distinct_count']}")
        
        print(f"   Size: {col['total_compressed_size']:,} bytes (compressed)")
        print(f"         {col['total_uncompressed_size']:,} bytes (uncompressed)")
        
        compression_ratio = col['total_uncompressed_size'] / col['total_compressed_size']
        print(f"         {compression_ratio:.2f}x compression ratio")
        
        print(f"   Encodings: {', '.join(col['encodings'])}")
        print(f"   Codec: {col['compression_codec']}")
        
        print("   Offsets:")
        if col['dictionary_page_offset'] is not None:
            print(f"      Dictionary: {col['dictionary_page_offset']}")
        print(f"      Data: {col['data_page_offset']}")
        if col['index_page_offset'] is not None:
            print(f"      Index: {col['index_page_offset']}")
        
        if col['bloom_offset'] is not None:
            print(f"   Bloom filter: offset={col['bloom_offset']}, length={col['bloom_length']}")
        
        if col['min'] is not None and col['max'] is not None:
            print(f"   Range: [{col['min']}, {col['max']}]")
        
        if col['key_value_metadata']:
            print(f"   Custom metadata: {col['key_value_metadata']}")
    
    print(f"\n{'-' * 70}")
    
    # Summary of all fields now exposed
    print("\n✨ All Exposed Metadata Fields:")
    all_fields = list(rg['columns'][0].keys())
    all_fields.sort()
    for field in all_fields:
        print(f"   • {field}")
    
    print(f"\n✅ Total: {len(all_fields)} fields per column (up from 8 previously)")
    print()


if __name__ == "__main__":
    main()
