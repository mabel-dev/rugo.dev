# Opteryx JSONL Decoder Analysis & Improvement Ideas

## Overview

This document analyzes the Cython-based JSONL decoder in Opteryx's main branch (v0.26.0-beta.1666) and identifies potential improvements for rugo's JSONL reader.

## Opteryx Decoder Architecture

### Key Components

The Opteryx decoder (`opteryx.compiled.structures.jsonl_decoder`) is a 479-line Cython implementation with the following architecture:

#### 1. **SIMD Operations** (`src/cpp/simd_search.h`)
- **Character search**: `avx_search()` and `neon_search()` for finding specific characters
- **Character counting**: `avx_count()` and `neon_count()` for counting occurrences
- **Delimiter detection**: `avx_find_delimiter()` and `neon_find_delimiter()` for JSON delimiters
- **Architecture detection**: Runtime detection of ARM64/AArch64 vs x86_64

#### 2. **Single-Pass Value Extraction**
```cython
cdef inline void extract_all_values(
    const char* line, Py_ssize_t line_len,
    const char** key_ptrs, Py_ssize_t* key_lengths,
    int num_cols, const char** value_ptrs,
    Py_ssize_t* value_lens, int* found_flags)
```

**Key Innovation**: Extracts all requested column values in a single pass through each line using:
- Pre-computed key pointers and lengths
- Memory comparison (`memcmp`) for key matching
- Pointer-based value extraction without string copies

#### 3. **Type-Specific Parsing**
```cython
cdef enum ColumnType:
    COL_BOOLEAN = 0
    COL_INTEGER = 1
    COL_FLOAT = 2
    COL_BINARY = 3
    COL_OTHER = 4
```

