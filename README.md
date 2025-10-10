# rugo

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/rugo?period=total&units=INTERNATIONAL_SYSTEM&left_color=BRIGHTGREEN&right_color=LIGHTGREY&left_text=downloads)](https://pepy.tech/projects/rugo)

`rugo` is a C++17 and Cython powered Parquet metadata reader for Python. It delivers high-throughput metadata inspection without loading columnar data pages.

## Key Features
- Fast metadata extraction backed by an optimized C++17 parser and thin Python bindings.
- Complete schema and row-group details, including encodings, codecs, offsets, bloom filter pointers, and custom key/value metadata.
- Works with file paths, byte strings, and contiguous memoryviews for zero-copy parsing.
- **Memory-based data reading** for uncompressed PLAIN-encoded columns with column selection and multi-row-group support.
- Optional schema conversion helpers for [Orso](https://github.com/mabel-dev/orso).
- No runtime dependencies beyond the Python standard library.

## Installation

### PyPI
```bash
pip install rugo

# Optional extras
pip install rugo[orso]
pip install rugo[dev]
```

### From source
```bash
git clone https://github.com/mabel-dev/rugo.git
cd rugo
python -m venv .venv
source .venv/bin/activate
make update
make compile
pip install -e .
```

### Requirements
- Python 3.9 or newer
- A C++17 compatible compiler (clang, gcc, or MSVC)
- Cython and setuptools for source builds (installed by the commands above)

## Quickstart
```python
import rugo.parquet as parquet_meta

metadata = parquet_meta.read_metadata("example.parquet")

print(f"Rows: {metadata['num_rows']}")
print("Schema columns:")
for column in metadata["schema_columns"]:
    print(f"  {column['name']}: {column['physical_type']} ({column['logical_type']})")

first_row_group = metadata["row_groups"][0]
for column in first_row_group["columns"]:
    print(
        f"{column['name']}: codec={column['compression_codec']}, "
        f"nulls={column['null_count']}, range=({column['min']}, {column['max']})"
    )
```
`read_metadata` returns dictionaries composed of Python primitives, ready for JSON serialisation or downstream processing.

## Returned metadata layout
```python
{
    "num_rows": int,
    "schema_columns": [
        {
            "name": str,
            "physical_type": str,
            "logical_type": str,
            "nullable": bool,
        },
        ...
    ],
    "row_groups": [
        {
            "num_rows": int,
            "total_byte_size": int,
            "columns": [
                {
                    "name": str,
                    "path_in_schema": str,
                    "type": str,
                    "logical_type": str,
                    "num_values": Optional[int],
                    "total_uncompressed_size": Optional[int],
                    "total_compressed_size": Optional[int],
                    "data_page_offset": Optional[int],
                    "index_page_offset": Optional[int],
                    "dictionary_page_offset": Optional[int],
                    "min": Any,
                    "max": Any,
                    "null_count": Optional[int],
                    "distinct_count": Optional[int],
                    "bloom_offset": Optional[int],
                    "bloom_length": Optional[int],
                    "encodings": List[str],
                    "compression_codec": Optional[str],
                    "key_value_metadata": Optional[Dict[str, str]],
                },
                ...
            ],
        },
        ...
    ],
}
```
Fields that are not present in the source Parquet file are reported as `None`. Minimum and maximum values are decoded into Python types when possible; otherwise hexadecimal strings are returned.

## Parsing options
All entry points share the same keyword arguments:

- `schema_only` (default `False`): return only the top-level schema without row group details.
- `include_statistics` (default `True`): skip min/max/num_values decoding when set to `False`.
- `max_row_groups` (default `-1`): limit the number of row groups inspected; handy for very large files.

```python
metadata = parquet_meta.read_metadata(
    "large_file.parquet",
    schema_only=False,
    include_statistics=False,
    max_row_groups=2,
)
```

## Working with in-memory data
```python
with open("example.parquet", "rb") as fh:
    data = fh.read()

from_bytes = parquet_meta.read_metadata_from_bytes(data)
from_view = parquet_meta.read_metadata_from_memoryview(memoryview(data))
```
`read_metadata_from_memoryview` performs zero-copy parsing when given a contiguous buffer.

## Prototype Data Decoding (Experimental)
`rugo` includes a prototype decoder for reading actual column data from Parquet files. This is a **limited, experimental feature** designed for simple use cases and testing.

### Supported Features
- ✅ Uncompressed columns only (`codec=UNCOMPRESSED`)
- ✅ PLAIN encoding only
- ✅ `int32`, `int64`, and `string` (byte_array) types only
- ✅ Memory-based processing (load once, decode multiple times)
- ✅ Column selection (decode only the columns you need)
- ✅ Multi-row-group support

### Unsupported Features  
- ❌ Compressed columns (SNAPPY, GZIP, ZSTD, etc.)
- ❌ Dictionary encoding, Delta encoding, RLE_DICTIONARY
- ❌ Other types (float, boolean, date, timestamp, complex types)
- ❌ Nullable columns (columns with definition levels)

### Primary API: Memory-Based Reading

The recommended approach loads Parquet data into memory once and performs all operations on the in-memory buffer:

```python
import rugo.parquet as rp

# Load file into memory once
with open("data.parquet", "rb") as f:
    parquet_data = f.read()

# Check if the data can be decoded
if rp.can_decode_from_memory(parquet_data):
    
    # Read ALL columns from all row groups
    table = rp.read_parquet(parquet_data)
    
    # Or read SPECIFIC columns only
    table = rp.read_parquet(parquet_data, ["name", "age", "salary"])
    
    # Access the structured data
    print(f"Columns: {table['column_names']}")
    print(f"Row groups: {len(table['row_groups'])}")
    
    # Iterate through row groups and columns
    for rg_idx, row_group in enumerate(table['row_groups']):
        print(f"Row group {rg_idx}:")
        for col_idx, column_data in enumerate(row_group):
            col_name = table['column_names'][col_idx]
            if column_data is not None:
                print(f"  {col_name}: {len(column_data)} values")
            else:
                print(f"  {col_name}: Failed to decode")
```

### Data Structure
The `read_parquet()` function returns a dictionary with this structure:
```python
{
    'success': bool,                    # True if reading succeeded
    'column_names': ['col1', 'col2'],   # List of column names
    'row_groups': [                     # List of row groups
        [col1_data, col2_data],         # Row group 0: list of columns
        [col1_data, col2_data],         # Row group 1: list of columns
        # ... more row groups
    ]
}
```
Each column's data is a Python list containing the decoded values.

### Performance Benefits

**Traditional Approach (Multiple File I/O):**
```python
# Each operation reads the file separately
metadata = rp.read_metadata("file.parquet")       # File I/O #1
col1 = rp.decode_column("file.parquet", "col1")   # File I/O #2  
col2 = rp.decode_column("file.parquet", "col2")   # File I/O #3
```

**Memory-Based Approach (Single File I/O):**
```python
# Load once, process multiple times
with open("file.parquet", "rb") as f:
    data = f.read()  # File I/O #1 (only)

table = rp.read_parquet(data, ["col1", "col2"])   # In-memory processing
```

### Legacy File-Based API
For backward compatibility, file-based functions are still available:

```python
# Check if a file can be decoded
if rp.can_decode("data.parquet"):
    # Decode a specific column from first row group only
    values = rp.decode_column("data.parquet", "column_name")
    print(values)  # e.g., [1, 2, 3, 4, 5] or ['a', 'b', 'c']
```

### Use Cases
The memory-based API is optimized for:
- **Query engines** with metadata-driven pruning
- **ETL pipelines** processing multiple Parquet files
- **Data exploration** where you need to examine various columns
- **High-performance scenarios** minimizing I/O operations

See `examples/memory_based_api_example.py` and `examples/optional_columns_example.py` for complete demonstrations.

**Note:** This decoder is a **prototype** for educational and testing purposes. For production use with full Parquet support, use [PyArrow](https://arrow.apache.org/docs/python/) or [FastParquet](https://github.com/dask/fastparquet).

## Optional Orso conversion
Install the optional extra (`pip install rugo[orso]`) to enable Orso helpers:
```python
from rugo.converters.orso import extract_schema_only, rugo_to_orso_schema

metadata = parquet_meta.read_metadata("example.parquet")
relation = rugo_to_orso_schema(metadata, "example_table")
schema_info = extract_schema_only(metadata)
```
See `examples/orso_conversion.py` for a complete walkthrough.

## Development
```bash
make update     # install build and test tooling (uses uv under the hood)
make compile    # rebuild the Cython extension with -O3 and C++17 flags
make test       # run pytest-based validation (includes PyArrow comparisons)
make lint       # run ruff, isort, pycln, cython-lint
make mypy       # type checking
```
`make compile` clears previous build artefacts before rebuilding the extension in-place.

## Project layout
```
rugo/
├── rugo/__init__.py
├── rugo/parquet/
│   ├── metadata_reader.pyx
│   ├── metadata.cpp
│   ├── metadata.hpp
│   ├── decode.cpp
│   ├── decode.hpp
│   └── thrift.hpp
├── rugo/converters/orso.py
├── examples/
│   ├── comprehensive_metadata.py
│   ├── decode_example.py
│   ├── memory_based_api_example.py
│   ├── new_decode_api_example.py
│   ├── optional_columns_example.py
│   └── orso_conversion.py
├── tests/
│   ├── data/
│   ├── test_all_metadata_fields.py
│   ├── test_decode.py
│   ├── test_logical_types.py
│   ├── test_orso_converter.py
│   └── test_statistics.py
├── Makefile
├── pyproject.toml
└── README.md
```

## Status and limitations
- Active development status (alpha); API details may evolve.
- Primary focus is metadata inspection; the data decoder is a prototype with limited capabilities but supports memory-based processing and multi-row-group reading.
- Requires a C++17 compiler when installing from source or editing the Cython bindings.
- Bloom filter information is exposed via offsets and lengths; higher-level helpers are planned.

## License
Licensed under the Apache License 2.0. See `LICENSE` for full terms.

## Maintainer
Created and maintained by Justin Joyce (`@joocer`). Contributions are welcome via issues and pull requests.
