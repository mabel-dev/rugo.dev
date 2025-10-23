# Format Support Analysis for rugo

## Executive Summary

This document analyzes additional file formats that rugo should consider supporting based on the project's core strengths: high-performance columnar data reading with custom optimizations that outperform general-purpose readers.

**Current Support:**
- ✅ **Parquet**: Custom C++17 metadata parser and experimental columnar decoder
- ✅ **JSON Lines (JSONL)**: High-performance columnar reader with SIMD optimizations (19% improvement)

**Key Selection Criteria:**
1. Widely used in data analytics and data engineering workflows
2. Columnar or semi-structured format amenable to columnar optimization
3. General-purpose readers leave performance on the table
4. Sufficient adoption to justify development effort

## Recommended Formats for Support

### 1. Apache ORC (Optimized Row Columnar) ⭐⭐⭐⭐⭐

**Priority: HIGH**

#### Overview
ORC is a self-describing, type-aware columnar file format designed for Hadoop workloads. It's widely used in the big data ecosystem, particularly with Apache Hive and Apache Spark.

#### Why rugo Should Support ORC

**Market Adoption:**
- De facto standard for Hive and many Hadoop ecosystems
- Native format for Apache Hive (2.x+)
- Well-supported in Spark, Presto, Trino, Impala
- Common in enterprise data lakes alongside Parquet

**Performance Opportunities:**
- **Predicate pushdown**: Built-in indexes (min/max, bloom filters) similar to Parquet
- **Stripe-level metadata**: Can skip entire stripes based on statistics
- **Specialized encodings**: RLE, dictionary, bit-packing - opportunities for custom decoders
- **Integrated compression**: Zlib, Snappy, LZO, LZ4, ZSTD per stripe
- **Type-specific optimizations**: Strong type system with timestamp, decimal, date types

**Why General Readers Fall Short:**
- PyORC (Python bindings to C++ ORC library) carries significant overhead
- Apache Arrow ORC reader optimized for Arrow conversion, not columnar extraction
- Many use cases only need metadata or specific columns, not full conversion

