# Parquet Data Decoding - Implementation Summary

## Overview
This implementation adds a prototype Parquet data decoder to the rugo library, enabling reading of actual column data from Parquet files (not just metadata).

## Implementation Details

### New Files Created

1. **`rugo/parquet/decode.hpp`** - Header file with function declarations
   - `CanDecode()` - Checks if a file can be decoded with our limited decoder
   - `DecodeColumn()` - Decodes a specific column from a Parquet file
   - `DecodedColumn` struct - Holds decoded data in type-specific vectors

2. **`rugo/parquet/decode.cpp`** - C++ implementation
   - Implements file reading and page header parsing
   - Decodes PLAIN-encoded int32, int64, and byte_array (string) data
   - Uses existing Thrift parsing infrastructure from `thrift.hpp`
   - Handles uncompressed columns only

3. **`tests/test_decode.py`** - Comprehensive test suite
   - Tests `can_decode()` with various file types
   - Tests `decode_column()` with int32, int64, and string columns
   - Tests error handling (non-existent columns, compressed files)
   - 10 tests, all passing

4. **`tests/data/test_decode.parquet`** - Test data file
   - Created with PyArrow
   - Contains non-nullable int32, int64, and string columns
   - Uses no compression and PLAIN encoding

5. **`examples/decode_example.py`** - Demonstration script
   - Shows how to use `can_decode()` and `decode_column()`
   - Explains decoder capabilities and limitations
   - Tests multiple files to show what can and cannot be decoded

### Modified Files

1. **`rugo/parquet/metadata_reader.pxd`** - Cython declarations
   - Added `DecodedColumn` struct declaration
   - Added `CanDecode()` and `DecodeColumn()` function declarations

2. **`rugo/parquet/metadata_reader.pyx`** - Cython implementation
   - Added `can_decode()` Python function
   - Added `decode_column()` Python function
   - Converts C++ vectors to Python lists
   - Handles type conversions (byte_array → UTF-8 strings)

3. **`setup.py`** - Build configuration
   - Added `decode.cpp` to the sources list for compilation

4. **`README.md`** - Documentation
   - Added "Prototype Data Decoding (Experimental)" section
   - Documented supported and unsupported features
   - Added usage examples
   - Updated project layout
   - Updated status and limitations

## Capabilities

### Supported Features ✅
- **Compression**: Uncompressed columns only (`codec=UNCOMPRESSED`)
- **Encoding**: PLAIN encoding only
- **Types**: `int32`, `int64`, `byte_array` (strings)
- **Output**: Python lists with native Python types (int, str)

### Unsupported Features ❌
- Compressed columns (SNAPPY, GZIP, ZSTD, LZO, BROTLI, LZ4)
- Dictionary encoding
- Delta encoding (DELTA_BINARY_PACKED, DELTA_BYTE_ARRAY)
- RLE_DICTIONARY encoding
- Other data types (float32, float64, boolean, date, timestamp, complex types)
- Nullable columns (columns with definition levels)
- Multiple row groups (only first row group is decoded)
- Nested/complex types

## API

### `can_decode(path: str) -> bool`
Checks if a Parquet file can be decoded with the prototype decoder.

```python
import rugo.parquet as parquet_meta

if parquet_meta.can_decode("data.parquet"):
    print("File can be decoded!")
else:
    print("File needs PyArrow or another full decoder")
```

### `decode_column(path: str, column_name: str) -> Optional[List]`
Decodes a specific column and returns a Python list.

```python
values = parquet_meta.decode_column("data.parquet", "my_column")
if values is not None:
    print(f"Decoded {len(values)} values: {values}")
else:
    print("Failed to decode column")
```

## Technical Implementation Notes

### Page Structure Handling
The decoder parses Parquet DataPage v1 structures:
1. **Page Header** (Thrift Compact Protocol)
   - Page type (should be 0 for DATA_PAGE)
   - Compressed/uncompressed sizes
   - Number of values
2. **Definition Levels** (if column is nullable) - NOT SUPPORTED
3. **Repetition Levels** (if column is repeated) - NOT SUPPORTED  
4. **Data** (PLAIN encoded)

For non-nullable, non-repeated columns (our target), data immediately follows the page header.

### Memory Management
- Reads entire column chunk into memory
- Parses page header in-place
- Creates new vectors/strings for decoded values
- Returns data as Python lists (copies data to Python objects)

### Error Handling
- Returns `False` from `can_decode()` if file cannot be decoded
- Returns `None` from `decode_column()` on any error
- Catches all C++ exceptions and returns gracefully
- Validates file size, offsets, and data bounds

## Testing

All tests pass:
- `test_can_decode_uncompressed_plain` ✅
- `test_can_decode_compressed` ✅
- `test_can_decode_unsupported_types` ✅
- `test_decode_string_column` ✅
- `test_decode_nonexistent_column` ✅
- `test_decode_compressed_column` ✅
- `test_decode_int32_column` ✅
- `test_decode_int64_column` ✅
- `test_decode_string_column_types` ✅
- `test_can_decode_test_file` ✅

Existing tests remain unaffected.

## Future Enhancements

Potential improvements for future iterations:
1. Support for compressed columns (SNAPPY, GZIP)
2. Support for dictionary encoding
3. Support for nullable columns (definition levels)
4. Support for more data types (float, boolean, timestamps)
5. Support for all row groups, not just the first
6. Streaming/chunked reading for large columns
7. Multi-threaded decoding
8. Zero-copy string decoding where possible

## Use Cases

This prototype decoder is suitable for:
- **Testing**: Quickly reading small test files without PyArrow dependency
- **Education**: Understanding Parquet format internals
- **Simple data**: Reading very simple, uncompressed Parquet files
- **Validation**: Cross-checking values against other decoders

**Not suitable for**:
- Production workloads (use PyArrow, DuckDB, or FastParquet instead)
- Files with compression
- Files with complex schemas
- Large-scale data processing

## Conclusion

The implementation successfully adds a working prototype Parquet decoder to rugo with:
- Clean C++/Python API
- Comprehensive tests
- Clear documentation
- Proper error handling
- Minimal scope (as requested)

The decoder provides a foundation that can be extended in the future while maintaining backward compatibility with the existing metadata-only API.
