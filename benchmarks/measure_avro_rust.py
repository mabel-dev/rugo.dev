#!/usr/bin/env python3
"""Race rugo's Avro reader against the Rust Avro readers on this machine.

    python3 benchmarks/measure_avro_rust.py [--rows 200000] [--rounds 5] [--reps 5]
                                            [--python 3.14] [--rugo-src /path/to/opteryx-core]
                                            [--tag name]   # results/<date>-avro-rust-<name>.json

Needs `uv` and `cargo` on PATH. Same file and method as measure_avro.py: gen_avro.py
writes a deterministic 20-field file with fastavro (so no reader is timed on its own
writer's output), each reader decodes the same in-memory bytes in a fresh process,
reading the file is outside the timing. Both codecs, `deflate` and `null` (`null`
isolates decode from inflate).

Arms - single thread unless the name says otherwise:
  rugo-1t              PyPI rugo, read_avro(max_threads=1) -> Morsels (avro_one.py)
  rugo                 PyPI rugo, every core (rugo's default) - NOT part of the race
  rugo-src-1t / -src   the same from an opteryx-core source tree (--rugo-src)
  arrow-avro           Apache Arrow's arrow-avro -> RecordBatches, crate defaults
                       (batch 1024, StringArray, miniz_oxide inflate)
  arrow-avro-tuned     the same with batch 65,536 (rugo's morsel size) and flate2 on
                       zlib-rs, the fastest Rust inflater - arrow-avro at its best
  arrow-avro-tuned-view  tuned + StringViewArray strings
  apache-avro          the Apache Avro Rust crate -> one Value per record

Rounds interleave the arms (order rotated each round) so thermal drift and order
bias land on every arm; each (round, arm) is a fresh process running `reps` reads.
Per arm: best = min over every read, median = median of the per-process medians.
Writes benchmarks/results/<UTC date>-avro-rust.json. Results are only comparable to
earlier runs from the same machine.
"""
import argparse, datetime, json, os, platform, statistics, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CRATE = f"{HERE}/avro-rust"
ap = argparse.ArgumentParser()
ap.add_argument("--rows", type=int, default=200_000)
ap.add_argument("--rounds", type=int, default=5)
ap.add_argument("--reps", type=int, default=5)
ap.add_argument("--python", default="3.14")
ap.add_argument("--rugo-src")
ap.add_argument("--tag")
ap.add_argument("--workdir", default=tempfile.mkdtemp(prefix="rugo-avro-rust-"))
a = ap.parse_args()
W = a.workdir


def sh(*cmd, env=None):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, env=env).stdout


def venv(name, pkgs):
    p = f"{W}/venv-{name}"
    sh("uv", "venv", "--python", a.python, p)
    sh("uv", "pip", "install", "--python", f"{p}/bin/python", *pkgs)
    return f"{p}/bin/python"


# --- builds: one binary per flate2 backend
print("building Rust readers", flush=True)
BIN = {}
for variant, extra in (("default", []), ("zlib-rs", ["--features", "zlib-rs"])):
    sh("cargo", "build", "--release", "--quiet", "--manifest-path", f"{CRATE}/Cargo.toml",
       "--target-dir", f"{CRATE}/target/{variant}", *extra)
    BIN[variant] = f"{CRATE}/target/{variant}/release/avro_rust"
lock = open(f"{CRATE}/Cargo.lock").read().split("[[package]]")
crate_versions = {}
for block in lock:
    fields = dict(line.split(" = ", 1) for line in block.strip().splitlines() if " = " in line)
    name = fields.get("name", "").strip('"')
    if name in ("arrow-avro", "apache-avro", "flate2", "zlib-rs", "miniz_oxide"):
        crate_versions[name] = fields["version"].strip('"')

# --- Python side
pypi = venv("pypi", ["rugo", "fastavro"])
ARMS = {"rugo-1t": [pypi, f"{HERE}/avro_one.py", "rugo-1t"],
        "rugo": [pypi, f"{HERE}/avro_one.py", "rugo"]}
ENV = {}
versions = {"rugo": sh(pypi, "-c", "import rugo;print(rugo.__version__)").strip(),
            "rustc": sh("rustc", "--version").strip(), **crate_versions}
if a.rugo_src:
    srcpy = venv("src", ["fastavro"])
    ENV = {**os.environ, "PYTHONPATH": os.path.abspath(a.rugo_src)}
    ARMS["rugo-src-1t"] = [srcpy, f"{HERE}/avro_one.py", "rugo-1t"]
    ARMS["rugo-src"] = [srcpy, f"{HERE}/avro_one.py", "rugo"]
    versions["rugo-src"] = sh(srcpy, "-c", "import rugo;print(rugo.__version__, rugo.__file__)", env=ENV).strip()
ARMS.update({
    "arrow-avro": [BIN["default"], "arrow-avro"],
    "arrow-avro-tuned": [BIN["zlib-rs"], "arrow-avro"],
    "arrow-avro-tuned-view": [BIN["zlib-rs"], "arrow-avro"],
    "apache-avro": [BIN["default"], "apache-avro"],
})
RUST_TAIL = {"arrow-avro": ["1024", "0"], "arrow-avro-tuned": ["65536", "0"],
             "arrow-avro-tuned-view": ["65536", "1"], "apache-avro": []}

res = {"date": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
       "machine": {"platform": platform.platform(), "cpu": platform.processor() or platform.machine(),
                   "cores": os.cpu_count(), "python": a.python},
       "rows": a.rows, "rounds": a.rounds, "reps": a.reps, "versions": versions,
       "files_mb": {}, "reads": {}}

for codec in ("deflate", "null"):
    path = f"{W}/events-{codec}.avro"
    print("generating", codec, flush=True)
    sh(pypi, f"{HERE}/gen_avro.py", path, str(a.rows), codec)
    res["files_mb"][codec] = round(os.path.getsize(path) / 1e6, 1)
    for shape in ("all", "narrow"):
        runs = {arm: [] for arm in ARMS}
        names = list(ARMS)
        for rnd in range(a.rounds):
            order = names[rnd % len(names):] + names[:rnd % len(names)]
            for arm in order:
                print(f"read: {codec} {shape} round {rnd + 1}/{a.rounds} {arm}", flush=True)
                cmd = ARMS[arm] + [shape, path, str(a.reps)] + RUST_TAIL.get(arm, [])
                env = ENV if arm.startswith("rugo-src") else None
                out = json.loads(sh(*cmd, env=env).strip().splitlines()[-1])
                if out["rows"] != a.rows:
                    raise SystemExit(f"{arm} read {out['rows']} rows, expected {a.rows}")
                runs[arm].append(out)
        for arm, outs in runs.items():
            res["reads"][f"{codec}/{shape}/{arm}"] = {
                "best_ms": min(o["best_ms"] for o in outs),
                "median_ms": round(statistics.median(o["median_ms"] for o in outs), 1),
                "rows": a.rows}

os.makedirs(f"{HERE}/results", exist_ok=True)
fn = f"{HERE}/results/{res['date'][:10]}-avro-rust{'-' + a.tag if a.tag else ''}.json"
json.dump(res, open(fn, "w"), indent=2)
print("wrote", fn)
for key, value in res["reads"].items():
    print(f"  {key:40s} best {value['best_ms']:9.1f}  median {value['median_ms']:9.1f} ms")
