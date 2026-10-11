"""Build docs/notebooks/*.ipynb - one Colab notebook per format (nbformat 4,
outputs left empty; Colab runs them fresh).

    python3 tools/build_notebooks.py

Each notebook installs rugo from PyPI and downloads its file from docs/data/
on GitHub, so it runs anywhere once pushed. Regenerate after editing the cells
below, then run every notebook against the published rugo before pushing.
"""
import json
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "notebooks")
DATA = "https://raw.githubusercontent.com/mabel-dev/rugo.dev/main/docs/data"
COLAB = "https://colab.research.google.com/github/mabel-dev/rugo.dev/blob/main/docs/notebooks"


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(keepends=True)}


def notebook(name, cells):
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
            "language_info": {"name": "python"},
            "colab": {"provenance": []},
        },
        "cells": cells,
    }
    for i, cell in enumerate(nb["cells"]):
        cell["id"] = f"{name}-{i:02d}"
    with open(os.path.join(OUT, f"{name}.ipynb"), "w") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")


def header(name, title, intro):
    return md(f"""
# {title}

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({COLAB}/{name}.ipynb)

{intro}

Every example uses the same dataset: 4,630 orbital launch attempts, from Sputnik onwards. More at [rugo.dev](https://rugo.dev).
""")


INSTALL = code("""
%pip install -q rugo pandas
""")


def download(filename):
    return code(f"""
import os
import urllib.request

if not os.path.exists("{filename}"):
    urllib.request.urlretrieve("{DATA}/{filename}", "{filename}")
print(f"{filename}: {{os.path.getsize('{filename}'):,}} bytes")
""")


TO_PANDAS = code("""
import pandas as pd


# Every morsel a rugo reader yields, as one pandas DataFrame.
def to_pandas(reader):
    frames = [
        pd.DataFrame({name.decode(): morsel.column(name).to_pylist() for name in morsel.column_names})
        for morsel in reader
    ]
    return pd.concat(frames, ignore_index=True)
""")

PANDAS_INTRO = md("""
## Load a file into pandas

Rugo doesn't need pandas, but it's easy to hand data over: each column's `to_pylist()` gives the values, and a dict of lists is a DataFrame. This little helper does it for every morsel a reader yields.
""")

PYTHON_VALUES = md("""
## Get Python values

A morsel holds typed columns. `column(name).to_pylist()` turns one into a Python list.
""")

# ---------------------------------------------------------------- parquet
notebook("parquet", [
    header("parquet", "How to use rugo with Parquet",
           "Read a Parquet file, look at its schema, read only the columns and rows you need, load it into pandas, and write Parquet back out - with rugo, which needs no PyArrow, pandas or NumPy of its own."),
    INSTALL,
    download("space_missions.parquet"),
    md("""
## Read a file

`read_parquet` is a context manager that yields **morsels** - batches of typed columns, one per row group.
"""),
    code("""
from rugo import parquet

with parquet.read_parquet("space_missions.parquet") as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Look at the schema without reading the data

`read_metadata` reads only the file footer: the row count and the column types.
"""),
    code("""
meta = parquet.read_metadata("space_missions.parquet")
print(meta.num_rows, "rows")
for column in meta.schema_columns:
    print(f"{column.name:16} {column.logical_type}")
"""),
    md("""
## Read only some columns

Name the columns you want; the others are never decoded.
"""),
    code("""
with parquet.read_parquet("space_missions.parquet", columns=["Company", "Mission", "Price"]) as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Filter rows as you read

`predicates` is a list of `(column, operator, value)`. Row groups that can't match are skipped using the file's statistics, then the remaining rows are filtered exactly. Operators: `== != < <= > >= in "not in"`.
"""),
    code("""
with parquet.read_parquet(
    "space_missions.parquet",
    columns=["Company", "Mission", "Price"],
    predicates=[("Company", "==", "SpaceX"), ("Price", "<", 60.0)],
) as reader:
    for morsel in reader:
        print(morsel.num_rows, "rows")
        print(morsel)
"""),
    PYTHON_VALUES,
    code("""
with parquet.read_parquet("space_missions.parquet", columns=["Mission"]) as reader:
    missions = [name for morsel in reader for name in morsel.column("Mission").to_pylist()]
print(missions[:5])
"""),
    PANDAS_INTRO,
    TO_PANDAS,
    code("""
with parquet.read_parquet("space_missions.parquet", predicates=[("Company", "==", "SpaceX")]) as reader:
    df = to_pandas(reader)

df.head()
"""),
    md("""
## Write a file

`write_parquet` turns a morsel into Parquet bytes (zstd-compressed by default).
"""),
    code("""
with parquet.read_parquet("space_missions.parquet", predicates=[("Mission_Status", "==", "Success")]) as reader:
    successes = next(iter(reader))

with open("successes.parquet", "wb") as f:
    f.write(parquet.write_parquet(successes))

print(parquet.read_metadata("successes.parquet").num_rows, "rows written")
"""),
    md("""
## Write a big file a batch at a time

`open_parquet_writer` writes one row group per `write_row_group` call and passes the bytes to your sink as it goes, so memory stays flat however large the output.
"""),
    code("""
with open("copy.parquet", "wb") as f:
    with parquet.open_parquet_writer(f.write) as writer:
        with parquet.read_parquet("space_missions.parquet") as reader:
            for morsel in reader:
                writer.write_row_group(morsel)

print(parquet.read_metadata("copy.parquet").num_rows, "rows written")
"""),
    md("""
## Convert to another format

Rugo's readers and writers share the morsel, so converting is a read and a write. Here Parquet becomes CSV.
"""),
    code("""
from rugo import csv

with parquet.read_parquet("space_missions.parquet") as reader:
    with open("space_missions.csv", "wb") as f:
        for i, morsel in enumerate(reader):
            f.write(csv.write_csv(morsel, header=(i == 0)))

print(open("space_missions.csv").readline())
"""),
])

