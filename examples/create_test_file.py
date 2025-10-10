#!/usr/bin/env python3
"""
Simple example of using the test Parquet file generator.

This creates a small test file that should be compatible with rugo's decoder.
"""

import os
import sys

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from generate_test_parquet import create_test_parquet_file

def main():
    # Create a simple test file that rugo can decode
    output_path = "rugo_test_file.parquet"
    
    # Simple configuration: only types that rugo supports
    column_specs = [
        {
            'name': 'id', 
            'type': 'int32', 
            'min_value': 1, 
            'max_value': 1000
        },
        {
            'name': 'value', 
            'type': 'int64', 
            'min_value': 0, 
            'max_value': 1000000
        },
        {
            'name': 'name', 
            'type': 'string', 
            'pattern': 'sequential',  # Creates "string_000001", "string_000002", etc.
            'string_length': 15
        },
        {
            'name': 'category', 
            'type': 'string', 
            'pattern': 'repeated',    # Creates repeated values for better testing
            'string_length': 8
        }
    ]
    
    # Create a small file: 3 row groups with 100 rows each
    stats = create_test_parquet_file(
        output_path=output_path,
        column_specs=column_specs,
        rows_per_group=100,
        num_groups=3,
        compression='none',  # No compression so rugo can decode it
        encoding={           # PLAIN encoding so rugo can decode it
            'id': 'PLAIN',
            'value': 'PLAIN', 
            'name': 'PLAIN',
            'category': 'PLAIN'
        },
        seed=42  # Reproducible data
    )
    
    print(f"\n📁 Test file created: {output_path}")
    print(f"📊 File stats: {stats}")
    
    # Test with rugo if available
    try:
        import rugo.parquet as rp
        
        print("\n🧪 Testing with rugo...")
        
        # Test if rugo can decode it
        can_decode = rp.can_decode(output_path)
        print(f"   Can decode: {can_decode}")
        
        if can_decode:
            # Read metadata
            with open(output_path, 'rb') as f:
                data = f.read()
            
            print(f"   File size: {len(data)} bytes")
            
            # Test the new API
            table = rp.read_parquet(data)
            
            if table and table['success']:
                print("   ✅ Successfully read with rugo!")
                print(f"   Columns: {table['column_names']}")
                print(f"   Row groups: {len(table['row_groups'])}")
                
                # Show sample data from first row group
                if table['row_groups']:
                    rg = table['row_groups'][0]
                    print("   Sample data from first row group:")
                    for i, col_name in enumerate(table['column_names']):
                        if i < len(rg) and rg[i]:
                            sample = rg[i][:5]  # First 5 values
                            print(f"     {col_name}: {sample}")
            else:
                print("   ❌ Failed to read with rugo")
        
    except ImportError:
        print("\n⚠️  rugo not available for testing")
    except Exception as e:
        print(f"\n❌ Error testing with rugo: {e}")

if __name__ == "__main__":
    main()