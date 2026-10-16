"""Run one (library, format) write measurement in a fresh process.

    python write_one.py <library> <format> <wide.csv> <reps> <tmpdir>

Prints one JSON line: best/median wall time in ms, bytes written, and the row
count read back. Called by measure_writes.py; not intended for direct use.

Every library writes the SAME table: wide.csv from gen_data.py (200,000 rows x
50 columns of ints, floats and strings), loaded into the library's own in-memory
form before the timing starts. Each writes at its own default threading;
Parquet is zstd for every writer (their defaults differ). Output goes to memory
where the library can write to a buffer; duckdb and fastparquet only write to a
path, so theirs goes to a file in <tmpdir> and the timing includes that write.

  rugo         rugo.parquet / rugo.csv / rugo.jsonl writers, from a Morsel. Parquet is
               written without rugo's bloom filters and page index (both on by
               default), so it writes what a plain Parquet writer writes
  rugo-defaults  rugo's Parquet writer at its defaults (bloom filters + page index)
  pyarrow      pyarrow.parquet.write_table / pyarrow.csv.write_csv (no JSON writer)
  polars       DataFrame.write_parquet / write_csv / write_ndjson
  duckdb       COPY ... TO (FORMAT parquet | csv | json) from an in-memory table
  fastparquet  fastparquet.write from a pandas DataFrame (Parquet only)
  python       the standard library: csv.writer / json.dumps per row, from a
               list of rows (CSV and JSONL only)
"""
import io, json, os, statistics, sys, time

lib, fmt, src, reps, tmp = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
target = os.path.join(tmp, f"out_{lib}.{fmt}")


def file_bytes():
    return open(target, "rb").read()


if lib in ("rugo", "rugo-defaults"):
    from rugo import csv as rcsv
    with rcsv.read_csv(src) as r:
        morsel = next(iter(r))
    if fmt == "parquet":
        from rugo import parquet
        if lib == "rugo":
            go = lambda: parquet.write_parquet(morsel, compression="zstd", bloom_filters=False, page_index=False)
        else:
            go = lambda: parquet.write_parquet(morsel, compression="zstd")
    elif fmt == "csv":
        go = lambda: rcsv.write_csv(morsel)
    else:
        from rugo import jsonl
        go = lambda: jsonl.write_jsonl(morsel)
elif lib == "pyarrow":
    import pyarrow.csv as pcsv
    table = pcsv.read_csv(src)
    if fmt == "parquet":
        import pyarrow as pa
        import pyarrow.parquet as pq

        def go():
            sink = pa.BufferOutputStream()
            pq.write_table(table, sink, compression="zstd")
            return sink.getvalue().to_pybytes()
    elif fmt == "csv":
        import pyarrow as pa

        def go():
            sink = pa.BufferOutputStream()
            pcsv.write_csv(table, sink)
            return sink.getvalue().to_pybytes()
    else:
        sys.exit("pyarrow has no JSON writer")
elif lib == "polars":
    import polars as pl
    df = pl.read_csv(src)

    def go():
        buf = io.BytesIO()
        {"parquet": lambda: df.write_parquet(buf, compression="zstd"),
         "csv": lambda: df.write_csv(buf),
         "jsonl": lambda: df.write_ndjson(buf)}[fmt]()
        return buf.getvalue()
elif lib == "duckdb":
    import duckdb
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t AS SELECT * FROM read_csv('{src}')")
    opts = {"parquet": "FORMAT parquet, COMPRESSION zstd", "csv": "FORMAT csv, HEADER",
            "jsonl": "FORMAT json"}[fmt]

    def go():
        con.execute(f"COPY t TO '{target}' ({opts})")
        return file_bytes()
elif lib == "fastparquet":
    import fastparquet
    import pandas as pd
    df = pd.read_csv(src)

    def go():
        fastparquet.write(target, df, compression="ZSTD")
        return file_bytes()
elif lib == "python":
    import csv
    from rugo import csv as rcsv
    with rcsv.read_csv(src) as r:  # typed rows (int / float / str), built before the timing
        morsel = next(iter(r))
    header = [n.decode() for n in morsel.column_names]
    rows = list(zip(*(morsel.column(n).to_pylist() for n in morsel.column_names)))
    if fmt == "csv":
        def go():
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(header)
            w.writerows(rows)
            return buf.getvalue().encode()
    else:
        def go():
            return "".join(json.dumps(dict(zip(header, r))) + "\n" for r in rows).encode()
else:
    sys.exit(f"unknown library {lib}")

times = []
out = b""
for _ in range(reps):
    t = time.perf_counter()
    out = go()
    times.append((time.perf_counter() - t) * 1000)

# The output must read back as every row (rugo reads all three formats).
if fmt == "parquet":
    from rugo import parquet as check
    with check.read_parquet(out) as r:
        rows_back = sum(m.num_rows for m in r)
elif fmt == "csv":
    from rugo import csv as check
    with check.read_csv(out) as r:
        rows_back = sum(m.num_rows for m in r)
else:
    rows_back = out.count(b"\n")
print(json.dumps({"best_ms": round(min(times), 1), "median_ms": round(statistics.median(times), 1),
                  "bytes": len(out), "rows": rows_back}))