# ---------------------------------------------------------------- csv
notebook("csv", [
    header("csv", "How to use rugo with CSV",
           "Read a CSV file, check its inferred types, read only the columns and rows you need, load it into pandas, and write CSV - with rugo, which needs no PyArrow, pandas or NumPy of its own."),
    INSTALL,
    download("space_missions.csv"),
    md("""
## Read a file

`read_csv` is a context manager that yields a **morsel** - a batch of typed columns. Column types are inferred from a sample of each column's values.
"""),
    code("""
from rugo import csv

with csv.read_csv("space_missions.csv") as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Look at the schema

`read_metadata` counts the rows and infers each column's type from the first rows. The first launches in this file have no price, so `Price` shows as text here; `read_csv` samples non-empty values instead, and reads it as a float.
"""),
    code("""
meta = csv.read_metadata("space_missions.csv")
print(meta.num_rows, "rows")
for column in meta.schema_columns:
    print(column)
"""),
    md("""
## Declare the types you know

Pass `explicit_schema` and a column is parsed straight into that type. The launch time is ISO-8601 text in the file; declare it as a timestamp.
"""),
    code("""
with csv.read_csv("space_missions.csv", explicit_schema={"Lauched_at": "TIMESTAMP[us]"}) as reader:
    morsel = next(iter(reader))

for name, kind in zip(morsel.column_names, morsel.column_types):
    print(f"{name.decode():16} {kind}")
"""),
    md("""
## Read only some columns
"""),
    code("""
with csv.read_csv("space_missions.csv", columns=["Company", "Mission", "Price"]) as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Filter rows as you read

`predicates` is a list of `(column, operator, value)`, applied as the file is parsed. The value must match the column's type - `Price` is a float, so compare it with a float.
"""),
    code("""
with csv.read_csv(
    "space_missions.csv",
    columns=["Company", "Mission", "Price"],
    predicates=[("Price", ">", 100.0)],
) as reader:
    expensive = next(iter(reader))

print(expensive.num_rows, "launches over $100M")
print(expensive)
"""),
    PYTHON_VALUES,
    code("""
print(sorted(set(expensive.column("Company").to_pylist())))
"""),
    PANDAS_INTRO,
    TO_PANDAS,
    code("""
with csv.read_csv("space_missions.csv", explicit_schema={"Lauched_at": "TIMESTAMP[us]"}) as reader:
    df = to_pandas(reader)

df.head()
"""),
    md("""
## Write a file

`write_csv` turns a morsel into RFC 4180 CSV bytes. Pass `delimiter="\\t"` for tab-separated output, and read it back the same way.
"""),
    code("""
with open("expensive.csv", "wb") as f:
    f.write(csv.write_csv(expensive))

with open("expensive.tsv", "wb") as f:
    f.write(csv.write_csv(expensive, delimiter="\\t"))

with csv.read_csv("expensive.tsv", delimiter="\\t") as reader:
    print(next(iter(reader)).num_rows, "rows read back from the TSV")
"""),
    md("""
## Convert to Parquet

Rugo's readers and writers share the morsel, so converting is a read and a write - and the Parquet file keeps the types, including the declared timestamp.
"""),
    code("""
from rugo import parquet

with csv.read_csv("space_missions.csv", explicit_schema={"Lauched_at": "TIMESTAMP[us]"}) as reader:
    with open("space_missions.parquet", "wb") as f:
        with parquet.open_parquet_writer(f.write) as writer:
            for morsel in reader:
                writer.write_row_group(morsel)

for column in parquet.read_metadata("space_missions.parquet").schema_columns:
    print(f"{column.name:16} {column.logical_type}")
"""),
])

