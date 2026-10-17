"""Noise-reduced cold-call model.

Cold-call billed time = median init (over all 20 cold samples per lib/arch/memory, since init
does not depend on query shape) + median cold handler time excluding the S3 download
+ a shared median download time for that arch/memory (same work for every library).
Warm-call billed time = median Billed Duration of warm calls.
"""
import json
import statistics as st
import sys
from collections import defaultdict

PRICE = {"x86_64": 0.0000166667, "aarch64": 0.0000133334}
LIBS = ["rugo", "pyarrow", "duckdb", "polars"]
SHAPES = ["broad", "selective", "pruned", "footer"]

rows = []
for f in sys.argv[1:]:
    rows += [json.loads(l) for l in open(f)]
ok = [r for r in rows if not r["error"]]
failed = defaultdict(int)
for r in rows:
    if r["error"]:
        failed[(r["lib"], r["arch"], r["memory"])] += 1

init = defaultdict(list)
dl = defaultdict(list)
cold_handler = defaultdict(list)
warm = defaultdict(list)
peak = defaultdict(list)
for r in ok:
    a, m, lib, s = r["arch"], int(r["memory"]), r["lib"], r["shape"]
    peak[(lib, a, m)].append(r["max_memory"])
    if r["kind"] == "cold":
        init[(lib, a, m)].append(r["init"])
        dl[(a, m)].append(r["payload"]["download_ms"])
        cold_handler[(lib, a, m, s)].append(r["duration"] - r["payload"]["download_ms"])
    else:
        warm[(lib, a, m, s)].append(r["billed"])


def model(lib, a, m, s):
    if (lib, a, m, s) not in warm:
        return None
    c = st.median(init[(lib, a, m)]) + st.median(cold_handler[(lib, a, m, s)]) + st.median(dl[(a, m)])
    return c, st.median(warm[(lib, a, m, s)])


def dollars(ms, m, a):
    return ms / 1000 * m / 1024 * PRICE[a] * 1e6 + 0.20


def breakeven(r, o):
    (rc, rw), (oc, ow) = r, o
    pen, save = rw - ow, oc - rc
    if pen <= 0 and save >= 0:
        return "always"
    if pen >= 0 and save <= 0:
        return "never"
    if pen > 0:
        return f"above {pen / (pen + save):.0%}"
    return f"below {-pen / (-pen - save):.0%}"


configs = sorted({(r["arch"], int(r["memory"])) for r in rows}, key=lambda x: (x[0], -x[1]))
print("failed calls:", dict(failed))
for a, m in configs:
    print(f"\n=== {a} @ {m} MB  (shared download median {st.median(dl[(a, m)]):.0f} ms) ===")
    print(f"{'lib':9}{'init':>7}{'peak MB':>9}")
    for lib in LIBS:
        if (lib, a, m) in init:
            print(f"{lib:9}{st.median(init[(lib, a, m)]):>7.0f}{max(peak[(lib, a, m)]):>9.0f}")
        else:
            print(f"{lib:9}  failed")
    print(f"{'shape':10}" + "".join(f"{l + ' cold/warm':>22}" for l in LIBS) + "   rugo cheaper vs pyarrow | duckdb | polars")
    for s in SHAPES:
        cells, be = [], []
        for lib in LIBS:
            v = model(lib, a, m, s)
            cells.append(f"{v[0]:>13.0f}/{v[1]:<8.0f}" if v else f"{'-':>22}")
        r = model("rugo", a, m, s)
        for o in ("pyarrow", "duckdb", "polars"):
            ov = model(o, a, m, s)
            be.append(breakeven(r, ov) if r and ov else "n/a")
        print(f"{s:10}" + "".join(cells) + "   " + " | ".join(be))
    print("  $/million, broad:")
    for f in (0, 0.1, 0.25, 0.5, 1):
        parts = []
        for lib in LIBS:
            v = model(lib, a, m, "broad")
            parts.append(f"{lib} {dollars(f * v[0] + (1 - f) * v[1], m, a):6.2f}" if v else f"{lib}    n/a")
        r, p = model("rugo", a, m, "broad"), model("pyarrow", a, m, "broad")
        vs = ""
        if r and p:
            vs = f"  rugo vs pyarrow {(dollars(f * r[0] + (1 - f) * r[1], m, a) / dollars(f * p[0] + (1 - f) * p[1], m, a) - 1):+.0%}"
        print(f"   {int(f * 100):>3}% cold: " + "  ".join(parts) + vs)
