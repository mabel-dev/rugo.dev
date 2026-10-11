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
%pip install -q rugo
""")


def download(filename):
    return code(f"""
import os
import urllib.request

if not os.path.exists("{filename}"):
    urllib.request.urlretrieve("{DATA}/{filename}", "{filename}")
print(f"{filename}: {{os.path.getsize('{filename}'):,}} bytes")
""")


PYTHON_VALUES = md("""
## Get Python values

A morsel holds typed columns. `column(name).to_pylist()` turns one into a Python list - only do this for the columns you need, since it's the step that creates a Python object per value.
""")

# ---------------------------------------------------------------- parquet
notebook("parquet", [
    header("parquet", "Read and write Parquet with rugo",
           "Rugo reads and writes Parquet with no PyArrow, pandas or NumPy. This notebook reads a file's schema without decoding it, reads only the columns and rows you ask for, and writes Parquet back out."),
    INSTALL,
    download("space_missions.parquet"),
    md("""
## Read the schema, not the data

`read_metadata` reads the file footer only - the row count and column types, with no column decoded.
"""),
    code("""
from rugo import parquet

meta = parquet.read_metadata("space_missions.parquet")
print(meta.num_rows, "rows in", meta.num_row_groups, "row group(s)")
for column in meta.schema_columns:
    print(f"{column.name:16} {column.logical_type:14} nullable={column.nullable}")
"""),
    md("""
## Read the whole file

`read_parquet` is a context manager that yields one **morsel** - a batch of typed columns - per row group.
"""),
    code("""
with parquet.read_parquet("space_missions.parquet") as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Read only what you need

`columns` picks the columns; `predicates` filters rows. Row groups whose statistics show they can't match are skipped before they're decoded, then the surviving rows are filtered exactly.
"""),
    code("""
with parquet.read_parquet(
    "space_missions.parquet",
    columns=["Company", "Mission", "Price"],
    predicates=[("Company", "==", "SpaceX"), ("Price", "<", 60.0)],
) as reader:
    spacex = next(iter(reader))

print(spacex.num_rows, "cheap SpaceX launches")
print(spacex)
"""),
    PYTHON_VALUES,
    code("""
missions = spacex.column("Mission").to_pylist()
prices = spacex.column("Price").to_pylist()
print(missions[:5])
print("average price:", round(sum(prices) / len(prices), 2), "($M)")
"""),
    md("""
## Write Parquet

`write_parquet` turns a morsel into Parquet bytes (zstd-compressed by default). Read it back to check it round-trips.
"""),
    code("""
data = parquet.write_parquet(spacex)
with open("spacex.parquet", "wb") as f:
    f.write(data)

print(len(data), "bytes;", parquet.read_metadata("spacex.parquet").num_rows, "rows read back")
"""),
    md("""
## Stream batches at constant memory

`open_parquet_writer` writes one row group per call to `write_row_group`, passing bytes to your sink as it goes, so a large conversion never holds the whole file in memory.
"""),
    code("""
with open("successes.parquet", "wb") as f:
    with parquet.open_parquet_writer(f.write) as writer:
        with parquet.read_parquet(
            "space_missions.parquet", predicates=[("Mission_Status", "==", "Success")]
        ) as reader:
            for morsel in reader:
                writer.write_row_group(morsel)

print(parquet.read_metadata("successes.parquet").num_rows, "successful launches written")
"""),
])

# ---------------------------------------------------------------- csv
notebook("csv", [
    header("csv", "Read and write CSV with rugo",
           "Rugo reads and writes CSV with no PyArrow, pandas or NumPy. Column types are inferred from a sample, or declared up front; columns and rows you don't ask for are dropped as the file is parsed."),
    INSTALL,
    download("space_missions.csv"),
    md("""
## Read the schema

`read_metadata` counts the rows and infers each column's type from the first rows. The first launches in this file have no price, so `Price` shows as text here; `read_csv` samples non-empty values instead, and reads it as a float.
"""),
    code("""
from rugo import csv

meta = csv.read_metadata("space_missions.csv")
print(meta.num_rows, "rows")
for column in meta.schema_columns:
    print(column)
"""),
    md("""
## Read the whole file

`read_csv` is a context manager that yields a **morsel** - a batch of typed columns.
"""),
    code("""
with csv.read_csv("space_missions.csv") as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Declare types you already know

Inference picks numbers and text. The launch time is ISO-8601 text in the file; declare it with `explicit_schema` and it's parsed straight into a timestamp.
"""),
    code("""
with csv.read_csv("space_missions.csv", explicit_schema={"Lauched_at": "TIMESTAMP[us]"}) as reader:
    morsel = next(iter(reader))

for name, kind in zip(morsel.column_names, morsel.column_types):
    print(f"{name.decode():16} {kind}")
"""),
    md("""
## Read only what you need

`columns` picks the columns; `predicates` filters rows as they're parsed. A predicate value must match the column's type - `Price` is a float, so compare it with a float.
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
companies = expensive.column("Company").to_pylist()
print(sorted(set(companies)))
"""),
    md("""
