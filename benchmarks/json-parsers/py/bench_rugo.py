"""rugo driver: rugo.jsonl.read_jsonl() called directly, one file at a time.

    python bench_rugo.py --workload W --source GLOB [--repeat R]

rugo is a reader, not a query engine: it projects columns and pushes predicates down, and
returns typed columns (draken vectors). So:

  filter_hi/lo  full workload   columns=["did"], predicate on commit->>'collection'
  minmax        full workload   columns=["time_us"], then the vector's own min()/max()
  freq_lo/hi,   EXTRACT ONLY    the key column is read (and for filter_agg, filtered), but
  filter_agg                    not counted: rugo has no GROUP BY. Opteryx is the full
                                workload over the same reader.
  parse         READ ALL        every top-level column materialised (nested objects as raw
                                JSON text). Not a DOM; closest rugo equivalent.
  deep, langs   not supported   rugo projects one level of nesting (key->>'sub').

Each file is read with rugo's internal threading (it uses every core; there is no thread
count knob). --file-workers N also overlaps N files at once from a Python thread pool
(read_jsonl releases the GIL), as an engine scanning many files would. fail_on_error=False skips malformed lines. Timed: the read of every file.
Filter results are kept for the digest; other results are dropped as each file finishes,
so 100M rows of extracted text do not push the input files out of the page cache. Run 0
is the warm-up; the report drops it. The digest's Python conversion is not timed.
"""
import argparse
import glob
import json
import os
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

import rugo
from rugo.jsonl import read_jsonl

ap = argparse.ArgumentParser()
ap.add_argument("--workload", required=True)
ap.add_argument("--source", required=True)
ap.add_argument("--repeat", type=int, default=1)
ap.add_argument("--file-workers", type=int, default=1)
a = ap.parse_args()

COLL = "commit->>'collection'"
SPEC = {
    "filter_hi": dict(columns=["did"], predicates=[(COLL, "==", "app.bsky.feed.like")]),
    "filter_lo": dict(columns=["did"], predicates=[(COLL, "==", "app.bsky.graph.block")]),
    "minmax": dict(columns=["time_us"]),
    "freq_lo": dict(columns=[COLL]),
    "freq_hi": dict(columns=["did"]),
    "filter_agg": dict(columns=[COLL], predicates=[("kind", "==", "commit"), ("commit->>'operation'", "==", "create")]),
    "parse": dict(),
}
SCOPE = {"filter_hi": "full", "filter_lo": "full", "minmax": "full",
         "freq_lo": "extract-only", "freq_hi": "extract-only", "filter_agg": "extract-only",
         "parse": "read-all-columns"}
if a.workload not in SPEC:
    sys.exit(f"rugo: workload {a.workload!r} not supported")

files = sorted(glob.glob(a.source))
nbytes = sum(os.path.getsize(f) for f in files)


def read_one(f):
    kept, mn, mx, rows = [], None, None, 0
    with read_jsonl(f, fail_on_error=False, **SPEC[a.workload]) as r:
        for m in r:
            rows += m.num_rows
            if a.workload == "minmax":
                v = m.column(b"time_us")
                lo, hi = v.min(), v.max()
                mn = lo if mn is None else min(mn, lo)
                mx = hi if mx is None else max(mx, hi)
            if a.workload in ("filter_hi", "filter_lo"):
                kept.append(m)
    return kept, rows, mn, mx


def run():
    t0 = time.perf_counter()
    if a.file_workers > 1:
        with ThreadPoolExecutor(a.file_workers) as ex:
            parts = list(ex.map(read_one, files))
    else:
        parts = [read_one(f) for f in files]
    secs = time.perf_counter() - t0
    kept = [m for p in parts for m in p[0]]
    rows = sum(p[1] for p in parts)
    mins = [p[2] for p in parts if p[2] is not None]
    maxs = [p[3] for p in parts if p[3] is not None]
    return secs, kept, rows, (min(mins) if mins else None, max(maxs) if maxs else None)


def digest(kept, rows, mm):
    w = a.workload
    if w in ("filter_hi", "filter_lo"):
        dids = [d for m in kept for d in m.column(b"did").to_pylist()]
        nulls = sum(1 for d in dids if d is None)
        h = sum(zlib.crc32(d.encode() if isinstance(d, str) else d) for d in dids if d is not None) % 2**64
        return {"rows": len(dids), "nulls": nulls, "hash": h}
    if w == "minmax":
        return {"min": mm[0], "max": mm[1]}
    return {"extracted_rows": rows}


for i in range(a.repeat):
    secs, kept, rows, mm = run()
    res = digest(kept, rows, mm) if i == a.repeat - 1 else None
    docs = rows if a.workload in ("freq_lo", "freq_hi", "minmax", "parse") else None
    print(json.dumps({
        "parser": "rugo", "version": rugo.__version__, "api": f"read_jsonl:{SCOPE[a.workload]}" + (f" fw={a.file_workers}" if a.file_workers > 1 else ""),
        "workload": a.workload, "threads": "all", "run": i, "files": len(files), "bytes": nbytes,
        "seconds": round(secs, 6), "docs": docs, "rejected": None, "result": res,
    }), flush=True)
    del kept
