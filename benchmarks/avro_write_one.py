"""Run one (writer, codec) Avro write measurement in a fresh process.

    python avro_write_one.py <writer> <codec> <rugo_file.avro> <reps>

Prints one JSON line: best/median wall time in ms, the bytes written, and the row
count read back. Called by measure_avro_write.py; not intended for direct use.

Every writer writes the SAME rows with the SAME schema: the file rugo wrote from the
comparison data (measure_avro_write.py), read back here outside the timing into each
library's own input form. Output goes to an in-memory buffer; file IO is outside the
timing.

  rugo          rugo.avro.write_avro(morsel) on every core (its default)
  rugo-1t       the same, max_threads=1
  fastavro      fastavro.writer(buffer, schema, records) - one dict per record
  avro          the Apache reference implementation (avro.datafile.DataFileWriter)
                - one dict per record

rugo starts from a Morsel (columns, as its readers return them); fastavro and avro
start from a list of dicts, which is their input. Building either input is not timed.
Each library cuts blocks at its own default size (rugo 1 MiB of encoded rows,
fastavro 16,000 bytes, avro 64,000 bytes).
"""
import io, json, statistics, sys, time

writer, codec, path, reps = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
data = open(path, "rb").read()

if writer in ("rugo", "rugo-1t"):
    from draken.morsels.morsel import Morsel
    from rugo import avro

    with avro.read_avro(data) as r:
        morsel = Morsel.combine(list(r))
    threads = 1 if writer == "rugo-1t" else 0

    def go():
        return avro.write_avro(morsel, codec=codec, record_name="Event", max_threads=threads)
elif writer == "fastavro":
    import fastavro

    reader = fastavro.reader(io.BytesIO(data))
    schema = fastavro.parse_schema(reader.writer_schema)
    records = list(reader)

    def go():
        buf = io.BytesIO()
        fastavro.writer(buf, schema, records, codec=codec)
        return buf.getvalue()
elif writer == "avro":
    import fastavro
    from avro.datafile import DataFileWriter
    from avro.io import DatumWriter
    from avro.schema import parse

    reader = fastavro.reader(io.BytesIO(data))
    schema = parse(json.dumps(reader.writer_schema))
    records = list(reader)

    def go():
        buf = io.BytesIO()
        w = DataFileWriter(buf, DatumWriter(), schema, codec=codec)
        for record in records:
            w.append(record)
        w.flush()
        return buf.getvalue()
else:
    sys.exit(f"unknown writer {writer}")

times = []
out = b""
for _ in range(reps):
    t = time.perf_counter()
    out = go()
    times.append((time.perf_counter() - t) * 1000)

# Every output must read back as the same number of rows (rugo reads all three).
from rugo import avro as _check
with _check.read_avro(out, columns=[]) as r:
    rows = sum(m.num_rows for m in r)
print(json.dumps({"best_ms": round(min(times), 1), "median_ms": round(statistics.median(times), 1),
                  "bytes": len(out), "rows": rows}))