## Write CSV

`write_csv` turns a morsel into RFC 4180 CSV bytes. Pass `delimiter="\\t"` for TSV, and read it back the same way.
"""),
    code("""
with open("expensive.tsv", "wb") as f:
    f.write(csv.write_csv(expensive, delimiter="\\t"))

with csv.read_csv("expensive.tsv", delimiter="\\t") as reader:
    print(next(iter(reader)).num_rows, "rows read back from the TSV")
"""),
])

# ---------------------------------------------------------------- jsonl
notebook("jsonl", [
    header("jsonl", "Read and write JSON Lines with rugo",
           "Rugo reads and writes JSON Lines (one JSON object per line) with no PyArrow, pandas or NumPy. Fields you don't ask for are skipped without being parsed into values, and rows are filtered as they're read."),
    INSTALL,
    download("space_missions.jsonl"),
    md("""
## Read the schema

`read_metadata` counts the lines and infers each field's type from the first few rows - which, as the next step shows, isn't always enough.
"""),
    code("""
from rugo import jsonl

meta = jsonl.read_metadata("space_missions.jsonl")
print(meta.num_rows, "rows")
for column in meta.schema_columns:
    print(column)
"""),
    md("""
## Declare types inference can't see

Types are inferred from a small sample - here the first launches have no price, so `Price` looks like text. `explicit_schema` declares a field's type; the launch time is declared as a timestamp too.
"""),
    code("""
SCHEMA = {"Price": "FLOAT64", "Lauched_at": "TIMESTAMP[us]"}

with jsonl.read_jsonl("space_missions.jsonl", explicit_schema=SCHEMA) as reader:
    morsel = next(iter(reader))

for name, kind in zip(morsel.column_names, morsel.column_types):
    print(f"{name.decode():16} {kind}")
print(morsel)
"""),
    md("""
## Read only what you need

`columns` picks fields; `predicates` filters rows as they're read. Declare types only for the fields you read.
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
print(len(prices), "with a price; cheapest", min(prices), "most expensive", max(prices), "($M)")
"""),
    md("""
## Write JSON Lines

`write_jsonl` turns a morsel into JSON Lines bytes. Read it back to check it round-trips.
"""),
    code("""
with open("spacex.jsonl", "wb") as f:
    f.write(jsonl.write_jsonl(spacex))

print(open("spacex.jsonl").readline())
print(jsonl.read_metadata("spacex.jsonl").num_rows, "rows read back")
"""),
])

# ---------------------------------------------------------------- avro
notebook("avro", [
    header("avro", "Read Avro with rugo",
           "Rugo **reads** Avro object container files - the format Kafka sinks, Hadoop-era data lakes and Iceberg manifests are written in - with no PyArrow, pandas or NumPy. **It doesn't write Avro**: it's a reader only. The last section times it against fastavro and the Apache `avro` package."),
    INSTALL,
    download("space_missions.avro"),
    md("""
## Read the schema, not the data

An Avro file carries its writer schema in its header. `read_metadata` returns it, with the codec, without decoding a record.
"""),
    code("""
from rugo import avro

meta = avro.read_metadata("space_missions.avro")
print("codec:", meta.codec)
for field in meta.schema["fields"]:
    print(f"{field['name']:16} {field['type']}")
"""),
    md("""
`["null", "double"]` is how Avro spells a nullable column. `Rocket` is a nested record holding a name and an enum.

## Read the whole file

`read_avro` is a context manager that yields **morsels** - batches of typed columns, made of whole Avro blocks. Logical types are decoded (the launch time arrives as a timestamp), enums arrive as their symbol, and a nested record arrives as JSON text.
"""),
    code("""
with avro.read_avro("space_missions.avro") as reader:
    for morsel in reader:
        print(morsel)
"""),
    md("""
## Read only the fields you need

`columns` picks fields. A dotted name reads one field out of a nested record as an ordinary column. Avro has no statistics, so there's no `predicates` argument - filter the morsel's values instead.
"""),
    code("""
with avro.read_avro(
    "space_missions.avro",
    columns=["Company", "Mission", "Rocket.Name", "Rocket.Status"],
) as reader:
    morsel = next(iter(reader))

print(morsel)
active = [name for name, status in zip(morsel.column("Rocket.Name").to_pylist(),
                                       morsel.column("Rocket.Status").to_pylist())
          if status == "Active"]
print(len(set(active)), "rockets still active")
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
    print(next(iter(reader)))
"""),
    md("""
## Compare with fastavro and the Apache `avro` package

Rugo doesn't write Avro, so fastavro writes a 100,000-row test file: 20 fields, deflate-compressed, in the mix of an event stream. Each reader then reads it twice - every field, and just 3 fields (rugo is given `columns`; the others are given a reader schema of those fields, which is how they skip the rest).

rugo returns typed columns, while fastavro and `avro` return a Python dict per record, so rugo is also timed with every column converted to Python values (`rugo+pylist`) - the fair comparison if you want Python objects at the end.
"""),
    code("""
