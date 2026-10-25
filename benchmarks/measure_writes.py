#!/usr/bin/env python3
"""Measure rugo's Parquet, CSV and JSONL writers against the usual Python
libraries on this machine and write a results file.

    python3 benchmarks/measure_writes.py [--reps 5] [--python 3.13]
                                     [--rugo-wheel PATH [--rugo-version 0.5.5+local]]
                                     [--rugo-tree DIR --rugo-version LABEL]

Needs `uv` on PATH. Builds one venv with the published packages, generates the
same deterministic data as measure.py (gen_data.py), and has every library write
the same 200,000-row, 50-column table (wide.csv) in each format it can, each
(library, format) timed in a fresh process (write_one.py). Results go to
benchmarks/results/<UTC date>-writes.json and are only comparable to earlier runs
from the same machine. --rugo-wheel PATH installs rugo from a local wheel (matching --python)
instead of PyPI and records --rugo-version (default "<wheel version>+local"); the file then
gets a "-<version>" suffix (...-writes-0.5.5.json).

--rugo-tree DIR measures rugo from a source checkout instead of a wheel: DIR (an
opteryx-core tree with rugo/ and draken/ built in place) goes on PYTHONPATH for every
run (each reads its output back with rugo), the other libraries still come from PyPI.
Point DIR at a directory holding only rugo/ and draken/ so nothing else in a repo root
can shadow a library. --rugo-version is
REQUIRED because there is no installed package to read it from (label it so the
results file says it was not a release). The tree's compiled extensions are for one
CPython (cp314 on Apple silicon today), so pass --python to match.
"""
import argparse, datetime, json, os, platform, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--reps", type=int, default=5)
ap.add_argument("--python", default="3.13")
ap.add_argument("--rugo-wheel", default=None, help="install rugo from this local wheel instead of PyPI")
ap.add_argument("--rugo-version", default=None, help="version to record for the local wheel (default: its own version + '+local')")
ap.add_argument("--rugo-tree", default=None, help="measure rugo from this source tree (needs --rugo-version)")
ap.add_argument("--workdir", default=tempfile.mkdtemp(prefix="rugo-write-bench-"))
a = ap.parse_args()
W = a.workdir
if a.rugo_tree and a.rugo_wheel:
    ap.error("--rugo-tree and --rugo-wheel are alternatives")
if a.rugo_tree and not a.rugo_version:
    ap.error("--rugo-tree needs --rugo-version (the label recorded for the tree)")
if a.rugo_version and not (a.rugo_wheel or a.rugo_tree):
    ap.error("--rugo-version only applies together with --rugo-wheel or --rugo-tree")
RUGO = os.path.abspath(a.rugo_wheel) if a.rugo_wheel else "rugo"
TREE = os.path.abspath(a.rugo_tree) if a.rugo_tree else None
UV = os.environ.get("UV", "uv")


def sh(*cmd, env=None):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, cwd=W, env=env).stdout


PKGS = ["rugo", "pyarrow", "polars", "duckdb", "fastparquet", "pandas"]
PLAN = {"parquet": ["rugo", "rugo-fast", "rugo-defaults", "pyarrow", "polars", "duckdb", "fastparquet"],
        "csv": ["rugo", "pyarrow", "polars", "duckdb", "python"],
        "jsonl": ["rugo", "polars", "duckdb", "python"]}

venv = f"{W}/venv"
sh(UV, "venv", "--python", a.python, venv)
sh(UV, "pip", "install", "--python", f"{venv}/bin/python",
   *[RUGO if p == "rugo" else p for p in PKGS if not (TREE and p == "rugo")])
py = f"{venv}/bin/python"
have = {x["name"].lower(): x["version"] for x in json.loads(sh(UV, "pip", "list", "--python", py, "--format", "json"))}
if a.rugo_wheel:
    have["rugo"] = a.rugo_version or have["rugo"] + "+local"
if TREE:
    have["rugo"] = a.rugo_version
# Every run reads its output back with rugo, so every run needs the tree on its path.
run_env = dict(os.environ, PYTHONPATH=TREE) if TREE else None

res = {"date": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
       "machine": {"platform": platform.platform(), "cpu": platform.processor() or platform.machine(),
                   "python": a.python, "cores": os.cpu_count()},
       "reps": a.reps, "versions": {p: have.get(p) for p in PKGS}, "writes": {}}

print("generating data", flush=True)
data = f"{W}/data"
sh(py, f"{HERE}/gen_data.py", data, "1000")  # the JSONL read file is not used here; keep it small
src = f"{data}/wide.csv"
res["table"] = {"rows": 200_000, "columns": 50, "csv_mb": round(os.path.getsize(src) / 1e6, 1)}

for fmt, libs in PLAN.items():
    for lib in libs:
        print("write:", fmt, lib, flush=True)
        out = json.loads(sh(py, f"{HERE}/write_one.py", lib, fmt, src, str(a.reps), W,
                            env=run_env).strip().splitlines()[-1])
        if out["rows"] != 200_000:
            raise SystemExit(f"{lib} {fmt}: read back {out['rows']} rows, expected 200,000")
        res["writes"][f"{fmt}/{lib}"] = out

os.makedirs(f"{HERE}/results", exist_ok=True)
suffix = "-" + have["rugo"].split("+")[0] if (a.rugo_wheel or TREE) else ""
fn = f"{HERE}/results/{res['date'][:10]}-writes{suffix}.json"
json.dump(res, open(fn, "w"), indent=2)
print("wrote", fn)
for key, value in res["writes"].items():
    print(f"  {key:20s} best {value['best_ms']:9.1f} ms  median {value['median_ms']:9.1f}  bytes {value['bytes']:>12,d}")
