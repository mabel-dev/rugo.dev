# File Format Considerations for Rugo

## Overview

Rugo currently supports two file formats with specialized optimizations:
- **Parquet**: Optimized metadata reader and experimental column decoder
- **JSON Lines**: Columnar reader with SIMD optimizations and projection pushdown

This document evaluates additional file formats that could benefit from similar columnar optimizations and specialized implementations.

## Evaluation Criteria

When considering additional formats, we prioritize:

1. **Columnar Optimization Potential**: Can we achieve meaningful performance gains over general-purpose libraries?
2. **Industry Adoption**: Is the format widely used in data engineering and analytics?
3. **Complexity vs. Benefit**: Does the implementation complexity justify the performance gains?
4. **Complementary Strengths**: Does the format fill a gap not covered by Parquet or JSONL?

## Formats Worth Considering

### 1. Apache Arrow IPC (Feather)

**Description**: Apache Arrow's native serialization format, designed for zero-copy in-memory columnar data.

**Pros**:
- ✅ **Extremely fast**: Zero-copy reads possible with memory mapping
- ✅ **Columnar by design**: Perfect fit for Rugo's optimization philosophy
- ✅ **Growing adoption**: Used by Pandas, Polars, DuckDB, and many modern tools
- ✅ **Simple format**: Less complex than Parquet, easier to optimize
- ✅ **Interoperability**: Direct compatibility with PyArrow, Polars, and other Arrow ecosystems

**Cons**:
- ❌ **No compression by default**: Files larger than Parquet (though ZSTD compression available)
- ❌ **PyArrow already excellent**: Less room for improvement over PyArrow than with Parquet

**Optimization Opportunities**:
- Memory-mapped zero-copy reading
- Fast metadata extraction without full parse
- Direct columnar access without deserialization
- SIMD-optimized batch processing

**Recommendation**: **HIGH PRIORITY** - Arrow IPC/Feather is the natural next format for Rugo. The zero-copy design aligns perfectly with our memory-based approach, and we could provide a lightweight reader for cases where PyArrow is too heavy.

---

### 2. Apache ORC (Optimized Row Columnar)

**Description**: Columnar format from the Hadoop ecosystem, optimized for Hive and Spark workloads.

**Pros**:
- ✅ **Columnar format**: Native columnar storage with stripe-based organization
- ✅ **Rich statistics**: Built-in min/max/sum statistics for predicate pushdown
- ✅ **Efficient encoding**: Dictionary encoding, RLE, and bit packing
- ✅ **Widely used**: Common in Hadoop/Spark ecosystems

**Cons**:
- ❌ **Complex format**: Similar complexity to Parquet
- ❌ **Declining adoption**: Parquet has become more popular in modern stacks
- ❌ **Overlaps with Parquet**: Both serve similar use cases

**Optimization Opportunities**:
- Fast stripe metadata extraction
- Bloom filter access for selective reads
- Custom type-specific decoders

**Recommendation**: **MEDIUM PRIORITY** - ORC is worth considering for Hadoop/Hive ecosystem users, but it largely overlaps with Parquet. Only pursue if there's specific user demand.

---

### 3. Apache Avro

**Description**: Row-based format with schema evolution support, common in streaming systems.

**Pros**:
- ✅ **Schema evolution**: First-class support for evolving schemas
- ✅ **Common in streaming**: Widely used with Kafka and event systems
- ✅ **Compact binary format**: Efficient wire format
- ✅ **Self-describing**: Schema embedded in file

**Cons**:
- ❌ **Row-oriented**: Fundamentally row-based, less amenable to columnar optimizations
- ❌ **Against Rugo's philosophy**: We specifically optimize for columnar workloads
- ❌ **Limited optimization potential**: Can't achieve same gains as with columnar formats

**Optimization Opportunities**:
- Fast schema extraction
- Efficient row-by-row streaming decoder
- Limited columnar conversion for analytics

**Recommendation**: **LOW PRIORITY** - Avro's row-oriented design conflicts with Rugo's columnar optimization focus. The performance gains would be limited.

---

### 4. CSV/TSV with Schema Inference

**Description**: Delimited text files, ubiquitous but challenging for high-performance reading.

**Pros**:
- ✅ **Ubiquitous**: Most common data exchange format
- ✅ **Human-readable**: Easy to inspect and debug
- ✅ **Large optimization gap**: Massive potential improvement over naive readers
- ✅ **SIMD opportunities**: Similar to JSONL, can use SIMD for parsing

