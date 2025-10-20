# JSONL Performance Comparison: rugo vs Opteryx

## Overview

This document presents a comprehensive performance comparison between rugo's JSONL reader and Opteryx's JSONL reader on a 50-column dataset. The comparison focuses on Linux x86_64 architecture with Python 3.12 (closest available to requested Python 3.11).

## Important Note on Opteryx Implementation

### Release Version (0.25.1) - Tested in This Benchmark

The benchmark results in this document are from testing against **Opteryx 0.25.1** (PyPI release), which uses a **Python-based reader** (`opteryx.utils.file_decoders.jsonl_decoder`) with the **csimdjson** library (a C/C++ extension wrapping the simdjson library) for JSON parsing.

### Main Branch Version (0.26.0+) - Available on GitHub

The **main branch** on GitHub (version 0.26.0-beta and later) includes a significantly faster **Cython-based JSONL decoder** (`opteryx.compiled.structures.jsonl_decoder`) with:
- Custom SIMD optimizations (AVX/NEON)
- Fast path for columnar decoding
- Type-specific optimizations
- Projection pushdown support

**To test against the latest main branch:**
```bash
pip install git+https://github.com/mabel-dev/opteryx.git
```

The Cython decoder in the main branch is expected to perform significantly better than the Python-based decoder tested here, potentially closing the performance gap with rugo considerably.

While Opteryx contains many Cython-compiled modules for other operations (joins, aggregations, table operations, etc.), only the main branch includes a Cython-compiled JSONL reader.

## Test Environment

- **Platform**: Linux-6.11.0-1018-azure-x86_64 with glibc2.39
- **Python Version**: 3.12.3 (GCC 13.3.0)
- **Processor**: x86_64
- **Architecture**: x86_64

## Dataset Characteristics

The benchmark uses a 50-column dataset with diverse data types:

- **10 Integer columns**: IDs, counters, rankings, scores
- **15 String columns**: Names, emails, descriptions, categories, statuses
- **15 Float columns**: Prices, measurements, coordinates, scores
- **10 Boolean columns**: Various flags and states

This distribution represents realistic business data with mixed types commonly found in analytics workloads.

## Key Architectural Differences

### rugo
- **Implementation**: C++17 with SIMD optimizations (AVX2/SSE2)
- **Projection Pushdown**: ✅ Yes - Only parses requested columns
- **Memory Model**: Zero-copy parsing with memoryview
- **String Parsing**: Bulk memory copy with escape handling
- **SIMD Operations**: Custom AVX2/SSE2 for newline detection and text scanning

### Opteryx (Release 0.25.1 - Tested)
- **Implementation**: Python with csimdjson (C/C++ extension wrapping simdjson)
- **Projection Pushdown**: ❌ No - Parses all columns, then filters
- **Memory Model**: Reads full JSON, converts to PyArrow
- **String Parsing**: Uses simdjson parser (C++ library via csimdjson binding)
- **SIMD Operations**: Via simdjson library for JSON parsing

**Note**: The release version (0.25.1) uses a Python function (`opteryx.utils.file_decoders.jsonl_decoder`) with csimdjson for parsing. 

### Opteryx (Main Branch 0.26.0+ - Not Tested)
- **Implementation**: Cython-based fast decoder with SIMD (AVX/NEON)
- **Projection Pushdown**: ✅ Yes - Can extract specific columns during decode
- **Memory Model**: Direct columnar decoding
- **String Parsing**: Cython-optimized with SIMD
- **SIMD Operations**: Custom AVX/NEON implementations for text scanning

**Note**: The main branch includes `opteryx.compiled.structures.jsonl_decoder`, a Cython-based decoder expected to be significantly faster than the release version. This was not tested in these benchmarks.

## Benchmark Results

### Test 1: 10,000 Rows (~11.6 MB)

| Operation | rugo Time | rugo Throughput | Opteryx Time | Opteryx Throughput | Speedup |
|-----------|-----------|-----------------|--------------|-------------------|---------|
| Full Read (50 cols) | 0.092s | 109K rows/sec | 0.250s | 40K rows/sec | **2.72x faster** |
| Projection (10 cols) | 0.057s | 174K rows/sec | 0.218s | 46K rows/sec | **3.80x faster** |
| Projection (5 cols) | 0.055s | 181K rows/sec | 0.217s | 46K rows/sec | **3.93x faster** |

### Test 2: 50,000 Rows (~58.4 MB)

| Operation | rugo Time | rugo Throughput | Opteryx Time | Opteryx Throughput | Speedup |
|-----------|-----------|-----------------|--------------|-------------------|---------|
| Full Read (50 cols) | 0.459s | 109K rows/sec | 1.261s | 40K rows/sec | **2.75x faster** |
| Projection (10 cols) | 0.265s | 189K rows/sec | 1.272s | 39K rows/sec | **4.80x faster** |
| Projection (5 cols) | 0.253s | 198K rows/sec | 1.262s | 40K rows/sec | **4.99x faster** |

### Test 3: 100,000 Rows (~116.8 MB)