%pip install -q fastavro avro
"""),
    code("""
import datetime, decimal, io, random
import fastavro

WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
schema = {"type": "record", "name": "Event", "fields": [
    {"name": "id", "type": "long"}, {"name": "user_id", "type": "long"},
    {"name": "small", "type": "int"}, {"name": "amount", "type": "double"},
    {"name": "ratio", "type": "float"}, {"name": "flag", "type": "boolean"},
    {"name": "event", "type": "string"},
    {"name": "country", "type": {"type": "enum", "name": "Country", "symbols": ["AU", "DE", "GB", "JP", "US"]}},
    {"name": "name", "type": "string"}, {"name": "url", "type": "string"},
    {"name": "note", "type": ["null", "string"]}, {"name": "score", "type": ["double", "null"]},
    {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-micros"}},
    {"name": "event_date", "type": {"type": "int", "logicalType": "date"}},
    {"name": "price", "type": {"type": "bytes", "logicalType": "decimal", "precision": 12, "scale": 2}},
    {"name": "session", "type": {"type": "fixed", "name": "Session", "size": 16}},
    {"name": "counter", "type": ["null", "long"]},
    {"name": "device", "type": {"type": "record", "name": "Device", "fields": [
        {"name": "os", "type": "string"}, {"name": "model", "type": ["null", "string"]}]}},
    {"name": "tags", "type": {"type": "array", "items": "string"}},
    {"name": "metrics", "type": {"type": "map", "values": "double"}},
]}

def records(n, rnd=random.Random(42)):
    start = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    for i in range(n):
        yield {"id": i, "user_id": rnd.randrange(5_000_000), "small": rnd.randrange(-1000, 1000),
               "amount": rnd.uniform(0, 10_000), "ratio": rnd.random(), "flag": rnd.random() < 0.3,
               "event": rnd.choice(["click", "view", "purchase"]),
               "country": rnd.choice(["AU", "DE", "GB", "JP", "US"]),
               "name": " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(1, 4))),
               "url": f"https://example.com/{rnd.choice(WORDS)}/{rnd.randrange(1_000_000)}",
               "note": None if rnd.random() < 0.7 else rnd.choice(WORDS),
               "score": None if rnd.random() < 0.1 else rnd.gauss(50, 15),
               "created_at": start + datetime.timedelta(seconds=i),
               "event_date": start.date() + datetime.timedelta(days=rnd.randrange(365)),
               "price": decimal.Decimal(rnd.randrange(-10_000_000, 100_000_000)).scaleb(-2),
               "session": rnd.randbytes(16), "counter": None if rnd.random() < 0.5 else rnd.randrange(1 << 40),
               "device": {"os": rnd.choice(["ios", "android"]), "model": None if rnd.random() < 0.2 else "m1"},
               "tags": [rnd.choice(WORDS) for _ in range(rnd.randint(0, 3))],
               "metrics": {rnd.choice(WORDS): rnd.random() for _ in range(rnd.randint(0, 3))}}

buffer = io.BytesIO()
fastavro.writer(buffer, fastavro.parse_schema(schema), records(100_000), codec="deflate", sync_interval=64_000)
data = buffer.getvalue()
print(f"{len(data):,} bytes")
"""),
    code("""
import json, time
from avro.datafile import DataFileReader
from avro.io import DatumReader
from avro.schema import parse

NARROW = ["id", "amount", "country"]
narrow_schema = {**schema, "fields": [f for f in schema["fields"] if f["name"] in NARROW]}

def rugo_read(columns, to_python=False):
    with avro.read_avro(data, columns=columns) as reader:
        for morsel in reader:
            if to_python:
                for name in morsel.column_names:
                    morsel.column(name).to_pylist()

def fastavro_read(columns):
    for _ in fastavro.reader(io.BytesIO(data), reader_schema=narrow_schema if columns else None):
        pass

def apache_read(columns):
    readers_schema = parse(json.dumps(narrow_schema)) if columns else None
    for _ in DataFileReader(io.BytesIO(data), DatumReader(readers_schema=readers_schema)):
        pass

readers = {
    "rugo": lambda c: rugo_read(c),
    "rugo+pylist": lambda c: rugo_read(c, to_python=True),
    "fastavro": fastavro_read,
    "avro (Apache)": apache_read,
}

def best_of(fn, columns, runs):
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn(columns)
        times.append(time.perf_counter() - start)
    return min(times)

for label, columns in (("every field", None), ("3 fields", NARROW)):
    print(label)
    base = best_of(readers["rugo"], columns, 3)
    for name, fn in readers.items():
        seconds = base if name == "rugo" else best_of(fn, columns, 1 if name.startswith("avro") else 3)
        print(f"  {name:14} {seconds * 1000:9.1f} ms   {seconds / base:6.1f}x rugo")
"""),
    md("""
Timings depend on the machine - on Colab you share one with other notebooks, so expect some noise. The published comparison, measured on a quiet machine with a script you can run yourself, is at [rugo.dev](https://rugo.dev/#performance).
"""),
])
