#!/usr/bin/env python3
"""Summarise a run: ./report.py results/<stamp> [results/<stamp2> ...]  ->  report.md in the first

Several directories merge: a measurement (pass, workload, method) in a later directory
replaces the same one from an earlier directory (a targeted re-run with --workloads/--methods).

Per pass and workload: best and median of the timed runs (run 0, the warm-up, is dropped),
GB/s on input file bytes at the best time, % of the newline-count floor, documents read and
rejected, and whether the answer matches the reference.

Reference = yyjson (strict RFC 8259 DOM; every document fully validated). "ok" means the
same answer. A different answer is shown as "DIFF", never hidden: the cause is
usually validation (an On-Demand API that does not validate what it skips can accept a
malformed line that the reference rejects).
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

WORKLOADS = ["parse", "filter_hi", "filter_lo", "minmax", "freq_lo", "freq_hi", "filter_agg", "deep", "langs"]
DESC = {
    "parse": "full parse of every document, nothing extracted",
    "filter_hi": "did of rows where commit.collection = 'app.bsky.feed.like' (~45% of rows)",
    "filter_lo": "did of rows where commit.collection = 'app.bsky.graph.block' (~1.4% of rows)",
    "minmax": "MIN and MAX of time_us",
    "freq_lo": "count per commit.collection (~20 distinct values)",
    "freq_hi": "count per did (millions of distinct values)",
    "filter_agg": "count per commit.collection where kind = 'commit' AND commit.operation = 'create'",
    "deep": "count rows with commit.record.reply.parent.uri (5 levels deep, absent on ~95%)",
    "langs": "unnest commit.record.langs (array), count per language",
}


def norm(res):
    if not isinstance(res, dict):
        return res
    if isinstance(res.get("groups"), list):
        return {"groups": sorted(map(tuple, res["groups"]), key=lambda g: (g[0] is not None, g[0] or ""))}
    return res


def check(r, ref):
    """ok / DIFF / n/a against the reference row's result."""
    if ref is None or r["result"] is None:
        return "?"
    res = r["result"]
    if "extracted_rows" in res:  # rugo extract-only: compare row counts
        rr = ref["result"]
        if r["workload"] == "filter_agg":
            want = sum(g[1] for g in rr["groups"])
        else:
            want = ref["docs"]
        return "ok (rows)" if res["extracted_rows"] == want else f"DIFF rows {res['extracted_rows']} vs {want}"
    return "ok" if norm(res) == norm(ref["result"]) else "DIFF"


def label(r):
    p, a = r["parser"], r["api"]
    return f"{p} {a}" if a else p


def summarise(paths):
    rows = []
    for path in paths:  # later files replace earlier measurements of the same method
        new = [json.loads(l) for l in open(path) if l.strip()]
        keys = {(r["workload"], label(r)) for r in new if not r.get("failed")}
        rows = [r for r in rows if r.get("failed") or (r["workload"], label(r)) not in keys]
        rows += new
    failed = [r["label"] for r in rows if r.get("failed")]
    groups = defaultdict(list)
    for r in rows:
        if r.get("failed"):
            continue
        groups[(r["workload"], label(r))].append(r)
    # Opteryx counts documents once per pass (an untimed COUNT(*)); show it on every row.
    opteryx_docs = next((r["docs"] for r in rows if r.get("parser") == "opteryx" and r.get("docs") is not None), None)
    for r in rows:
        if r.get("parser") == "opteryx" and r.get("docs") is None:
            r["docs"] = opteryx_docs
    out = []
    floor = groups.get(("parse", "floor-newlines"))
    floor_gbs = None
    if floor:
        timed = [r for r in floor if r["run"] > 0] or floor
        best = min(r["seconds"] for r in timed)
        floor_gbs = timed[0]["bytes"] / best / 1e9
        out.append(f"Floor (count newlines over the same mmap'd chunks, same threads): "
                   f"{best:.3f} s, {floor_gbs:.1f} GB/s over {timed[0]['bytes']/1e9:.2f} GB in {timed[0]['files']} files\n")
    for w in WORKLOADS:
        cells = [(k[1], v) for k, v in groups.items() if k[0] == w and k[1] != "floor-newlines"]
        if not cells:
            continue
        ref = next((v[-1] for k, v in cells if k.startswith("yyjson")), None)
        out.append(f"### {w}: {DESC[w]}\n")
        out.append("| method | best s | median s | GB/s | % of floor | docs | rejected | answer |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---|")
        table = []
        for name, runs in cells:
            timed = [r for r in runs if r["run"] > 0] or runs
            secs = [r["seconds"] for r in timed]
            best, med = min(secs), statistics.median(secs)
            gbs = timed[0]["bytes"] / best / 1e9
            last = runs[-1]
            docs = next((r["docs"] for r in runs if r.get("docs") is not None), None)
            table.append((best, f"| {name} | {best:.3f} | {med:.3f} | {gbs:.2f} | "
                                f"{100*gbs/floor_gbs:.0f}% | " if floor_gbs else f"| {name} | {best:.3f} | {med:.3f} | {gbs:.2f} | – | ",
                          docs, last.get("rejected"), check(last, ref)))
        for best, head, docs, rej, ans in sorted(table, key=lambda t: t[0]):
            out.append(f"{head}{'–' if docs is None else f'{docs:,}'} | {'–' if rej is None else f'{rej:,}'} | {ans} |")
        out.append("")
    if failed:
        out.append("FAILED: " + ", ".join(failed))
    return "\n".join(out)


def main():
    dirs = [Path(p) for p in sys.argv[1:]]
    d = dirs[0]
    parts = [f"# JSON parser benchmark: {', '.join(x.name for x in dirs)}\n"]
    for x in dirs:
        parts += ["```", (x / "env.txt").read_text().strip(), "```\n"]
    for name in ("multi", "onecore", "single"):  # "single" = the one-core pass in runs before 2026-10-04 21:00
        ps = [x / f"raw_{name}.jsonl" for x in dirs if (x / f"raw_{name}.jsonl").exists()]
        if ps:
            parts.append(f"## Pass: {name}\n")
            parts.append(summarise(ps))
    text = "\n".join(parts)
    (d / "report.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
