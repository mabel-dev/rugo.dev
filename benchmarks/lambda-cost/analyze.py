"""Summarise results.jsonl: medians, cost per million calls, break-even cold-start rates."""
import json
import statistics
import sys
from collections import defaultdict

PRICE = {"x86_64": 0.0000166667, "aarch64": 0.0000133334}  # $ per GB-second, us-east-1
REQUEST = 0.20  # $ per million
LIBS = ["rugo", "pyarrow", "duckdb", "polars"]
SHAPES = ["broad", "selective", "pruned", "footer"]

rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else "results.jsonl")]
errors = [r for r in rows if r["error"]]
groups = defaultdict(list)
for r in rows:
    if not r["error"]:
        groups[(r["lib"], r["arch"], int(r["memory"]), r["shape"], r["kind"])].append(r)


def med(key, field):
    vals = [r[field] if field in r else r["payload"][field] for r in groups[key]]
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def cost(billed_ms, memory, arch):
    return billed_ms / 1000 * memory / 1024 * PRICE[arch] * 1e6 + REQUEST


summary = {}
for key in sorted(groups):
    lib, arch, memory, shape, kind = key
    summary[key] = {
        "n": len(groups[key]),
        "init": med(key, "init"),
        "duration": med(key, "duration"),
        "billed": med(key, "billed"),
        "max_memory": med(key, "max_memory"),
        "download_ms": med(key, "download_ms"),
        "query_ms": med(key, "query_ms"),
        "results": sorted({tuple(r["payload"]["result"]) for r in groups[key]}),
    }

print(f"errors: {len(errors)}")
for e in errors[:5]:
    print("  ", e["lib"], e["arch"], e["memory"], e["shape"], e["payload"])

for arch in PRICE:
    for memory in (1024, 512):
        print(f"\n=== {arch} @ {memory} MB ===")
        print(f"{'shape':10}{'lib':9}{'init':>8}{'cold billed':>12}{'warm billed':>12}{'warm query':>11}{'download':>9}{'peak MB':>8}  answers")
        for shape in SHAPES:
            for lib in LIBS:
                c = summary.get((lib, arch, memory, shape, "cold"))
                w = summary.get((lib, arch, memory, shape, "warm"))
                if not c or not w:
                    continue
                answers = c["results"] + w["results"]
                print(
                    f"{shape:10}{lib:9}{c['init']:>8.0f}{c['billed']:>12.0f}{w['billed']:>12.0f}"
                    f"{w['query_ms']:>11.1f}{c['download_ms']:>9.0f}{max(c['max_memory'], w['max_memory']):>8.0f}  {sorted(set(answers))}"
                )

        print(f"\n  break-even cold-start rate for rugo (cheaper above this):")
        for shape in SHAPES:
            parts = []
            for other in ("pyarrow", "duckdb", "polars"):
                try:
                    rc = summary[("rugo", arch, memory, shape, "cold")]["billed"]
                    rw = summary[("rugo", arch, memory, shape, "warm")]["billed"]
                    oc = summary[(other, arch, memory, shape, "cold")]["billed"]
                    ow = summary[(other, arch, memory, shape, "warm")]["billed"]
                except KeyError:
                    continue
                warm_pen, cold_save = rw - ow, oc - rc
                if warm_pen <= 0 and cold_save >= 0:
                    s = "always"
                elif warm_pen >= 0 and cold_save <= 0:
                    s = "never"
                elif warm_pen > 0:
                    s = f">{warm_pen / (warm_pen + cold_save):.1%}"
                else:
                    s = f"<{-warm_pen / (-warm_pen - cold_save):.1%}"
                parts.append(f"vs {other}: {s} (warm {warm_pen:+.0f} ms, cold {-cold_save:+.0f} ms)")
            print(f"  {shape:10}" + " | ".join(parts))

        print(f"\n  $ per million calls, broad (requests included):")
        for f in (0, 0.25, 0.5, 0.75, 1):
            line = []
            for lib in LIBS:
                c = summary[(lib, arch, memory, "broad", "cold")]["billed"]
                w = summary[(lib, arch, memory, "broad", "warm")]["billed"]
                line.append(f"{lib} ${cost(f * c + (1 - f) * w, memory, arch):6.2f}")
            print(f"  {int(f * 100):>3}% cold: " + "  ".join(line))

json.dump({"|".join(map(str, k)): v for k, v in summary.items()}, open("summary.json", "w"), indent=1, default=list)