**Cons**:
- ❌ **No standard schema**: Requires inference or external schema
- ❌ **Ambiguous types**: Type inference is error-prone
- ❌ **Encoding complexity**: Many dialects (quotes, escaping, delimiters)
- ❌ **Not truly columnar**: Still requires full parse before columnar access

**Optimization Opportunities**:
- SIMD-accelerated delimiter detection (similar to JSONL newline detection)
- Parallel chunk processing
- Projection pushdown (skip unwanted columns during parse)
- Fast type inference
- Memory-mapped reading with zero-copy string views

**Recommendation**: **HIGH PRIORITY** - Despite being text-based, CSV is so widely used that a high-performance columnar CSV reader would be extremely valuable. We can apply similar SIMD optimizations as JSONL.

---

### 5. NDJSON/JSON (Full JSON, not JSON Lines)

**Description**: Standard JSON (single large object/array) vs. our current JSONL (one JSON per line).

**Pros**:
- ✅ **Common format**: Many APIs return JSON arrays
- ✅ **Could reuse JSONL infrastructure**: Similar parsing techniques
- ✅ **SIMD optimization potential**: Similar to JSONL

**Cons**:
- ❌ **Less columnar-friendly**: Array of objects harder to stream process
- ❌ **Memory overhead**: Must load entire structure before processing
- ❌ **JSONL already covers use case**: Users can convert to JSONL easily

**Optimization Opportunities**:
- Streaming parser for JSON arrays
- Direct columnar extraction without intermediate representation
- SIMD-optimized tokenization

**Recommendation**: **MEDIUM PRIORITY** - Nice complement to JSONL for API responses, but lower priority than CSV or Arrow.

---

### 6. MessagePack

**Description**: Binary JSON-like format, more compact than JSON.

**Pros**:
- ✅ **Compact**: Smaller than JSON, faster to parse
- ✅ **Growing adoption**: Used in RPC systems and data exchange
- ✅ **Simple format**: Easier than Parquet/ORC

**Cons**:
- ❌ **Row-oriented**: Still fundamentally row-based like JSON
- ❌ **Limited adoption**: Not as widely used as JSON/Parquet
- ❌ **Optimization potential unclear**: PyArrow and msgpack libraries already fast

**Recommendation**: **LOW PRIORITY** - Limited differentiation from JSONL. Focus on more impactful formats first.

---

## Recommended Priority Order

Based on the evaluation criteria and Rugo's philosophy of columnar optimization:

### Tier 1 - High Value, High Priority
1. **Apache Arrow IPC / Feather** - Perfect alignment with columnar zero-copy philosophy
2. **CSV/TSV** - Huge potential impact due to ubiquity, strong SIMD optimization potential

### Tier 2 - Good Value, Medium Priority
3. **Apache ORC** - If Hadoop ecosystem users request it
4. **JSON (full arrays)** - Natural extension of JSONL work

### Tier 3 - Lower Priority
5. **Apache Avro** - Row-oriented, conflicts with columnar optimization goals
6. **MessagePack** - Limited differentiation

## Implementation Approach

If pursuing additional formats, we should:

1. **Start with Arrow IPC**: Provides maximum columnar benefit with reasonable complexity
2. **Add CSV next**: Massive user base and strong optimization potential with SIMD
3. **Evaluate user feedback**: Let real-world usage guide ORC/JSON/other format decisions

## Format Characteristics Comparison

| Format | Type | Compression | Schema | SIMD Potential | Zero-Copy | Complexity |
|--------|------|-------------|--------|---------------|-----------|------------|
| **Parquet** | Columnar | Built-in | Embedded | High | Partial | High |
| **JSONL** | Row→Col | External | Inferred | High | Limited | Medium |
| **Arrow IPC** | Columnar | Optional | Embedded | Very High | Yes | Low |
| **CSV** | Row→Col | External | Inferred | High | Partial | Medium |
| **ORC** | Columnar | Built-in | Embedded | High | Partial | High |
| **JSON** | Row→Col | External | Inferred | Medium | No | Medium |
| **Avro** | Row | Built-in | Embedded | Low | No | Medium |

## Conclusion

Rugo's strength lies in providing highly optimized columnar readers that outperform general-purpose libraries. The most promising additions are:

1. **Arrow IPC/Feather** - Natural fit, zero-copy columnar access
2. **CSV** - Ubiquitous format with huge optimization potential

Both formats would benefit from Rugo's memory-based, SIMD-optimized approach and would provide value in different scenarios than Parquet and JSONL.

ORC, JSON, and Avro are lower priorities unless specific user demand emerges.