**Complexity Assessment:**
- ✅ Well-documented format specification
- ✅ Protocol Buffers for metadata (similar to Parquet's Thrift)
- ⚠️ More complex than Parquet (multiple encoding schemes)
- ✅ Can start with metadata-only reader like Parquet

**Use Cases Enabled:**
- Fast metadata inspection for query planning
- Selective column reading for ETL pipelines
- Predicate pushdown optimization
- Data lake catalog operations

**Estimated Development Effort:** Medium-High
- Metadata reader: 2-3 weeks
- Basic column decoder: 4-6 weeks
- Full format support: 8-12 weeks

---

### 2. Apache Avro ⭐⭐⭐⭐

**Priority: MEDIUM-HIGH**

#### Overview
Avro is a row-oriented data serialization format that's widely used for data exchange, particularly in streaming systems like Apache Kafka.

#### Why rugo Should Support Avro

**Market Adoption:**
- Industry standard for Kafka message schemas
- Common in data streaming pipelines
- Schema evolution support makes it popular for long-lived datasets
- Native format for many Apache projects

**Performance Opportunities:**
- **Schema-driven parsing**: Embedded schema enables optimized parsing paths
- **Binary encoding**: Compact binary format with no field delimiters
- **Projection pushdown**: Can skip unwanted fields during parsing
- **Container format**: Block-level compression and sync markers
- **Fast primitive decoding**: Fixed-width integers, direct binary representation

**Why General Readers Fall Short:**
- fastavro is Python-based with C extensions, but row-oriented
- Apache Avro official Python library is pure Python (slow)
- No readers optimize for columnar extraction from row format
- Schema parsing overhead in tight loops

**Unique Optimization Angle:**
While Avro is row-oriented, rugo could:
1. **Batch decode rows into columns** (similar to JSONL approach)
2. **Single-pass schema parsing** then type-specific fast paths
3. **SIMD-optimized field skipping** for projection pushdown
4. **Zero-copy string extraction** from binary blocks

**Complexity Assessment:**
- ✅ Relatively simple binary format
- ✅ Schema embedded in file (no external dependencies)
- ✅ Simpler encoding than Parquet/ORC
- ⚠️ Row-oriented requires different optimization strategy

**Use Cases Enabled:**
- Fast Kafka message batch processing
- Schema registry integration
- ETL from Avro sources
- Data lake ingestion optimization

**Estimated Development Effort:** Medium
- Basic row decoder: 2-3 weeks
- Columnar conversion optimization: 3-4 weeks
- Full format support: 5-7 weeks

---

### 3. CSV/TSV (Delimiter-Separated Values) ⭐⭐⭐⭐

**Priority: MEDIUM**

#### Overview
Despite being "simple" text formats, CSV/TSV remain ubiquitous in data workflows. High-performance parsing is a well-studied problem with significant room for optimization.

#### Why rugo Should Support CSV/TSV

**Market Adoption:**
- Universal format for data exchange
- Default export format for most databases and spreadsheets
- Common in data science workflows
- Often the first step in ETL pipelines

**Performance Opportunities:**
- **SIMD-optimized scanning**: Parallel search for delimiters, quotes, newlines
- **Memory-mapped parsing**: Zero-copy field extraction
- **Type inference with columnar output**: Scan once, output typed columns
- **Projection by column index**: Skip unwanted columns entirely
- **Quote handling optimization**: Fast paths for unquoted fields

**Why General Readers Fall Short:**
- pandas.read_csv is Python-heavy with some C extensions
- Python csv module is pure Python (very slow)
- PyArrow CSV reader optimized for Arrow conversion
- polars is fast but requires full library installation
- Most don't optimize for columnar extraction with type inference

**Unique Optimization Angle:**
CSV is where rugo's SIMD expertise could shine brightest:
- AVX2/SSE2 for delimiter scanning (like JSONL newline detection)
- Parallel field boundary detection
- Single-pass type inference
- Chunked processing with projection pushdown

**Complexity Assessment:**
- ⚠️ RFC 4180 has many edge cases (quoted fields, escaping)
- ⚠️ Dialect detection (delimiter, quote char, line endings)
- ✅ Well-understood problem space
- ✅ Can start with simple case, add complexity incrementally

**Use Cases Enabled:**
- Data science notebook performance
- ETL pipeline optimization
- Database export processing
- Log file parsing (TSV variant)

**Estimated Development Effort:** Medium
- Basic parser: 2-3 weeks
- SIMD optimization: 2-3 weeks
- Full RFC 4180 support: 4-6 weeks

---

### 4. Apache Arrow IPC / Feather ⭐⭐⭐

**Priority: LOW-MEDIUM**

#### Overview
Arrow IPC (Inter-Process Communication) format, also known as Feather v2, is a language-agnostic columnar memory format designed for efficient data exchange.

#### Why rugo Might Support Arrow IPC

**Market Adoption:**
- Growing adoption in Python data ecosystem
- Native format for polars
- Efficient data exchange between processes/languages
- Increasingly common in ML pipelines

**Performance Opportunities:**
- **Already columnar**: Data is laid out in memory-ready format
- **Zero-copy reading**: Direct memory mapping possible
- **Metadata scanning**: Fast schema and statistics extraction
- **Compression per column**: LZ4, ZSTD support built-in

**Why General Readers Fall Short:**
- PyArrow is comprehensive but heavyweight dependency
- Loading PyArrow just to read metadata is overkill
- No lightweight metadata-only reader exists

**Unique Optimization Angle:**
- **Lightweight metadata extraction** without PyArrow
- **Memory-mapped direct access** to compressed chunks
- **Selective column loading** with minimal overhead
- Could be complementary to Parquet reader

**Complexity Assessment:**
- ✅ Well-specified format
- ✅ FlatBuffers for metadata (similar complexity to Protobuf/Thrift)
- ⚠️ Complex memory layout for nested types
- ✅ Can start with flat schemas only

**Use Cases Enabled:**
- Fast metadata inspection for Arrow files
- Lightweight column extraction without PyArrow
- IPC format optimization for data pipelines

**Estimated Development Effort:** Medium-High
- Metadata reader: 2-3 weeks
- Column decoder: 4-5 weeks
- Full nested type support: 8-10 weeks

---

### 5. NDJSON (Newline-Delimited JSON) ⭐⭐⭐⭐⭐

**Priority: ALREADY SUPPORTED (as JSONL)**

**Note:** NDJSON is synonymous with JSONL (JSON Lines), which rugo already supports with high performance. This format is included for completeness.

---

### 6. MessagePack ⭐⭐

**Priority: LOW**

#### Overview
MessagePack is a binary serialization format that's more compact than JSON but maintains similar simplicity.

#### Why rugo Might Consider MessagePack

**Market Adoption:**
- Used in some messaging systems
- Popular in gaming and real-time applications
- Supported by Redis, Fluentd

**Performance Opportunities:**
- **Binary format**: More efficient than JSON parsing
- **Type markers**: Built-in type information
- **Compact encoding**: Smaller than JSON

**Why Priority is Low:**
- Less adoption in data analytics space
- Primarily used for point-to-point messaging, not batch data
- Row-oriented like Avro but less standardized
- Limited use in data lakes/warehouses

**Estimated Development Effort:** Low-Medium (3-4 weeks)

---

### 7. Protocol Buffers ⭐⭐

**Priority: LOW**

#### Overview
Google's language-neutral serialization format, widely used in microservices but less common in analytics.

#### Why Priority is Low for Analytics:
- Requires external schema definitions (.proto files)
- Primarily used for RPC, not batch data processing
- Not designed for columnar access patterns
- Limited adoption in data lake/warehouse scenarios

However, Protocol Buffers knowledge is valuable as:
- ORC uses Protobuf for metadata
- Many internal Google systems use Protobuf
- Could enable integration with specific enterprise systems

---

## Formats NOT Recommended

### Excel Files (.xlsx, .xls)
**Reason:** Extremely complex format designed for spreadsheet software, not data processing. Better handled by specialized libraries like openpyxl or xlrd. Little opportunity for optimization beyond what these libraries provide.

### XML
**Reason:** Verbose, complex parsing, poor performance characteristics. Not commonly used for bulk data storage in modern data pipelines. Better alternatives exist for all XML use cases.

### HDF5
**Reason:** Primarily used in scientific computing (not data analytics). Complex format with C library dependency. Limited adoption in cloud/data lake environments. PyTables handles this well.

### Database-Specific Formats (e.g., .dbf, .mdb)
**Reason:** Legacy formats with declining usage. Better to read via database connectors or convert to modern formats.

---

## Recommended Implementation Priority

### Phase 1: Core Columnar Formats (Next 6 months)
1. **ORC** - Complements Parquet for Hive ecosystems
2. **CSV/TSV** - Universal format, SIMD opportunities align with rugo strengths

### Phase 2: Streaming & Exchange Formats (6-12 months)
3. **Avro** - Kafka/streaming integration
4. **Arrow IPC** - Modern data exchange

### Phase 3: Specialized Formats (12+ months)
5. **MessagePack** - If specific user demand emerges

---

## Technical Considerations

### Shared Infrastructure Opportunities

**Compression Libraries:**
- Already have: Snappy, ZSTD
- Would need: Zlib (ORC), LZ4 (Arrow, ORC)

**Serialization Libraries:**
- Already have: Thrift (Parquet)
- Would need: Protocol Buffers (ORC), FlatBuffers (Arrow)

**SIMD Optimizations:**
- Already have: AVX2/SSE2 text scanning
- Can reuse for: CSV, Avro field skipping
- New opportunities: Binary format parsing (MessagePack, Avro)

### Code Reuse Potential

**From Parquet implementation:**
- Compression infrastructure → ORC, Arrow
- Metadata extraction patterns → ORC, Arrow
- Column-oriented decoding → All formats
- Memory-based processing → All formats

**From JSONL implementation:**
- SIMD text scanning → CSV
- Type inference → CSV, Avro
- Projection pushdown → Avro, CSV
- Columnar assembly from rows → Avro

---

## Competitive Analysis

### Current Ecosystem Gaps

**ORC:**
- PyORC: C++ bindings, heavyweight
- PyArrow: Full dependency just for ORC
- **Gap:** Lightweight metadata + selective reading

**CSV:**
- pandas: Python-heavy
- PyArrow: Optimized for Arrow conversion
- polars: Excellent but requires full install
- **Gap:** SIMD-optimized columnar CSV with minimal dependencies

**Avro:**
- fastavro: Fast but row-oriented
- Apache Avro: Pure Python (slow)
- **Gap:** Columnar extraction from Avro files

**Arrow IPC:**
- PyArrow: Only option, heavyweight
- **Gap:** Lightweight metadata/selective reading

---

## Success Metrics

For each new format, success would be measured by:

1. **Performance vs General Readers:**
   - 2-5x faster than pandas/PyArrow for target use cases
   - Maintain current SIMD optimization benefits (15-20% improvement)

2. **Feature Completeness:**
   - Metadata extraction (100% coverage)
   - Basic type support (int, float, string, bool)
   - Compression support (Snappy, ZSTD minimum)
   - Projection pushdown

3. **Adoption Indicators:**
   - PyPI download growth
   - GitHub stars/issues
   - User feedback on format support

---

## Conclusion

**Strongest Candidates:**

1. **ORC** - Natural companion to Parquet, significant market need
2. **CSV/TSV** - Universal format where SIMD optimization excels
3. **Avro** - Streaming/Kafka integration opportunity

**Implementation Strategy:**

- Start with **metadata-only readers** (like Parquet)
- Add **basic column decoding** for common types
- Leverage **existing compression infrastructure**
- Apply **SIMD optimizations** where applicable
- Maintain **no runtime dependencies** philosophy

**Key Differentiator:**

rugo should focus on formats where:
- General-purpose readers are suboptimal for columnar extraction
- SIMD/C++17 optimizations provide clear advantage
- Metadata operations are useful on their own
- The format is widely used in data analytics workflows

This strategy aligns with rugo's core mission: delivering specialized, high-performance readers that outperform general-purpose alternatives through targeted optimization.
