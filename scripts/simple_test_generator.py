#!/usr/bin/env python3
"""
Simplified test Parquet file generator function.

This provides a single function to create test Parquet files without the full framework.
Useful for quick testing with rugo.
"""

import random
from typing import Optional


def create_simple_test_parquet(
    output_path: str,
    num_rows: int = 1000,
    num_row_groups: int = 3,
    include_strings: bool = True,
    compression: str = 'none',
    seed: Optional[int] = 42
) -> bool:
    """
    Create a simple test Parquet file compatible with rugo's decoder.
    
    Args:
        output_path: Where to save the file
        num_rows: Total number of rows
        num_row_groups: Number of row groups to create
        include_strings: Whether to include string columns
        compression: 'none' for uncompressed (rugo compatible) or 'snappy', 'gzip', etc.
        seed: Random seed for reproducible data
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print("❌ PyArrow is required. Install with: pip install pyarrow")
        return False
    
    if seed is not None:
        random.seed(seed)
    
    rows_per_group = num_rows // num_row_groups
    
    print(f"Creating test Parquet file: {output_path}")
    print(f"  Rows: {num_rows:,} ({num_row_groups} groups of ~{rows_per_group:,} rows)")
    print(f"  Compression: {compression}")
    
    # Generate simple test data
    data = {
        'id': list(range(1, num_rows + 1)),
        'value': [random.randint(0, 1000000) for _ in range(num_rows)],
        'score': [random.randint(-1000, 1000) for _ in range(num_rows)],
    }
    
    if include_strings:
        data['name'] = [f'user_{i:08d}' for i in range(num_rows)]
        data['category'] = [f'group_{i % 20:02d}' for i in range(num_rows)]
    
    # Create PyArrow arrays with explicit types
    arrays = [
        pa.array(data['id'], type=pa.int32()),
        pa.array(data['value'], type=pa.int64()),
        pa.array(data['score'], type=pa.int32()),
    ]
    names = ['id', 'value', 'score']
    
    if include_strings:
        arrays.extend([
            pa.array(data['name'], type=pa.string()),
            pa.array(data['category'], type=pa.string())
        ])
        names.extend(['name', 'category'])
    
    # Create table
    table = pa.table(arrays, names=names)
    
    # Write with controlled row groups
    try:
        # For uncompressed files, disable dictionary encoding to ensure PLAIN encoding
        use_dictionary = compression != 'none'
        
        if num_row_groups == 1:
            # Simple case: write entire table at once
            pq.write_table(
                table,
                output_path,
                compression=compression if compression != 'none' else None,
                use_dictionary=use_dictionary,
                row_group_size=rows_per_group
            )
        else:
            # Multiple row groups: use ParquetWriter to write in chunks
            with pq.ParquetWriter(
                output_path,
                table.schema,
                compression=compression if compression != 'none' else None,
                use_dictionary=use_dictionary
            ) as writer:
                
                # Write in chunks to create multiple row groups
                for i in range(num_row_groups):
                    start_idx = i * rows_per_group
                    chunk_size = min(rows_per_group, num_rows - start_idx)
                    chunk = table.slice(start_idx, chunk_size)
                    writer.write_table(chunk)
        
        # Verify the file
        file_info = pq.ParquetFile(output_path)
        import os
        file_size = os.path.getsize(output_path)
        
        print(f"  ✅ Created: {file_size:,} bytes, {file_info.num_row_groups} row groups")
        return True
        
    except Exception as e:
        print(f"  ❌ Failed to create file: {e}")
        return False


def test_with_rugo(parquet_file_path: str) -> None:
    """Test the created file with rugo if available."""
    try:
        import rugo.parquet as rp
        
        print(f"\n🧪 Testing {parquet_file_path} with rugo...")
        
        # Check if rugo can decode it
        can_decode = rp.can_decode(parquet_file_path)
        print(f"   Can decode: {can_decode}")
        
        if not can_decode:
            print("   ⚠️  File cannot be decoded by rugo (likely compressed or uses unsupported encoding)")
            return
        
        # Load and decode
        with open(parquet_file_path, 'rb') as f:
            data = f.read()
        
        # Test reading all columns
        table = rp.read_parquet(data)
        
        if table and table.get('success'):
            print("   ✅ Successfully decoded!")
            print(f"   Columns: {table['column_names']}")
            print(f"   Row groups: {len(table['row_groups'])}")
            
            # Show sample from each row group
            total_rows = 0
            for rg_idx, row_group in enumerate(table['row_groups']):
                if row_group and row_group[0]:  # Check first column
                    rg_rows = len(row_group[0])
                    total_rows += rg_rows
                    print(f"   Row group {rg_idx}: {rg_rows:,} rows")
                    
                    # Show sample values from first few columns
                    for col_idx, col_name in enumerate(table['column_names'][:3]):
                        if col_idx < len(row_group) and row_group[col_idx]:
                            sample = row_group[col_idx][:3]
                            print(f"     {col_name}: {sample}")
            
            print(f"   Total decoded rows: {total_rows:,}")
            
        else:
            print("   ❌ Failed to decode")
            
    except ImportError:
        print(f"\n⚠️  rugo not available for testing {parquet_file_path}")
    except Exception as e:
        print(f"\n❌ Error testing {parquet_file_path}: {e}")


if __name__ == "__main__":
    print("Simple Test Parquet Generator")
    print("=" * 35)
    
    # Create test files
    test_files = []
    
    # 1. Small uncompressed file (rugo compatible)
    if create_simple_test_parquet(
        "small_uncompressed.parquet",
        num_rows=300,
        num_row_groups=3,
        compression='none'
    ):
        test_files.append("small_uncompressed.parquet")
    
    # 2. Larger uncompressed file (rugo compatible)
    if create_simple_test_parquet(
        "large_uncompressed.parquet", 
        num_rows=5000,
        num_row_groups=5,
        compression='none'
    ):
        test_files.append("large_uncompressed.parquet")
    
    # 3. Compressed file (rugo incompatible)
    if create_simple_test_parquet(
        "compressed.parquet",
        num_rows=1000,
        num_row_groups=2,
        compression='snappy'
    ):
        test_files.append("compressed.parquet")
    
    # Test each file with rugo
    for file_path in test_files:
        test_with_rugo(file_path)
    
    print(f"\n📁 Created {len(test_files)} test files")
    print("\n💡 Usage:")
    print("   import rugo.parquet as rp")
    print("   table = rp.read_parquet(open('small_uncompressed.parquet', 'rb').read())")
    print("   print(table['column_names'])")
