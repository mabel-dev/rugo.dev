#!/usr/bin/env python3
"""Head-to-head ORC read benchmark: rugo vs PyArrow (Apache ORC C++). The ORC twin of
measure_parquet.py - same data, queries, fresh process per (library, query), each library's
default threading and again pinned to one thread.

    python3 benchmarks/measure_orc.py --rugo-src /path/to/opteryx-core [--rows 1000000] [--reps 7]
                                      [--python 3.14]

Needs `uv` on PATH. DuckDB and Polars are not in the field: neither has a built-in ORC reader.
--rugo-src: import rugo (and draken) from an opteryx-core source tree built in place
(`make c`); the ORC reader is not on PyPI yet. --python must match that build's CPython.
rugo.orc decodes stripes serially and has no predicate argument, so its "all" and "1" rows
are the same reader, and its filtered queries are recorded as unsupported, not timed.
Writes benchmarks/results/<UTC date>-orc-read.json.
"""
import argparse, datetime, json, os, platform, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=1_000_000)
ap.add_argument("--reps", type=int, default=7)
ap.add_argument("--python", default="3.14")
ap.add_argument("--rugo-src", required=True)
ap.add_argument("--workdir", default=tempfile.mkdtemp(prefix="rugo-orc-bench-"))
a = ap.parse_args()
W = a.workdir
ENV = dict(os.environ, PYTHONPATH=os.path.abspath(a.rugo_src))

def sh(*cmd, env=None):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, env=env).stdout

LIBS = ["rugo", "pyarrow"]
sh("uv", "venv", "--python", a.python, f"{W}/venv")
py = f"{W}/venv/bin/python"
sh("uv", "pip", "install", "--python", py, "pyarrow")
have = {x["name"].lower(): x["version"] for x in json.loads(sh("uv", "pip", "list", "--python", py, "--format", "json"))}
have["rugo"] = sh(py, "-c", "import rugo;print(rugo.__version__)", env=ENV).strip() + " (source build, not on PyPI)"

data = f"{W}/data"
sh(py, f"{HERE}/gen_orc.py", data, str(a.rows))
files = {"wide": f"{data}/wide.orc", "narrow": f"{data}/narrow.orc"}
meta = json.loads(sh(py, "-c", "import json,pyarrow.orc as po;"
                     f"m=[po.ORCFile(p) for p in ({files['wide']!r},{files['narrow']!r})];"
                     "print(json.dumps([[x.nrows,len(x.schema),x.nstripes] for x in m]))"))
for p in files.values():  # warm the page cache
    with open(p, "rb") as f:
        while f.read(1 << 24): pass

plan = [("wide", q) for q in ["select2", "unsorted_p10", "unsorted_p1", "sorted_p10", "sorted_p1", "count"]] + [("narrow", "full")]
res = {"date": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
       "machine": {"platform": platform.platform(), "cpu": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip() or platform.machine(),
                   "cores": os.cpu_count(), "python": a.python},
       "versions": {l: have.get(l) for l in LIBS},
       "files": {k: {"mb": round(os.path.getsize(p) / 1e6, 1), "rows": m[0], "columns": m[1], "stripes": m[2],
                     "compression": "zstd"} for (k, p), m in zip(files.items(), meta)},
       "reps": a.reps, "queries": {}}
for threads in ["all", "1"]:
    for f, q in plan:
        for lib in LIBS:
            print("query:", threads, f, q, lib, flush=True)
            out = sh(py, f"{HERE}/bench_orc_one.py", lib, q, files[f], str(a.reps), threads, env=ENV)
            res["queries"][f"{threads}/{f}/{q}/{lib}"] = json.loads(out.strip().splitlines()[-1])

fn = f"{HERE}/results/{res['date'][:10]}-orc-read.json"
os.makedirs(os.path.dirname(fn), exist_ok=True)
json.dump(res, open(fn, "w"), indent=2)
print("wrote", fn)
