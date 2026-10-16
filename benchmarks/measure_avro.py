#!/usr/bin/env python3
"""Measure rugo's Avro reader against fastavro and the Apache `avro` package on
this machine and write a results file.

    python3 benchmarks/measure_avro.py [--rows 200000] [--reps 5] [--python 3.13]

Needs `uv` on PATH. Builds one fresh venv per library (footprint + cold import)
and one shared venv for the timings, generates a deterministic deflate file with
fastavro (gen_avro.py), times each (reader, shape) in a fresh process
(avro_one.py), and writes benchmarks/results/<UTC date>-avro.json. Results are
only comparable to earlier runs from the same machine.

This compares readers; benchmarks/measure_avro_write.py compares writers.
"""
import argparse, datetime, json, os, platform, shutil, subprocess, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=200_000)
ap.add_argument("--reps", type=int, default=5)
ap.add_argument("--python", default="3.13")
ap.add_argument("--workdir", default=tempfile.mkdtemp(prefix="rugo-avro-bench-"))
a = ap.parse_args()
W = a.workdir


def sh(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def venv(name, pkgs):
    p = f"{W}/venv-{name}"
    sh("uv", "venv", "--python", a.python, p)
    sh("uv", "pip", "install", "--python", f"{p}/bin/python", *pkgs)
    return p


def dir_size(p):
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(p)
               for f in fs if not os.path.islink(os.path.join(d, f)))


def versions(py, pkgs):
    have = {x["name"].lower(): x["version"]
            for x in json.loads(sh("uv", "pip", "list", "--python", py, "--format", "json"))}
    return {p: have.get(p) for p in pkgs}


ENTRY = {"rugo": "rugo.avro", "fastavro": "fastavro", "avro": "avro.datafile"}
res = {"date": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
       "machine": {"platform": platform.platform(), "cpu": platform.processor() or platform.machine(),
                   "python": a.python},
       "rows": a.rows, "reps": a.reps, "codec": "deflate", "footprint": {}, "reads": {}}

# --- footprint + cold import, one clean venv per library
for lib, mod in ENTRY.items():
    print("footprint:", lib, flush=True)
    p = venv(f"fp-{lib}", [lib]); py = f"{p}/bin/python"
    sp = sh(py, "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])").strip()

    def cold(code):
        best = 1e9
        for _ in range(15):
            t = time.perf_counter(); subprocess.run([py, "-c", code], check=True)
            best = min(best, time.perf_counter() - t)
        return best * 1000

    base = cold("pass")
    res["footprint"][lib] = {"version": versions(py, [lib])[lib], "installed_mb": round(dir_size(sp) / 1e6, 1),
                             "cold_import_ms": round(cold(f"import {mod}") - base, 1)}
    shutil.rmtree(p)

# --- read timings
allpy = venv("all", list(ENTRY))
py = f"{allpy}/bin/python"
res["versions"] = versions(py, list(ENTRY))
path = f"{W}/events.avro"
print("generating data", flush=True)
sh(py, f"{HERE}/gen_avro.py", path, str(a.rows), "deflate")
res["file_mb"] = round(os.path.getsize(path) / 1e6, 1)

for shape in ("all", "narrow"):
    for reader in ("rugo", "rugo+pylist", "fastavro", "avro"):
        print("read:", shape, reader, flush=True)
        out = json.loads(sh(py, f"{HERE}/avro_one.py", reader, shape, path, str(a.reps)).strip().splitlines()[-1])
        if out["rows"] != a.rows:
            raise SystemExit(f"{reader} read {out['rows']} rows, expected {a.rows}")
        res["reads"][f"{shape}/{reader}"] = out

os.makedirs(f"{HERE}/results", exist_ok=True)
fn = f"{HERE}/results/{res['date'][:10]}-avro.json"
json.dump(res, open(fn, "w"), indent=2)
print("wrote", fn)
for key, value in res["reads"].items():
    print(f"  {key:22s} best {value['best_ms']:10.1f} ms")
