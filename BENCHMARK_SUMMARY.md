# Performance Comparison Summary: rugo vs Opteryx

## Executive Summary

Performance benchmarking on 50-column JSONL datasets shows that **rugo is 2.7-5.6x faster** than Opteryx for JSONL reading operations on Linux x86_64.

**Note**: This comparison is against Opteryx's Python-based JSONL reader (`opteryx.utils.file_decoders.jsonl_decoder`) which uses the csimdjson C/C++ extension for JSON parsing. While Opteryx has many Cython-compiled modules for other operations, the JSONL reader itself is not Cython-based.

## Test Configuration

- **Platform**: Linux x86_64 (Ubuntu/Azure)
- **Python**: 3.12.3 (closest available to requested 3.11)
- **Dataset**: 50 columns (10 int, 15 string, 15 float, 10 bool)
- **Test Sizes**: 10K, 50K, 100K rows

## Key Results

### 100,000 Rows (~116.8 MB)

| Operation | rugo | Opteryx | Speedup |
|-----------|------|---------|---------|
| Full Read (50 cols) | 0.918s (109K rows/sec) | 2.864s (35K rows/sec) | **3.12x** |
| Projection (10 cols) | 0.523s (191K rows/sec) | 2.815s (36K rows/sec) | **5.39x** |
| Projection (5 cols) | 0.497s (201K rows/sec) | 2.792s (36K rows/sec) | **5.62x** |

## Why rugo is Faster

1. **True Projection Pushdown**: Only parses requested columns (Opteryx parses all then filters)
2. **C++17 + SIMD**: Custom AVX2/SSE2 optimizations for text scanning
3. **Zero-Copy Design**: Direct memory-to-column conversion
4. **Efficient Memory Allocation**: Bulk copy operations, minimal intermediate objects

## Architectural Differences

### rugo
- ✅ Projection pushdown at parse time
- ✅ C++17 implementation with custom SIMD
- ✅ Zero-copy memoryview processing
- ✅ Direct columnar output

### Opteryx
- ❌ No projection pushdown (parses all columns)
- ✅ Uses csimdjson (C/C++ extension wrapping simdjson)
- ❌ Converts to PyArrow after parsing
- ❌ Creates intermediate Python objects

**Implementation**: The Opteryx JSONL reader is a Python function that uses csimdjson (a C/C++ extension) for parsing. It's not a Cython-based reader.

## Performance Trend

The speedup increases with:
- More columns in dataset (50 columns tested)
- Fewer columns in projection (5 cols = 5.6x speedup)
- Larger datasets (100K rows = best speedup)

## Recommendation

For **JSONL reading performance** on wide tables with column projection, rugo is the clear winner. Use Opteryx when you need full SQL engine capabilities beyond simple data reading.

## Files Added

1. `benchmarks/compare_opteryx_performance.py` - Comprehensive benchmark script
2. `PERFORMANCE_COMPARISON.md` - Detailed results and analysis
3. `benchmarks/README.md` - Benchmark documentation
4. Updated `README.md` - Performance section with Opteryx comparison

## Running the Benchmark

```bash
# Install dependencies
pip install opteryx

# Run benchmark
python benchmarks/compare_opteryx_performance.py
```

The benchmark automatically handles cases where Opteryx is not installed and provides rugo-only results.