# ---------------------------------------------------------------- jsonl
notebook("jsonl", [
    header("jsonl", "How to use rugo with JSON Lines",
           "Read a JSON Lines file (one JSON object per line), set the types you need, read only the fields and rows you need, load it into pandas, and write JSON Lines - with rugo, which needs no PyArrow, pandas or NumPy of its own."),
    INSTALL,
    download("space_missions.jsonl"),
    md("""
## Read a file

`read_jsonl` is a context manager that yields a **morsel** - a batch of typed columns. Types are inferred from the first few rows.
"""),
    code("""
from rugo import jsonl

with jsonl.read_jsonl("space_missions.jsonl") as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Look at the schema

`read_metadata` counts the lines and infers each field's type from the first few rows.
"""),
    code("""
meta = jsonl.read_metadata("space_missions.jsonl")
print(meta.num_rows, "rows")
for column in meta.schema_columns:
    print(column)
"""),
    md("""
## Declare the types you know

The first launches have no price, so a small sample sees `Price` as text. `explicit_schema` sets a field's type; the launch time is declared as a timestamp too. (`infer_sample_size=1000` would also find the float.)
"""),
    code("""
SCHEMA = {"Price": "FLOAT64", "Lauched_at": "TIMESTAMP[us]"}

with jsonl.read_jsonl("space_missions.jsonl", explicit_schema=SCHEMA) as reader:
    morsel = next(iter(reader))

for name, kind in zip(morsel.column_names, morsel.column_types):
    print(f"{name.decode():16} {kind}")
"""),
    md("""
## Read only some fields

Fields you don't name are skipped without being turned into values.
"""),
    code("""
with jsonl.read_jsonl("space_missions.jsonl", columns=["Company", "Mission"]) as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Filter rows as you read

`predicates` is a list of `(column, operator, value)`, applied as lines are read. Declare types only for the fields you read.
"""),
    code("""
with jsonl.read_jsonl(
    "space_missions.jsonl",
    columns=["Company", "Mission", "Price"],
    predicates=[("Company", "==", "SpaceX")],
    explicit_schema={"Price": "FLOAT64"},
) as reader:
    spacex = next(iter(reader))

print(spacex.num_rows, "SpaceX launches")
print(spacex)
"""),
    PYTHON_VALUES,
    code("""
prices = [p for p in spacex.column("Price").to_pylist() if p is not None]
print("cheapest", min(prices), "- most expensive", max(prices), "($M)")
"""),
    PANDAS_INTRO,
    TO_PANDAS,
    code("""
with jsonl.read_jsonl("space_missions.jsonl", explicit_schema=SCHEMA) as reader:
    df = to_pandas(reader)

df.head()
"""),
    md("""
## Write a file

`write_jsonl` turns a morsel into JSON Lines bytes.
"""),
    code("""
with open("spacex.jsonl", "wb") as f:
    f.write(jsonl.write_jsonl(spacex))

print(open("spacex.jsonl").readline())
print(jsonl.read_metadata("spacex.jsonl").num_rows, "rows written")
"""),
    md("""
## Convert to Parquet

Rugo's readers and writers share the morsel, so converting is a read and a write - with the declared types carried into the Parquet file.
"""),
    code("""
from rugo import parquet

with jsonl.read_jsonl("space_missions.jsonl", explicit_schema=SCHEMA) as reader:
    with open("space_missions.parquet", "wb") as f:
        with parquet.open_parquet_writer(f.write) as writer:
            for morsel in reader:
                writer.write_row_group(morsel)

for column in parquet.read_metadata("space_missions.parquet").schema_columns:
    print(f"{column.name:16} {column.logical_type}")
"""),
])

