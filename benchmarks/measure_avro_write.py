#!/usr/bin/env python3
"""Measure rugo's Avro writer against fastavro and the Apache `avro` package on
this machine and write a results file.

    python3 benchmarks/measure_avro_write.py [--rows 200000] [--reps 5] [--python 3.13]
                                             [--codecs null deflate zstandard]
                                             [--rugo-src /path/to/opteryx-core]

Needs `uv` on PATH. Builds one venv holding the libraries (rugo, fastavro, avro,
zstandard), generates the same deterministic event rows as the reader benchmark
(gen_avro.py, written by fastavro), and has rugo read that file and write it once:
that file - its schema and rows - is what every writer then writes, each timed in a
fresh process (avro_write_one.py) per (writer, codec). Results go to
benchmarks/results/<UTC date>-avro-write.json and are only comparable to earlier runs
from the same machine.

The schema is the one rugo writes for these rows (the reader returns the nested
record and map as JSON text, so they are strings here; no-null columns are required,
low-cardinality names are enums, the decimal is a fixed), so all three write the same
thing.

--rugo-src: import rugo (and draken) from an opteryx-core source tree, built in place,
instead of PyPI - for a writer not yet released. --python must then match the tree's
build. The results file records which rugo was measured.
"""
import argparse, datetime, json, os, platform, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=200_000)
ap.add_argument("--reps", type=int, default=5)
ap.add_argument("--python", default="3.13")
ap.add_argument("--codecs", nargs="+", default=["null", "deflate", "zstandard"])
ap.add_argument("--rugo-src")
ap.add_argument("--workdir", default=tempfile.mkdtemp(prefix="rugo-avro-write-bench-"))
a = ap.parse_args()
W = a.workdir
UV = os.environ.get("UV", "uv")
ENV = dict(os.environ)
if a.rugo_src:
    ENV["PYTHONPATH"] = os.path.abspath(a.rugo_src)


def sh(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, env=ENV, cwd=W).stdout


# fastavro 1.13 takes its zstd codec from backports.zstd (stdlib on 3.14+)
libs = ["fastavro", "avro", "zstandard", "backports.zstd; python_version < '3.14'"] + ([] if a.rugo_src else ["rugo"])
venv = f"{W}/venv"
sh(UV, "venv", "--python", a.python, venv)
sh(UV, "pip", "install", "--python", f"{venv}/bin/python", *libs)
py = f"{venv}/bin/python"
have = {x["name"].lower(): x["version"]
        for x in json.loads(sh(UV, "pip", "list", "--python", py, "--format", "json"))}
rugo_version = sh(py, "-c", "import rugo;print(rugo.__version__, getattr(rugo, '__writer_id__', ''))").strip()

res = {"date": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
       "machine": {"platform": platform.platform(), "cpu": platform.processor() or platform.machine(),
                   "python": a.python, "cores": os.cpu_count()},
       "rows": a.rows, "reps": a.reps,
       "versions": {"rugo": rugo_version + (" (source build, not on PyPI)" if a.rugo_src else ""),
                    "fastavro": have.get("fastavro"), "avro": have.get("avro")},
       "writes": {}}

print("generating data", flush=True)
source = f"{W}/events.avro"
sh(py, f"{HERE}/gen_avro.py", source, str(a.rows), "deflate")
common = f"{W}/events_rugo.avro"
sh(py, "-c", (
    "import sys; from draken.morsels.morsel import Morsel; from rugo import avro\n"
    f"r = avro.read_avro({source!r})\n"
    "with r as it: m = Morsel.combine(list(it))\n"
    f"open({common!r}, 'wb').write(avro.write_avro(m, codec='null', record_name='Event'))\n"))
res["schema"] = json.loads(sh(py, "-c", f"from rugo import avro; import json; print(json.dumps(avro.read_metadata({common!r}).schema))"))

for codec in a.codecs:
    for writer in ("rugo", "rugo-1t", "fastavro", "avro"):
        print("write:", codec, writer, flush=True)
        out = json.loads(sh(py, f"{HERE}/avro_write_one.py", writer, codec, common, str(a.reps)).strip().splitlines()[-1])
        if out["rows"] != a.rows:
            raise SystemExit(f"{writer} wrote {out['rows']} rows, expected {a.rows}")
        res["writes"][f"{codec}/{writer}"] = out

os.makedirs(f"{HERE}/results", exist_ok=True)
fn = f"{HERE}/results/{res['date'][:10]}-avro-write.json"
json.dump(res, open(fn, "w"), indent=2)
print("wrote", fn)
for key, value in res["writes"].items():
    print(f"  {key:22s} best {value['best_ms']:10.1f} ms  median {value['median_ms']:10.1f}  bytes {value['bytes']:>12,d}")