| Operation | rugo Time | rugo Throughput | Opteryx Time | Opteryx Throughput | Speedup |
|-----------|-----------|-----------------|--------------|-------------------|---------|
| Full Read (50 cols) | 0.918s | 109K rows/sec | 2.864s | 35K rows/sec | **3.12x faster** |
| Projection (10 cols) | 0.523s | 191K rows/sec | 2.815s | 36K rows/sec | **5.39x faster** |
| Projection (5 cols) | 0.497s | 201K rows/sec | 2.792s | 36K rows/sec | **5.62x faster** |

## Performance Analysis

### Key Findings

1. **Consistent Performance Advantage**: rugo is consistently **2.7-5.6x faster** than Opteryx across all test scenarios
2. **Projection Benefit**: rugo's projection pushdown provides increasing benefits as fewer columns are selected (up to 5.6x speedup)
3. **Scalability**: rugo maintains consistent throughput (~109-201K rows/sec) regardless of dataset size
4. **Column Count Impact**: The 50-column dataset highlights rugo's efficiency with wide tables

### Performance Breakdown

#### Full Read Performance (50 columns)
- **rugo**: ~109K rows/sec (consistent across all dataset sizes)
- **Opteryx**: 35-40K rows/sec (varies with dataset size)
- **Advantage**: rugo is **2.7-3.1x faster**

#### Projection Performance (10 columns)
- **rugo**: 174-191K rows/sec (benefits from projection pushdown)
- **Opteryx**: 36-46K rows/sec (still parses all columns)
- **Advantage**: rugo is **3.8-5.4x faster**

#### Projection Performance (5 columns)
- **rugo**: 181-201K rows/sec (maximum benefit from projection pushdown)
- **Opteryx**: 36-46K rows/sec (no projection benefit)
- **Advantage**: rugo is **3.9-5.6x faster**

## Why is rugo Faster?

### 1. True Projection Pushdown
rugo only parses the columns you request, while Opteryx parses all columns and then filters. With 50 columns, reading only 5 columns gives rugo a 10x reduction in parsing work.

### 2. Optimized C++17 Implementation
- Custom SIMD operations for text scanning
- Zero-copy string handling
- Efficient memory allocation patterns
- Direct columnar output without intermediate representations

### 3. Memory Efficiency
- No intermediate Python objects during parsing
- Direct memory-to-column conversion
- Minimal allocations with bulk copy operations

### 4. SIMD Optimizations
- AVX2: Process 32 bytes at once for newline detection
- SSE2: Process 16 bytes at once (fallback)
- Custom implementations tuned for JSONL format

## Use Case Recommendations

### Choose rugo when:
- ✅ Working with wide tables (many columns)
- ✅ Frequently using column projection (SELECT specific columns)
- ✅ Need consistent high throughput
- ✅ Processing large JSONL files
- ✅ Memory-based processing is preferred
- ✅ Maximum performance is critical

### Choose Opteryx when:
- ✅ Need full SQL query engine capabilities
- ✅ Working with multiple data sources
- ✅ Need advanced query planning and optimization
- ✅ Require database-like features (JOINs, aggregations, etc.)
- ✅ Integration with broader data pipeline

## Conclusion

For **pure JSONL reading performance**, especially with wide tables and column projection, rugo demonstrates significant advantages over **Opteryx 0.25.1 (release version)**:

- **2.7-5.6x faster** than Opteryx 0.25.1
- **Consistent throughput** across dataset sizes
- **True projection pushdown** that provides real performance benefits
- **Efficient memory usage** with zero-copy design

The performance gap widens with:
1. More columns in the dataset (50 columns tested)
2. Fewer columns in the projection (5 columns shows 5.6x speedup)
3. Larger datasets (100K rows shows best speedup)

For Python 3.11+ on Linux with 50-column datasets, **rugo is significantly faster** than Opteryx 0.25.1 for JSONL reading operations.

### Important Caveat: Opteryx Main Branch

These benchmarks test against **Opteryx 0.25.1** (PyPI release). The **main branch** (0.26.0-beta+) on GitHub includes a new **Cython-based JSONL decoder** with custom SIMD optimizations that is expected to perform significantly better. The Cython decoder includes:

- Direct columnar decoding
- Custom AVX/NEON SIMD implementations  
- Type-specific optimizations
- Projection pushdown support

A future benchmark comparing rugo against Opteryx's main branch Cython decoder would provide a more accurate comparison of the latest capabilities of both libraries.

## Running the Benchmark

To reproduce these results:

## Running the Benchmark

```bash
# Install dependencies
pip install rugo opteryx pyarrow

# Compile rugo (if from source)
make compile

# Run benchmark
python benchmarks/compare_opteryx_performance.py
```

**Testing Against Main Branch**: The Opteryx main branch (0.26.0-beta) includes a Cython-based decoder expected to be significantly faster, but it's not yet released on PyPI. See `TESTING_OPTERYX_MAIN.md` for installation details and `OPTERYX_DECODER_ANALYSIS.md` for a detailed technical analysis of the Cython decoder and potential improvements for rugo.

## Notes

- All benchmarks use averaged results from 5 iterations
- Times measured with Python's `time.perf_counter()` for high precision
- Tests run on the same hardware with same Python version
- Both libraries tested with optimal configurations
- Memory-based processing (no disk I/O during tests)
