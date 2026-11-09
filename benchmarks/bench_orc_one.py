"""Run one (library, query) ORC read in a fresh process.

    bench_orc_one.py LIB QUERY PATH REPS THREADS

The ORC twin of bench_parquet_one.py: same queries, same timing, same output line.
THREADS is "all" (each library's default) or "1". Results stay in each library's native form
(rugo Morsels, a PyArrow Table); nothing is converted to Python lists. A query the library
cannot express prints {"unsupported": reason} instead of a timing. Called by measure_orc.py.
"""
import json, os, resource, statistics, sys, time

lib, query, path, reps, threads = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
if threads == "1":
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
    import pyarrow.orc as _po
    total = _po.ORCFile(path).nrows
    pred = (pred[0], pred[1], pred[2] * total // 1_000_000)

def build():
    if lib == "rugo":
        from rugo import orc
        if query == "count":
            return lambda: orc.read_metadata(path).num_rows
        if pred:
            return None  # rugo.orc has no predicate argument
        def go():
            n = 0
            for m in orc.read_orc(path, columns=cols): n += len(m)
            return n
        return go
    if lib == "pyarrow":
        import pyarrow as pa, pyarrow.orc as orc
        pa.set_cpu_count(1) if threads == "1" else None
        if query == "count":
            return lambda: orc.ORCFile(path).nrows
        if pred:
            import pyarrow.dataset as ds
            f = {"<": lambda c, v: ds.field(c) < v}[pred[1]](pred[0], pred[2])
            d = ds.dataset(path, format="orc")
            return lambda: d.to_table(columns=cols, filter=f, use_threads=threads != "1").num_rows
        return lambda: orc.read_table(path, columns=cols).num_rows

go = build()
if go is None:
    print(json.dumps({"unsupported": "rugo.orc.read_orc has no predicate argument"}))
    sys.exit(0)
after_import = rss_mb()
times, rows = [], None
for _ in range(reps):
    t = time.perf_counter(); rows = go(); times.append((time.perf_counter() - t) * 1000)
print(json.dumps({"first_ms": round(times[0], 2), "best_ms": round(min(times), 2),
                  "median_ms": round(statistics.median(times), 2), "rows": rows,
                  "rss_after_import_mb": round(after_import, 1), "peak_rss_mb": round(rss_mb(), 1)}))