# ---------------------------------------------------------------- avro
notebook("avro", [
    header("avro", "How to use rugo with Avro",
           "Read an Avro file, look at its schema, read only the fields you need, filter rows, load it into pandas, and convert it to Parquet - with rugo, which needs no PyArrow, pandas or NumPy of its own. **Rugo reads Avro; it doesn't write it.**"),
    INSTALL,
    download("space_missions.avro"),
    md("""
## Read a file

`read_avro` is a context manager that yields **morsels** - batches of typed columns, made of whole Avro blocks. Logical types are decoded (the launch time arrives as a timestamp), enums arrive as their symbol, and a nested record arrives as JSON text.
"""),
    code("""
from rugo import avro

with avro.read_avro("space_missions.avro") as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Look at the schema without reading the data

An Avro file carries the schema it was written with in its header. `read_metadata` returns it, with the compression codec, without decoding a record. `["null", "double"]` is how Avro spells a nullable column; `Rocket` is a nested record.
"""),
    code("""
meta = avro.read_metadata("space_missions.avro")
print("codec:", meta.codec)
for field in meta.schema["fields"]:
    print(f"{field['name']:16} {field['type']}")
"""),
    md("""
## Read only some fields

Name the fields you want. A dotted name reads one field out of a nested record as an ordinary column.
"""),
    code("""
with avro.read_avro(
    "space_missions.avro",
    columns=["Company", "Mission", "Rocket.Name", "Rocket.Status"],
) as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Filter rows

An Avro file has no statistics a reader could use to skip records, so there's no `predicates` argument: read the fields you need and filter the values.
"""),
    code("""
with avro.read_avro("space_missions.avro", columns=["Company", "Mission", "Price"]) as reader:
    rows = [
        (company, mission, price)
        for morsel in reader
        for company, mission, price in zip(
            morsel.column("Company").to_pylist(),
            morsel.column("Mission").to_pylist(),
            morsel.column("Price").to_pylist(),
        )
        if company == "SpaceX" and price is not None and price < 60
    ]

print(len(rows), "cheap SpaceX launches")
print(rows[:3])
"""),
    md("""
## Read through a reader schema

A reader schema is the shape you want, matched against the shape the file was written with: fields it leaves out are dropped, fields the file doesn't have take their default, and numbers can widen (int to long, float to double). It's how Avro reads old and new versions of a schema together.
"""),
    code("""
reader_schema = {
    "type": "record",
    "name": "Launch",
    "fields": [
        {"name": "Mission", "type": "string"},
        {"name": "Price", "type": ["null", "double"], "default": None},
        {"name": "Source", "type": "string", "default": "space_missions"},
    ],
}

with avro.read_avro("space_missions.avro", reader_schema=reader_schema) as reader:
    for morsel in reader:
        print(morsel)
"""),
    PANDAS_INTRO,
    TO_PANDAS,
    code("""
with avro.read_avro("space_missions.avro", columns=["Company", "Mission", "Price", "Rocket.Name"]) as reader:
    df = to_pandas(reader)

df[df["Company"] == "SpaceX"].head()
"""),
    md("""
## Convert to Parquet

Rugo doesn't write Avro, but it writes Parquet, CSV and JSON Lines - and readers and writers share the morsel, so converting is a read and a write. The Avro schema's types are carried into the Parquet file.
"""),
    code("""
from rugo import parquet

with avro.read_avro("space_missions.avro") as reader:
    with open("space_missions.parquet", "wb") as f:
        with parquet.open_parquet_writer(f.write) as writer:
            for morsel in reader:
                writer.write_row_group(morsel)

for column in parquet.read_metadata("space_missions.parquet").schema_columns:
    print(f"{column.name:16} {column.logical_type}")
"""),
])
