#!/usr/bin/env python3
"""
Example demonstrating Parquet data decoding with rugo.

This is a prototype decoder that supports:
- Uncompressed columns only
- PLAIN encoding only
- int32, int64, and string (byte_array) types only
"""
import sys
from pathlib import Path

import rugo.parquet as parquet_meta

sys.path.insert(0, str(Path(__file__).parent.parent))



def main():
    print("=" * 70)
    print("Rugo - Parquet Data Decoding Example")
    print("=" * 70)
    
    # Check if we can decode a file
    test_file = 'tests/data/test_decode.parquet'
    
    print(f"\n📂 Checking file: {test_file}")
    can_decode = parquet_meta.can_decode(test_file)
    print(f"   Can decode? {can_decode}")
    
    if not can_decode:
        print("   ❌ This file cannot be decoded with the prototype decoder")
        print("   Reasons: compressed data, non-PLAIN encoding, or unsupported types")
        return
    
    # Read metadata to see what columns are available
    metadata = parquet_meta.read_metadata(test_file)
    print(f"\n📊 File has {metadata['num_rows']} rows")
    print(f"   Columns: {[col['name'] for col in metadata['row_groups'][0]['columns']]}")
    
    # Decode each column
    print("\n📋 Decoding columns:")
    print("-" * 70)
    
    for col in metadata['row_groups'][0]['columns']:
        col_name = col['name']
        col_type = col['type']
        
        print(f"\n🔹 {col_name} ({col_type}):")
        
        data = parquet_meta.decode_column(test_file, col_name)
        
        if data is None:
            print("   ❌ Failed to decode")
        else:
            print(f"   ✅ Decoded {len(data)} values")
            print(f"   First 5: {data[:5]}")
            print(f"   Last 5: {data[-5:]}")
    
    print("\n" + "=" * 70)
    print("Prototype Decoder Capabilities:")
    print("  ✅ Uncompressed columns (codec=UNCOMPRESSED)")
    print("  ✅ PLAIN encoding")
    print("  ✅ int32, int64, string types")
    print("  ❌ Compressed columns (SNAPPY, GZIP, etc.)")
    print("  ❌ Dictionary encoding")
    print("  ❌ Delta encoding")
    print("  ❌ Other encodings (RLE_DICTIONARY, etc.)")
    print("  ❌ Other types (float, boolean, date, timestamp, etc.)")
    print("=" * 70)
    
    # Test with other files
    print("\n🧪 Testing with other files:")
    other_files = [
        'tests/data/binary.parquet',
        'tests/data/planets.parquet',
        'tests/data/alltypes_plain.parquet'
    ]
    
    for file_path in other_files:
        can_decode = parquet_meta.can_decode(file_path)
        status = "✅" if can_decode else "❌"
        print(f"   {status} {Path(file_path).name}")


if __name__ == "__main__":
    main()
