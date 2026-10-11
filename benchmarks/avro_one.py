"""Run one (reader, shape) Avro measurement in a fresh process.

    python avro_one.py <reader> <shape> <file.avro> <reps>

Prints one JSON line: best/median wall time in ms and the row count. Called by
measure_avro.py; not intended for direct use.

Every reader decodes the same in-memory bytes; reading the file is outside the
timing.

  rugo          rugo.avro.read_avro -> columnar Morsels (no Python object per value)
  rugo+pylist   the same, then every column .to_pylist() - the cost of ending in
                Python objects, which is what the other two return
  fastavro      fastavro.reader -> one dict per record
  avro          the Apache reference implementation (avro.datafile.DataFileReader)
                -> one dict per record

Shapes: `all` reads every field; `narrow` reads id, amount and country. rugo is
given `columns`; fastavro and avro are given a reader schema of just those
fields, which is how they skip the rest.
"""
import io, json, statistics, sys, time

reader, shape, path, reps = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
NARROW = ["id", "amount", "country"]
data = open(path, "rb").read()


def narrow_schema():
    import fastavro
    schema = fastavro.reader(io.BytesIO(data)).writer_schema
    return {**schema, "fields": [f for f in schema["fields"] if f["name"] in NARROW]}


if reader in ("rugo", "rugo+pylist"):
    from rugo.avro import read_avro
    columns = NARROW if shape == "narrow" else None
    to_python = reader == "rugo+pylist"

    def go():
        n = 0
        with read_avro(data, columns=columns) as r:
            for morsel in r:
                n += morsel.num_rows
                if to_python:
                    for name in morsel.column_names:
                        morsel.column(name).to_pylist()
        return n
elif reader == "fastavro":
    import fastavro
    reader_schema = narrow_schema() if shape == "narrow" else None

    def go():
        return sum(1 for _ in fastavro.reader(io.BytesIO(data), reader_schema=reader_schema))
elif reader == "avro":
    from avro.datafile import DataFileReader
    from avro.io import DatumReader
    from avro.schema import parse
    readers_schema = parse(json.dumps(narrow_schema())) if shape == "narrow" else None

    def go():
        r = DataFileReader(io.BytesIO(data), DatumReader(readers_schema=readers_schema))
        n = sum(1 for _ in r)
        r.close()
        return n
else:
    sys.exit(f"unknown reader {reader}")

times = []
for _ in range(reps):
    t = time.perf_counter()
    rows = go()
    times.append((time.perf_counter() - t) * 1000)
print(json.dumps({"best_ms": round(min(times), 1), "median_ms": round(statistics.median(times), 1), "rows": rows}))
