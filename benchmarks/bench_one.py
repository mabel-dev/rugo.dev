"""Run one (library, workload, query) measurement in a fresh process.

Prints one JSON line: best/median wall time in ms, row count, RSS after import
and peak RSS (MB). Called by measure.py; not intended for direct use.
"""
import json, resource, statistics, sys, time

lib, workload, query, path, reps = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])

def rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 1e6 if sys.platform == "darwin" else r / 1e3

# ---- JSONL / CSV: 110/50 generic columns, c000 uniform int 0..999, c001..c003 payload
PRED = {"select1": None, "select_star": None, "p10": 100, "p1": 10}
COLS = {"jsonl": ["c001"], "csv": ["c001", "c002"]}

def run_rugo_text():
    fmt = workload
    mod = __import__(f"rugo.{fmt}", fromlist=["x"])
    reader = getattr(mod, f"read_{fmt}")
    def go():
        kw = {}
        if query in ("select1",): kw["columns"] = COLS[fmt]
        if query in ("p10", "p1"):
            kw["columns"] = COLS[fmt]; kw["predicates"] = [("c000", "<", PRED[query])]
        n = 0
        with reader(path, **kw) as r:
            for m in r: n += len(m)
        return n
    return go

def run_pyarrow_text():
    import pyarrow.compute as pc
    if workload == "jsonl":
        import pyarrow.json as pj
        load = lambda cols=None: pj.read_json(path)
    else:
        import pyarrow.csv as pc_
        load = lambda cols=None: pc_.read_csv(path, convert_options=pc_.ConvertOptions(include_columns=cols))
    def go():
        if query == "select_star": return load().num_rows
        if query == "select1":
            return load(COLS[workload] if workload == "csv" else None).select(COLS[workload]).num_rows
        t = load(None if workload == "jsonl" else COLS[workload] + ["c000"])
        return t.filter(pc.less(t["c000"], PRED[query])).select(COLS[workload]).num_rows
    return go

# ---- Parquet: event_id monotonic, status 200/500/other, response_ms float
def parquet_bounds():
    return 1_000_000, 1_050_000

def run_parquet():
    lo, hi = parquet_bounds()
    shape = {"broad": (["status", "response_ms"], "status", 200),
             "selective": (["response_ms"], "status", 500),
             "pruned": (["response_ms"], None, None)}[query]
    cols, pcol, pval = shape
    if lib == "rugo":
        from rugo import parquet
        preds = [(pcol, "==", pval)] if pcol else [("event_id", ">=", lo), ("event_id", "<", hi)]
        def go():
            n = 0
            with parquet.read_parquet(path, columns=cols, predicates=preds) as r:
                for m in r:
                    m.column("response_ms").sum(); n += len(m)
            return n
    elif lib == "pyarrow":
        import pyarrow.parquet as pq
        f = [(pcol, "==", pval)] if pcol else [("event_id", ">=", lo), ("event_id", "<", hi)]
        def go():
            t = pq.read_table(path, columns=cols, filters=f)
            return t.num_rows
    elif lib == "duckdb":
        import duckdb
        w = f"{pcol} = {pval}" if pcol else f"event_id >= {lo} AND event_id < {hi}"
        con = duckdb.connect()
        def go():
            return con.execute(f"SELECT count(*), avg(response_ms) FROM read_parquet('{path}') WHERE {w}").fetchone()[0]
    elif lib == "polars":
        import polars as pl
        e = (pl.col(pcol) == pval) if pcol else ((pl.col("event_id") >= lo) & (pl.col("event_id") < hi))
        def go():
            return pl.scan_parquet(path).filter(e).select(cols).collect().height
    return go

if workload == "parquet": go = run_parquet()
elif lib == "rugo": go = run_rugo_text()
else: go = run_pyarrow_text()

after_import = rss_mb()
times, rows = [], None
for _ in range(reps):
    t = time.perf_counter(); rows = go(); times.append((time.perf_counter() - t) * 1000)
print(json.dumps({"best_ms": round(min(times), 2), "median_ms": round(statistics.median(times), 2),
                  "rows": rows, "rss_after_import_mb": round(after_import, 1), "peak_rss_mb": round(rss_mb(), 1)}))
