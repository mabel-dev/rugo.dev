"""Run one (library, query) Parquet read in a fresh process.

    bench_parquet_one.py LIB QUERY PATH REPS THREADS

THREADS is "all" (each library's default) or "1". Results stay in each library's native form
(rugo Morsels, a PyArrow Table, a Polars DataFrame, a DuckDB result fetched as an Arrow table);
nothing is converted to Python lists. Prints one JSON line. Called by measure_parquet.py.
"""
import inspect, json, os, resource, statistics, sys, time

lib, query, path, reps, threads = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
if threads == "1":
    os.environ["POLARS_MAX_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"

def rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3

# query -> (projected columns, (column, op, value) or None). `id` is the sort column, `k` is not.
Q = {"select2":      (["a", "b"], None),
     "unsorted_p10": (["a", "b"], ("k", "<", 100)),
     "unsorted_p1":  (["a", "b"], ("k", "<", 10)),
     "sorted_p10":   (["a", "b"], ("id", "<", 100_000)),
     "sorted_p1":    (["a", "b"], ("id", "<", 10_000)),
     "full":         (None, None),
     "count":        ([], None)}
cols, pred = Q[query]
# the p10/p1 literals above assume 1M rows; scale the sorted bound if the file is smaller
if pred and pred[0] == "id":
    import rugo.parquet as _rp
    total = _rp.read_metadata(path).num_rows
    pred = (pred[0], pred[1], pred[2] * total // 1_000_000)

def build():
    if lib == "rugo":
        from rugo import parquet
        if query == "count":
            return lambda: parquet.read_metadata(path).num_rows
        def go():
            n = 0
            kw = {"columns": cols} if cols else {}
            if pred: kw["predicates"] = [pred]
            # rugo >= the multi-core reader takes threads=; older wheels are serial anyway
            if threads == "1" and "threads" in inspect.signature(parquet.read_parquet).parameters: kw["threads"] = 1
            with parquet.read_parquet(path, **kw) as r:
                for m in r: n += len(m)
            return n
        return go
    if lib == "pyarrow":
        import pyarrow as pa, pyarrow.parquet as pq
        pa.set_cpu_count(1) if threads == "1" else None
        if query == "count":
            return lambda: pq.ParquetFile(path).metadata.num_rows
        f = [pred] if pred else None
        return lambda: pq.read_table(path, columns=cols, filters=f, use_threads=threads != "1").num_rows
    if lib == "duckdb":
        import duckdb
        con = duckdb.connect()
        if threads == "1": con.execute("SET threads=1")
        where = f"WHERE {pred[0]} {pred[1]} {pred[2]}" if pred else ""
        sel = "count(*)" if query == "count" else ", ".join(cols) if cols else "*"
        sql = f"SELECT {sel} FROM read_parquet('{path}') {where}"
        if query == "count": return lambda: con.execute(sql).fetchone()[0]
        return lambda: con.execute(sql).to_arrow_table().num_rows
    if lib == "polars":
        import polars as pl
        if query == "count": return lambda: pl.scan_parquet(path).select(pl.len()).collect().item()
        e = {"<": lambda c, v: pl.col(c) < v}[pred[1]](pred[0], pred[2]) if pred else None
        def go():
            q = pl.scan_parquet(path)
            if e is not None: q = q.filter(e)
            if cols: q = q.select(cols)
            return q.collect().height
        return go

go = build()
after_import = rss_mb()
times, rows = [], None
for _ in range(reps):
    t = time.perf_counter(); rows = go(); times.append((time.perf_counter() - t) * 1000)
print(json.dumps({"first_ms": round(times[0], 2), "best_ms": round(min(times), 2),
                  "median_ms": round(statistics.median(times), 2), "rows": rows,
                  "rss_after_import_mb": round(after_import, 1), "peak_rss_mb": round(rss_mb(), 1)}))
