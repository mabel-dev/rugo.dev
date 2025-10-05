# rugo

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/rugo?period=total&units=INTERNATIONAL_SYSTEM&left_color=BRIGHTGREEN&right_color=LIGHTGREY&left_text=downloads)](https://pepy.tech/projects/rugo)

`rugo` is a C++17 and Cython powered Parquet metadata reader for Python. It delivers high-throughput metadata inspection without loading columnar data pages.

## Key Features
- Fast metadata extraction backed by an optimized C++17 parser and thin Python bindings.
- Complete schema and row-group details, including encodings, codecs, offsets, bloom filter pointers, and custom key/value metadata.
- Works with file paths, byte strings, and contiguous memoryviews for zero-copy parsing.
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
│   └── thrift.hpp
├── rugo/converters/orso.py
├── examples/
│   ├── comprehensive_metadata.py
│   └── orso_conversion.py
├── tests/
│   ├── data/
│   ├── test_all_metadata_fields.py
│   ├── test_logical_types.py
│   ├── test_orso_converter.py
│   └── test_statistics.py
├── Makefile
├── pyproject.toml
└── README.md
```

## Status and limitations
- Active development status (alpha); API details may evolve.
- Focused on metadata inspection; columnar data reads are out of scope.
- Requires a C++17 compiler when installing from source or editing the Cython bindings.
- Bloom filter information is exposed via offsets and lengths; higher-level helpers are planned.

## License
Licensed under the Apache License 2.0. See `LICENSE` for full terms.

## Maintainer
Created and maintained by Justin Joyce (`@joocer`). Contributions are welcome via issues and pull requests.
