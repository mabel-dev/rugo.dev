#!/usr/bin/env python3
"""Re-measure rugo's headline numbers on this machine and append a results file.

    python3 benchmarks/measure.py [--rows 200000] [--reps 5] [--python 3.13]

Needs `uv` on PATH. Builds one fresh venv per library (footprint + cold import),
one shared venv for rugo/pyarrow/duckdb/polars (query timings), generates
deterministic data, and writes benchmarks/results/<UTC date>.json.
Results are only comparable to earlier runs from the same machine.
"""
import argparse, datetime, json, os, platform, shutil, statistics, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=200_000)
ap.add_argument("--reps", type=int, default=5)
ap.add_argument("--python", default="3.13")
ap.add_argument("--workdir", default=tempfile.mkdtemp(prefix="rugo-bench-"))
a = ap.parse_args()
W = a.workdir

def sh(*cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout

def venv(name, pkgs):
    p = f"{W}/venv-{name}"
    sh("uv", "venv", "--python", a.python, p)
    sh("uv", "pip", "install", "--python", f"{p}/bin/python", *pkgs)
    return p

def dir_size(p):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p) for f in fs if not os.path.islink(os.path.join(d, f)))

def versions(py, pkgs):
    out = sh("uv", "pip", "list", "--python", py, "--format", "json")
    have = {x["name"].lower().replace("_", "-"): x["version"] for x in json.loads(out)}
    return {p: have.get(p) for p in pkgs}

ENTRY = {"rugo": "rugo.parquet", "duckdb": "duckdb", "fastparquet": "fastparquet",
         "pyarrow": "pyarrow.parquet", "polars": "polars"}
res = {"date": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
       "machine": {"platform": platform.platform(), "cpu": platform.processor() or platform.machine(),
                   "python": a.python}, "footprint": {}, "queries": {}}

# --- footprint + cold import, one clean venv per library
for lib, mod in ENTRY.items():
    print("footprint:", lib, flush=True)
    p = venv(f"fp-{lib}", [lib]); py = f"{p}/bin/python"
    sp = sh(py, "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])").strip()
    def cold(code):
        best = 1e9
        for _ in range(15):
            t = time.perf_counter(); subprocess.run([py, "-c", code], check=True); best = min(best, time.perf_counter() - t)
        return best * 1000
    base = cold("pass")
    res["footprint"][lib] = {"version": versions(py, [lib])[lib], "installed_mb": round(dir_size(sp) / 1e6, 1),
                             "cold_import_ms": round(cold(f"import {mod}") - base, 1),
                             "n_packages": len(json.loads(sh("uv", "pip", "list", "--python", py, "--format", "json")))}
    shutil.rmtree(p)

# --- query timings
print("generating data", flush=True)
allpy = venv("all", ["rugo", "pyarrow", "duckdb", "polars"])
py = f"{allpy}/bin/python"
res["versions"] = versions(py, ["rugo", "pyarrow", "duckdb", "polars"])
data = f"{W}/data"
sh(py, f"{HERE}/gen_data.py", data, str(a.rows))
res["data"] = {f: round(os.path.getsize(f"{data}/{f}") / 1e6, 1) for f in os.listdir(data)}

plan = [("jsonl", f"{data}/wide.jsonl", ["rugo", "pyarrow"], ["select1", "p10", "p1", "select_star"]),
        ("csv", f"{data}/wide.csv", ["rugo", "pyarrow"], ["select_star", "select1", "p10", "p1"]),
        ("parquet", f"{data}/events.parquet", ["rugo", "pyarrow", "duckdb", "polars"], ["broad", "selective", "pruned"])]
for wl, path, libs, queries in plan:
    for q in queries:
        for lib in libs:
            print("query:", wl, q, lib, flush=True)
            out = sh(py, f"{HERE}/bench_one.py", lib, wl, q, path, str(a.reps))
            res["queries"][f"{wl}/{q}/{lib}"] = json.loads(out.strip().splitlines()[-1])

os.makedirs(f"{HERE}/results", exist_ok=True)
fn = f"{HERE}/results/{res['date'][:10]}.json"
json.dump(res, open(fn, "w"), indent=2)
print("wrote", fn)
