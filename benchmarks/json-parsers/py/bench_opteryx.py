"""Opteryx driver: each workload as the SQL a user would write, over the raw NDJSON files.

    python bench_opteryx.py --workload W --source GLOB [--repeat R] [--count]

READ_JSONL(..., ignore_errors => true) skips malformed lines, as the C++ drivers do.
Timed: execute_to_morsels() fully drained, so the result exists as columnar morsels — the
point at which a query engine has "answered". Import, session creation and the Python
conversion used for the result digest are not timed.

Worker count is MAX_EXECUTION_WORKERS (set by run.sh; Opteryx's own default is 80% of
cores). Every run is a new session in the same process. Run 0 is the warm-up; the report
drops it, as it does for every driver. Opteryx caches no JSONL data or results between
queries.
"""
import argparse
import glob
import json
import os
import sys
import time
import zlib

import opteryx

ap = argparse.ArgumentParser()
ap.add_argument("--workload", required=True)
ap.add_argument("--source", required=True, help="glob of .jsonl files")
ap.add_argument("--repeat", type=int, default=1)
ap.add_argument("--count", action="store_true", help="also report docs read (untimed COUNT(*))")
a = ap.parse_args()

T = f"READ_JSONL('{a.source}', ignore_errors => true)"
COLL = "commit->>'collection'"
SQL = {
    "filter_hi": f"SELECT did FROM {T} WHERE {COLL} = 'app.bsky.feed.like'",
    "filter_lo": f"SELECT did FROM {T} WHERE {COLL} = 'app.bsky.graph.block'",
    "minmax": f"SELECT MIN(time_us), MAX(time_us) FROM {T}",
    "freq_lo": f"SELECT {COLL} AS k, COUNT(*) FROM {T} GROUP BY k",
    "freq_hi": f"SELECT did, COUNT(*) FROM {T} GROUP BY did",
    "filter_agg": f"SELECT {COLL} AS k, COUNT(*) FROM {T} "
                  f"WHERE kind = 'commit' AND commit->>'operation' = 'create' GROUP BY k",
    "deep": f"SELECT COUNT(*) FROM {T} WHERE commit->'record'->'reply'->'parent'->>'uri' IS NOT NULL",
    "langs": f"SELECT lang, COUNT(*) FROM {T} "
             f"CROSS JOIN UNNEST(CAST(commit->'record'->'langs' AS ARRAY<VARCHAR>)) AS lang GROUP BY lang",
}
if a.workload not in SQL:
    sys.exit(f"opteryx: no SQL for workload {a.workload!r}")

files = sorted(glob.glob(a.source))
nbytes = sum(os.path.getsize(f) for f in files)


def run():
    morsels = []
    t0 = time.perf_counter()
    for m in opteryx.session().execute_to_morsels(SQL[a.workload]):
        morsels.append(m)
    return time.perf_counter() - t0, morsels


def columns(morsels):
    cols = None
    for m in morsels:
        vals = [m.column(c).to_pylist() for c in m.column_names]
        if cols is None:
            cols = vals
        else:
            for c, v in zip(cols, vals):
                c.extend(v)
    return cols or []


def text(v):
    return v.decode() if isinstance(v, (bytes, bytearray)) else v


def digest(morsels):
    cols = columns(morsels)
    w = a.workload
    if w in ("filter_hi", "filter_lo"):
        dids = cols[0] if cols else []
        nulls = sum(1 for d in dids if d is None)
        h = sum(zlib.crc32(text(d).encode()) for d in dids if d is not None) % 2**64
        return {"rows": len(dids), "nulls": nulls, "hash": h}
    if w == "minmax":
        return {"min": cols[0][0], "max": cols[1][0]}
    if w in ("freq_lo", "filter_agg", "langs"):
        return {"groups": [[None if k is None else text(k), n] for k, n in zip(cols[0], cols[1])]}
    if w == "freq_hi":
        h = sum((zlib.crc32(text(k).encode()) if k is not None else 0) * n
                for k, n in zip(cols[0], cols[1])) % 2**64
        return {"groups": len(cols[0]), "total": sum(cols[1]), "hash": h}
    if w == "deep":
        return {"count": cols[0][0]}


docs = None
if a.count:
    m = next(iter(opteryx.session().execute_to_morsels(f"SELECT COUNT(*) FROM {T}")))
    docs = m.column(m.column_names[0]).to_pylist()[0]

workers = os.environ.get("MAX_EXECUTION_WORKERS", "auto")
for i in range(a.repeat):
    secs, morsels = run()
    res = digest(morsels) if i == a.repeat - 1 else None
    print(json.dumps({
        "parser": "opteryx", "version": opteryx.__version__, "api": "sql", "workload": a.workload,
        "threads": workers, "run": i, "files": len(files), "bytes": nbytes, "seconds": round(secs, 6),
        "docs": docs, "rejected": None, "result": res,
    }), flush=True)