**Optimizations**:
- `fast_atoll()`: Custom integer parsing without string allocation
- `parse_float_direct()`: Uses fast_float library (C++ port of Daniel Lemire's algorithm)
- Boolean parsing: Direct `memcmp` against "true"/"false" literals
- String parsing: Returns raw bytes without unnecessary decoding

#### 4. **Memory Pre-allocation**
```cython
# Pre-count lines for preallocation
line_count = simd_count(data, data_len, 10)  # Count '\n'
estimated_lines = line_count + 1

# Preallocate column lists
for i in range(num_cols):
    col_list = [None] * estimated_lines
```

**Benefit**: Eliminates repeated list resizing during parsing

#### 5. **Fast Float Parsing**
Uses `fastfloat` library (C++ implementation of Daniel Lemire's algorithm):
```cython
from opteryx.third_party.fastfloat.fast_float cimport c_parse_fast_float
```

This is significantly faster than Python's `float()` or standard `atof()`.

## Comparison with rugo's Implementation

### What rugo Already Does Well

1. **Projection Pushdown**: rugo implements true projection at parse time
2. **SIMD Text Scanning**: Custom AVX2/SSE2 for newline and text operations
3. **Zero-Copy Design**: Direct memory-to-column conversion
4. **Bulk String Operations**: Uses bulk `assign()` for strings without escapes

### Potential Improvements from Opteryx

#### 1. **Single-Pass Multi-Column Extraction** ⭐⭐⭐ HIGH PRIORITY
**Current rugo approach**: Likely parses JSON, then extracts columns
**Opteryx approach**: Single pass through each line extracting all requested columns simultaneously

**Benefit**: Reduced cache misses, better CPU pipeline utilization

**Implementation idea**:
```cpp
// Pre-compute key information
std::vector<const char*> key_ptrs;
std::vector<size_t> key_lengths;
for (const auto& col : requested_columns) {
    key_ptrs.push_back(col.data());
    key_lengths.push_back(col.size());
}

// Single pass extraction
while (parsing_line) {
    find_key_start();
    for (size_t i = 0; i < num_cols; i++) {
        if (memcmp(key_start, key_ptrs[i], key_lengths[i]) == 0) {
            extract_value_directly_to_column[i];
            break;
        }
    }
}
```

#### 2. **Fast Float Parsing Library** ⭐⭐⭐ HIGH PRIORITY
**Current rugo approach**: Likely uses standard C++ float parsing
**Opteryx approach**: Uses fast_float library (Daniel Lemire's algorithm)

**Benefit**: 2-4x faster float parsing

**Implementation**:
- Add fast_float as a vendored dependency
- Replace `std::stod()` or `atof()` with `fast_float::from_chars()`

**Reference**: https://github.com/fastfloat/fast_float

#### 3. **Pre-counting Lines for Memory Pre-allocation** ⭐⭐ MEDIUM PRIORITY
**Current rugo approach**: Lists grow dynamically
**Opteryx approach**: SIMD count of newlines, pre-allocate exact size

**Benefit**: Eliminates reallocation overhead, better memory locality

**Implementation**:
```cpp
// Use existing SIMD newline counter
size_t line_count = count_newlines_simd(data, data_len);
for (auto& column_vector : columns) {
    column_vector.reserve(line_count);
}
```

#### 4. **Custom Fast Integer Parsing** ⭐⭐ MEDIUM PRIORITY
**Current rugo approach**: Likely uses `std::stoll()` or similar
**Opteryx approach**: Custom `fast_atoll()` implementation

**Benefit**: Avoids string allocation, 2-3x faster for simple integers

**Implementation**:
```cpp
inline int64_t fast_parse_int(const char* str, size_t len) {
    int64_t value = 0;
    int sign = 1;
    size_t i = 0;
    
    if (str[0] == '-') { sign = -1; i = 1; }
    else if (str[0] == '+') { i = 1; }
    
    for (; i < len; i++) {
        value = value * 10 + (str[i] - '0');
    }
    return sign * value;
}
```

#### 5. **Delimiter Finding SIMD** ⭐ LOW PRIORITY
**Opteryx approach**: `avx_find_delimiter()` finds any of: space, comma, `}`, `]`, tab, newline

**Benefit**: Marginal - rugo likely has similar functionality

#### 6. **Boolean Literal Matching** ⭐ LOW PRIORITY
**Opteryx approach**: Direct `memcmp` against constant literals
```cython
cdef const char* LIT_TRUE = b"true"
cdef const char* LIT_FALSE = b"false"

if value_len == 4 and memcmp(value_ptr, LIT_TRUE, 4) == 0:
    result = True
```

**Benefit**: Marginal improvement over parsing

## Recommendations for rugo

### Phase 1: High-Impact Improvements

1. **Integrate fast_float library** (Expected: 2-4x float parsing speedup)
   - Vendor the fast_float single-header library
   - Replace float parsing with `fast_float::from_chars()`
   - Test with float-heavy datasets

2. **Implement single-pass multi-column extraction** (Expected: 10-15% overall speedup)
   - Pre-compute key pointers and lengths for requested columns
   - Extract all columns in single pass through each line
   - Use memcmp for key matching instead of string comparisons

3. **Add custom fast integer parser** (Expected: 2-3x integer parsing speedup)
   - Implement digit-by-digit parsing without string allocation
   - Handle sign detection inline
   - Add overflow detection

### Phase 2: Memory Optimizations

4. **Pre-count and pre-allocate** (Expected: 5-8% speedup, better memory profile)
   - Use existing SIMD newline counter
   - Pre-allocate column vectors to exact size
   - Eliminate vector resizing overhead

### Phase 3: Micro-optimizations

5. **Optimize boolean parsing** (Expected: <1% overall impact)
   - Use memcmp against constant literals
   - Skip JSON parsing for simple values

## Testing Strategy

### Benchmark Comparison
Create new benchmarks comparing:
- Float-heavy datasets (test fast_float impact)
- Integer-heavy datasets (test fast_atoll impact)  
- Wide tables with projection (test single-pass extraction)

### Specific Test Cases
1. **Dataset with 50 float columns, 100K rows** → Measure fast_float impact
2. **Dataset with 50 int columns, 100K rows** → Measure fast_atoll impact
3. **Dataset with 50 mixed columns, projection to 5 columns** → Measure single-pass impact

## Conclusion

The Opteryx Cython decoder demonstrates several optimization techniques that could benefit rugo:

**Highest Priority**:
1. Fast float parsing (fast_float library) - Easy to integrate, high impact
2. Single-pass multi-column extraction - More complex but significant benefit
3. Custom integer parsing - Medium complexity, good impact

**Implementation Order**:
1. Start with fast_float (easiest, high impact)
2. Add custom integer parser (moderate effort, good impact)  
3. Implement single-pass extraction (complex but worth it)
4. Add pre-allocation optimization (relatively easy)

These improvements could potentially close or reverse the performance gap when comparing against the Opteryx main branch, while maintaining rugo's architectural advantages of true projection pushdown and zero-copy design.

## References

- Opteryx GitHub: https://github.com/mabel-dev/opteryx
- fast_float library: https://github.com/fastfloat/fast_float
- Daniel Lemire's blog on fast number parsing: https://lemire.me/blog/
