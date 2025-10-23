# Format Support Roadmap

## Current Support (v0.1.x)

### Parquet ✅
- Metadata extraction (C++17 parser)
- Experimental column decoder
- Encodings: PLAIN, RLE_DICTIONARY
- Compression: UNCOMPRESSED, SNAPPY, ZSTD

### JSON Lines (JSONL) ✅
- High-performance columnar reader
- SIMD optimizations (19% faster)
- Schema inference
- Projection pushdown

---

## Planned Support

### Phase 1: Core Columnar Formats (v0.2.x - v0.3.x)

#### ORC (Optimized Row Columnar) 🎯
**Target:** v0.2.0  
**Timeline:** Q2 2026

**Rationale:**
- Natural companion to Parquet
- De facto standard for Hive/Hadoop ecosystems
- Similar optimization opportunities (predicate pushdown, stripe-level skipping)
- Can reuse compression infrastructure

**Deliverables:**
1. Metadata reader (schema, stripe statistics)
2. Basic column decoder (primitives + strings)
3. Compression support (reuse ZSTD/Snappy, add Zlib)
4. Predicate pushdown support

**Complexity:** Medium-High  
**Estimated Effort:** 8-12 weeks

---

#### CSV/TSV (Delimiter-Separated Values) 🎯
**Target:** v0.3.0  
**Timeline:** Q3 2026

**Rationale:**
- Universal data exchange format
- Excellent fit for rugo's SIMD expertise
- Performance gap vs existing readers is large
- Common first step in ETL pipelines

**Deliverables:**
1. SIMD-optimized delimiter scanning (AVX2/SSE2)
2. Schema inference with columnar output
3. Projection by column index
4. RFC 4180 compliance (quoted fields, escaping)
5. Dialect detection (delimiter, quote char)

**Complexity:** Medium  
**Estimated Effort:** 4-6 weeks

---

### Phase 2: Streaming & Exchange Formats (v0.4.x - v0.5.x)

#### Apache Avro 🔮
**Target:** v0.4.0  
**Timeline:** Q4 2026

**Rationale:**
- Industry standard for Kafka message schemas
- Growing use in streaming pipelines
- Unique opportunity: columnar extraction from row format
- Schema evolution support

**Deliverables:**
1. Schema-driven binary decoder
2. Batch decode rows → columns optimization
3. Projection pushdown (field skipping)
4. Container format support (compression, sync markers)

**Complexity:** Medium  
**Estimated Effort:** 5-7 weeks

---

#### Arrow IPC / Feather 🔮
**Target:** v0.5.0  
**Timeline:** Q1 2027

**Rationale:**
- Growing adoption in Python ecosystem
- Lightweight alternative to PyArrow for metadata
- Zero-copy opportunities
- Native format for polars

**Deliverables:**
1. Metadata extraction (schema, statistics)
2. Memory-mapped column access
3. Compression support (LZ4, ZSTD)
4. Selective column loading

**Complexity:** Medium-High  
**Estimated Effort:** 6-8 weeks

---

### Phase 3: Specialized Formats (Future)

#### MessagePack ⏳
**Target:** TBD  
**Condition:** User demand

**Rationale:**
- Binary format, more compact than JSON
- Used in messaging systems
- Lower priority due to limited analytics adoption

**Estimated Effort:** 3-4 weeks

---

## Format Selection Criteria

Formats are selected based on:

1. **Market Adoption** - Widely used in data analytics/engineering
2. **Performance Opportunity** - General readers leave room for optimization
3. **Columnar Fit** - Format amenable to columnar extraction
4. **Ecosystem Gap** - No lightweight/fast alternative exists
5. **Code Reuse** - Can leverage existing infrastructure

---

## Formats Explicitly NOT Planned

### Excel (.xlsx, .xls)
Too complex, well-served by openpyxl/xlrd

### XML
Verbose, declining usage in data pipelines

### HDF5
Scientific computing focus, not data analytics

### Protocol Buffers
RPC-focused, requires external schemas

### Database Formats (.dbf, .mdb)
Legacy, better handled by database connectors

---

## Implementation Strategy

For each new format:

1. **Start with Metadata** - Like Parquet, metadata-only reader first
2. **Basic Decoding** - Primitives + strings for 80% of use cases
3. **Leverage Infrastructure** - Reuse compression, SIMD, memory handling
4. **Maintain Philosophy** - No runtime dependencies (beyond stdlib)
5. **Incremental Rollout** - Experimental → Beta → Stable

---

## Technical Dependencies

### Compression (Already Have)
- ✅ Snappy (Parquet, future ORC)
- ✅ ZSTD (Parquet, future ORC, Arrow)
- ⚠️ Need: Zlib (ORC)
- ⚠️ Need: LZ4 (Arrow, ORC)

### Serialization (Already Have)
- ✅ Thrift (Parquet metadata)
- ⚠️ Need: Protocol Buffers (ORC metadata)
- ⚠️ Need: FlatBuffers (Arrow metadata)

### SIMD (Already Have)
- ✅ AVX2/SSE2 text scanning (JSONL)
- ✅ Can reuse for CSV, Avro
- ✅ New opportunities: Binary parsing

---

## Success Metrics

### Performance Targets
- 2-5x faster than pandas/PyArrow for target operations
- Maintain 15-20% SIMD optimization benefit
- Sub-second metadata extraction for files <1GB

### Feature Coverage
- Metadata: 100% of common fields
- Types: int32/64, float32/64, string, boolean (minimum)
- Compression: SNAPPY, ZSTD (minimum)
- Advanced: Nested types (stretch goal)

### Adoption
- PyPI downloads growth
- User feedback on format support
- Integration with Orso and other ecosystems

---

## Community Input

This roadmap is not final. We welcome feedback on:

- **Format priorities** - Which formats would benefit you most?
- **Use cases** - What specific optimizations matter for your workflows?
- **Performance targets** - What speedups would make format support valuable?

Please open GitHub issues with feature requests or comments on the roadmap.

---

## Status

- ✅ **Completed** - Fully supported
- 🎯 **Planned** - Committed for future release
- 🔮 **Proposed** - Under consideration
- ⏳ **Conditional** - Depends on user demand
- ❌ **Not Planned** - Out of scope

Last Updated: 2025-10-23
