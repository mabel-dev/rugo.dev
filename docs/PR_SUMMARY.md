# JSON Lines Reader SIMD Performance Improvements

## Summary

This PR adds SIMD (Single Instruction, Multiple Data) optimizations to the JSON Lines reader in rugo, inspired by similar optimizations used in Opteryx's JSON Lines reader. These optimizations focus on text searching operations which are critical for JSON parsing performance.

## Changes Made

### 1. New SIMD Helper Functions (`rugo/jsonl_src/simd_helpers.hpp`)
- **FindNewline**: AVX2/SSE2-accelerated newline detection (processes 16-32 bytes at once)
- **SkipWhitespace**: Fast whitespace skipping using SIMD comparisons
- **FindQuote**: Quote detection with escape sequence handling
- **FindChar**: Generic character search for JSON delimiters

### 2. Optimized String Parsing (`rugo/jsonl_src/jsonl_reader.cpp`)
- Replaced character-by-character string building with bulk memory copy operations
- Reduced string allocations by using `std::string::assign()` for contiguous data
- Fast path for strings without escape sequences (most common case)

### 3. Build System Updates (`setup.py`)
- Added AVX2 and SSE4.2 compiler flags for x86-64 architecture
- Automatic SIMD instruction detection at compile time
- Graceful fallback to scalar operations on non-x86 platforms

## Performance Results

### Before vs After

**100K rows, 5 columns (baseline test):**
- Before: ~1.42M rows/sec (projection)
- After: ~1.69M rows/sec (projection)
- **Improvement: +19%**

### Comprehensive Benchmark Results

| Dataset | Operation | Throughput |
|---------|-----------|------------|
| 10K rows | Full read (8 cols) | 739K rows/sec |
| 10K rows | Projection (3 cols) | 1.07M rows/sec |
| 10K rows | Projection (2 cols) | 1.14M rows/sec |
| 100K rows | Full read (8 cols) | 790K rows/sec |
| 100K rows | Projection (3 cols) | 1.14M rows/sec |
| 100K rows | Projection (2 cols) | 1.22M rows/sec |
| 250K rows | Full read (8 cols) | 796K rows/sec |
| 250K rows | Projection (3 cols) | 1.12M rows/sec |
| 250K rows | Projection (2 cols) | 1.21M rows/sec |

## Key Benefits

1. **Faster Text Searching**: SIMD operations process 16-32 bytes in parallel instead of one byte at a time
2. **Reduced Memory Allocations**: Bulk copy operations minimize reallocations during string parsing
3. **Better Projection Performance**: Optimizations particularly benefit queries that read only specific columns
4. **Scalable Performance**: Consistent throughput across different dataset sizes
5. **Backward Compatible**: Automatic fallback to scalar operations when SIMD isn't available

## Technical Details

### SIMD Instruction Sets Used
- **AVX2** (preferred): 256-bit operations, processes 32 bytes per iteration
- **SSE2** (fallback): 128-bit operations, processes 16 bytes per iteration  
- **Scalar** (fallback): Byte-by-byte processing for non-x86 architectures

### Example: AVX2 Newline Detection
```cpp
__m256i newline_vec = _mm256_set1_epi8('\n');
__m256i chunk = _mm256_loadu_si256(ptr);
__m256i cmp = _mm256_cmpeq_epi8(chunk, newline_vec);
int mask = _mm256_movemask_epi8(cmp);
if (mask != 0) {
    return ptr + __builtin_ctz(mask);
}
```

This processes 32 bytes in a single instruction, dramatically faster than checking each byte individually.

## Testing

- ✅ All existing tests pass
- ✅ No security vulnerabilities (CodeQL analysis clean)
- ✅ Performance improvements verified with comprehensive benchmarks
- ✅ Tested on x86-64 with AVX2/SSE2 support

## Related Work

This implementation is inspired by similar SIMD optimizations in:
- Opteryx JSON Lines reader
- simdjson library
- RapidJSON library

## Files Changed

- `rugo/jsonl_src/simd_helpers.hpp` (new): SIMD helper functions
- `rugo/jsonl_src/jsonl_reader.cpp` (modified): Optimized string parsing
- `setup.py` (modified): Added SIMD compiler flags
- `benchmark_jsonl.py` (new): Comprehensive performance benchmark
- `JSONL_SIMD_OPTIMIZATIONS.md` (new): Detailed optimization documentation

## How to Use

The optimizations are automatically applied when building from source on x86-64 platforms:

```bash
make compile
# or
python setup.py build_ext --inplace
```

No code changes required - the reader API remains unchanged.

## Future Enhancements

Potential areas for additional optimization:
1. SIMD-based number parsing
2. Parallel processing of multiple JSON lines
3. Memory pooling for string allocations
4. Vectorized schema inference
