#!/usr/bin/env python3
"""Head-to-head Parquet read benchmark: rugo vs DuckDB vs Polars (scan_parquet) vs PyArrow.

    python3 benchmarks/measure_parquet.py [--rows 1000000] [--reps 7] [--python 3.13]
                                      [--rugo-wheel PATH [--rugo-version 0.5.5+local]]

Needs `uv` on PATH. Builds one venv with the four libraries, generates a wide (100-column) and a
narrow (4-column) zstd Parquet file with 20 row groups (see gen_parquet.py), and times each
query in a fresh process per library, at each library's default threading and again pinned to
one thread. Writes benchmarks/results/<UTC date>-parquet-read.json.

--rugo-wheel PATH installs rugo from a local wheel instead of PyPI (it must match --python) and
records --rugo-version (default "<wheel version>+local") as its version; the results file then
gets a "-<version>" suffix (e.g. ...-parquet-read-0.5.5.json) so it never overwrites another run.
"""
import argparse, datetime, json, os, platform, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=1_000_000)
ap.add_argument("--reps", type=int, default=7)
ap.add_argument("--python", default="3.13")
ap.add_argument("--rugo-wheel", default=None, help="install rugo from this local wheel instead of PyPI")
ap.add_argument("--rugo-version", default=None, help="version to record for the local wheel (default: its own version + '+local')")
ap.add_argument("--workdir", default=tempfile.mkdtemp(prefix="rugo-parquet-bench-"))
a = ap.parse_args()
W = a.workdir

if a.rugo_version and not a.rugo_wheel:
    ap.error("--rugo-version only applies together with --rugo-wheel")
RUGO = os.path.abspath(a.rugo_wheel) if a.rugo_wheel else "rugo"

def sh(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout

LIBS = ["rugo", "duckdb", "polars", "pyarrow"]
sh("uv", "venv", "--python", a.python, f"{W}/venv")
py = f"{W}/venv/bin/python"
sh("uv", "pip", "install", "--python", py, *[RUGO if l == "rugo" else l for l in LIBS])
have = {x["name"].lower(): x["version"] for x in json.loads(sh("uv", "pip", "list", "--python", py, "--format", "json"))}
if a.rugo_wheel:
    have["rugo"] = a.rugo_version or have["rugo"] + "+local"

data = f"{W}/data"
sh(py, f"{HERE}/gen_parquet.py", data, str(a.rows))
files = {"wide": f"{data}/wide.parquet", "narrow": f"{data}/narrow.parquet"}
meta = json.loads(sh(py, "-c", "import json,pyarrow.parquet as pq;"
                     f"m=[pq.ParquetFile(p).metadata for p in ({files['wide']!r},{files['narrow']!r})];"
                     "print(json.dumps([[x.num_rows,x.num_columns,x.num_row_groups] for x in m]))"))
for p in files.values():  # warm the page cache
    with open(p, "rb") as f:
        while f.read(1 << 24): pass

plan = [("wide", q) for q in ["select2", "unsorted_p10", "unsorted_p1", "sorted_p10", "sorted_p1", "count"]] + [("narrow", "full")]
res = {"date": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
       "machine": {"platform": platform.platform(), "cpu": subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip() or platform.machine(),
                   "cores": os.cpu_count(), "python": a.python},
       "versions": {l: have.get(l) for l in LIBS},
       "files": {k: {"mb": round(os.path.getsize(p) / 1e6, 1), "rows": m[0], "columns": m[1], "row_groups": m[2],
                     "compression": "zstd"} for (k, p), m in zip(files.items(), meta)},
       "reps": a.reps, "queries": {}}
for threads in ["all", "1"]:
    for f, q in plan:
        for lib in LIBS:
            print("query:", threads, f, q, lib, flush=True)
            out = sh(py, f"{HERE}/bench_parquet_one.py", lib, q, files[f], str(a.reps), threads)
            res["queries"][f"{threads}/{f}/{q}/{lib}"] = json.loads(out.strip().splitlines()[-1])

suffix = "-" + have["rugo"].split("+")[0] if a.rugo_wheel else ""
fn = f"{HERE}/results/{res['date'][:10]}-parquet-read{suffix}.json"
os.makedirs(os.path.dirname(fn), exist_ok=True)
json.dump(res, open(fn, "w"), indent=2)
print("wrote", fn)
