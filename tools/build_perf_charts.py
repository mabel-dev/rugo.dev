#!/usr/bin/env python3
"""Render the Performance section's charts into docs/index.html from the results files.

    python3 tools/build_perf_charts.py

Each chart in CHARTS is drawn between `<!-- chart:<id> -->` and `<!-- /chart:<id> -->`
markers in docs/index.html, replacing whatever is there. Every number comes from a
file in benchmarks/results/ (best-of-N `best_ms`), so the page can't drift from what
was measured: re-run a benchmark, point CHARTS at the new file, re-run this.

The form (ruled 2026-10-16): big headline multiples over horizontal bars on a LINEAR
scale - one scale per chart, shared by all its bars, so lengths compare honestly; the
fastest bar of each group in the win colour (rugo is always listed first), every other
bar muted; the value printed at each bar's end.
Plain HTML and CSS, no script.
"""
import html, json, os, re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RESULTS = os.path.join(ROOT, "benchmarks", "results")
PAGE = os.path.join(ROOT, "docs", "index.html")


def load(name):
    with open(os.path.join(RESULTS, name)) as f:
        return json.load(f)


def ms(value):
    """~76 ms / ~1.24 s, as the page has always written times."""
    if value >= 1000:
        return f"~{value / 1000:.2f} s"
    if value >= 100:
        return f"~{value:.0f} ms"
    if value >= 10:
        return f"~{value:.0f} ms"
    return f"~{value:.1f} ms"


def times(ratio):
    return f"{ratio:.0f}×" if ratio >= 10 else f"{ratio:.1f}×"


# A chart: results section, groups of (label, [(name, key, is_rugo)]), and headline
# tiles of (big, label). `big` is literal text, ("ratio", a, b) = value(a) / value(b) as
# "N×", or ("time", key) = that result's time. `label` is literal text, or
# ("gap", [(rugo_key, other_key), ...], template): the template with {gap} = the widest
# |rugo - other| over the pairs, in whole ms.
CHARTS = [
    {
        "id": "jsonl-read", "file": "2026-10-25.json", "section": "queries",
        "groups": [
            ("SELECT 1 column", [("Rugo", "jsonl/select1/rugo", True), ("PyArrow", "jsonl/select1/pyarrow", False)]),
            ("WHERE ~10% pass", [("Rugo", "jsonl/p10/rugo", True), ("PyArrow", "jsonl/p10/pyarrow", False)]),
            ("WHERE ~1% pass", [("Rugo", "jsonl/p1/rugo", True), ("PyArrow", "jsonl/p1/pyarrow", False)]),
            ("SELECT *", [("Rugo", "jsonl/select_star/rugo", True), ("PyArrow", "jsonl/select_star/pyarrow", False)]),
        ],
        "tiles": [
            (("ratio", "jsonl/p10/pyarrow", "jsonl/p10/rugo"), "faster than PyArrow, filtered to ~10%"),
            (("ratio", "jsonl/select1/pyarrow", "jsonl/select1/rugo"), "faster, one column of 110"),
            (("ratio", "jsonl/select_star/pyarrow", "jsonl/select_star/rugo"), "faster, every column"),
        ],
    },
    {
        "id": "avro-read", "file": "2026-10-11-avro.json", "section": "reads",
        "groups": [
            ("Every field", [("Rugo", "all/rugo", True), ("Rugo → Python", "all/rugo+pylist", True),
                             ("fastavro", "all/fastavro", False), ("avro (Apache)", "all/avro", False)]),
            ("3 of 20 fields", [("Rugo", "narrow/rugo", True), ("Rugo → Python", "narrow/rugo+pylist", True),
                                ("fastavro", "narrow/fastavro", False), ("avro (Apache)", "narrow/avro", False)]),
        ],
        "tiles": [
            (("ratio", "all/fastavro", "all/rugo"), "faster than fastavro"),
            (("ratio", "all/avro", "all/rugo"), "faster than avro (Apache)"),
        ],
    },
    {
        "id": "avro-write", "file": "2026-10-16-avro-write.json", "section": "writes",
        "groups": [
            ("deflate", [("Rugo", "deflate/rugo", True), ("Rugo, 1 thread", "deflate/rugo-1t", True),
                         ("fastavro", "deflate/fastavro", False), ("avro (Apache)", "deflate/avro", False)]),
            ("zstandard", [("Rugo", "zstandard/rugo", True), ("Rugo, 1 thread", "zstandard/rugo-1t", True),
                           ("fastavro", "zstandard/fastavro", False), ("avro (Apache)", "zstandard/avro", False)]),
            ("Uncompressed", [("Rugo", "null/rugo", True), ("Rugo, 1 thread", "null/rugo-1t", True),
                              ("fastavro", "null/fastavro", False), ("avro (Apache)", "null/avro", False)]),
        ],
        "tiles": [
            (("ratio", "deflate/fastavro", "deflate/rugo"), "faster than fastavro"),
            (("ratio", "deflate/avro", "deflate/rugo"), "faster than avro (Apache)"),
            (("ratio", "deflate/fastavro", "deflate/rugo-1t"), "faster than fastavro on one thread"),
        ],
    },
]


WRITES = "2026-10-25-writes-0.9.173.json"
CHARTS += [
    {
        "id": "parquet-write", "file": WRITES, "section": "writes",
        "groups": [(None, [("Rugo", "parquet/rugo", True), ("Rugo (fast write)", "parquet/rugo-fast", True),
                                      ("polars", "parquet/polars", False),
                                      ("DuckDB", "parquet/duckdb", False), ("PyArrow", "parquet/pyarrow", False),
                                      ("fastparquet", "parquet/fastparquet", False)])],
        "tiles": [
            (("ratio", "parquet/pyarrow", "parquet/rugo"), "faster than PyArrow"),
            (("ratio", "parquet/duckdb", "parquet/rugo"), "faster than DuckDB"),
            (("ratio", "parquet/fastparquet", "parquet/rugo"), "faster than fastparquet"),
        ],
    },
    {
        "id": "jsonl-write", "file": WRITES, "section": "writes",
        "groups": [(None, [("Rugo", "jsonl/rugo", True), ("polars", "jsonl/polars", False),
                              ("DuckDB", "jsonl/duckdb", False), ("Python (json)", "jsonl/python", False)])],
        "tiles": [
            (("ratio", "jsonl/python", "jsonl/rugo"), "faster than Python's json module"),
            (("ratio", "jsonl/duckdb", "jsonl/rugo"), "faster than DuckDB"),
        ],
    },
]


# Parquet reads (benchmarks/measure_parquet.py). Key: <threads>/<file>/<query>/<library>.
PARQUET_READ = "2026-10-25-parquet-read-0.5.5.json"
LIBS = [("Rugo", "rugo", True), ("DuckDB", "duckdb", False), ("polars", "polars", False), ("PyArrow", "pyarrow", False)]


def parquet_groups(threads):
    shapes = [("SELECT 2 columns", "wide/select2"), ("WHERE ~10% pass", "wide/unsorted_p10"),
              ("WHERE ~1% pass", "wide/unsorted_p1"), ("SELECT * — 4 columns", "narrow/full"),
              ("count(*)", "wide/count")]
    return [(label, [(name, f"{threads}/{q}/{lib}", rugo) for name, lib, rugo in LIBS]) for label, q in shapes]


CHARTS += [
    {
        "id": "parquet-read", "file": PARQUET_READ, "section": "queries",
        "groups": parquet_groups("all"),
        "tiles": [
            (("ratio", "all/narrow/full/duckdb", "all/narrow/full/rugo"), "faster than DuckDB on a full read"),
            (("ratio", "all/wide/count/duckdb", "all/wide/count/rugo"), "faster than DuckDB on count(*)"),
            (("ratio", "all/wide/select2/pyarrow", "all/wide/select2/rugo"), "faster than PyArrow, 2 of 100 columns"),
        ],
    },
    {
        "id": "parquet-read-1t", "file": PARQUET_READ, "section": "queries",
        "groups": parquet_groups("1"),
        "tiles": [
            (("ratio", "1/wide/select2/duckdb", "1/wide/select2/rugo"), "faster than DuckDB on one thread"),
            (("ratio", "1/narrow/full/pyarrow", "1/narrow/full/rugo"), "faster than PyArrow, full read, one thread"),
            ("Parity", ("gap", [("1/wide/select2/rugo", "1/wide/select2/polars"), ("1/narrow/full/rugo", "1/narrow/full/polars")],
                        "with polars on 2-column and full reads — within {gap} ms")),
        ],
    },
]


def render(chart):
    data = load(chart["file"])[chart["section"]]
    value = lambda key: data[key]["best_ms"]
    top = max(value(k) for _, bars in chart["groups"] for _, k, _ in bars)
    out = ['<div class="bench">', '<div class="bench-big">']
    for big, label in chart["tiles"]:
        tone = ""  # a multiple or a parity claim is a win (green); a plain time is not
        if type(big) is tuple and big[0] == "ratio":
            big = times(value(big[1]) / value(big[2]))
        elif type(big) is tuple and big[0] == "time":
            big = ms(value(big[1]))
            tone = " is-plain"
        if type(label) is tuple:
            _, pairs, template = label
            gap = max(abs(value(a) - value(b)) for a, b in pairs)
            label = template.format(gap=f"{gap:.0f}")
        out.append(f'<div class="big"><span class="big-n{tone}">{html.escape(big)}</span>'
                   f'<span class="big-l">{html.escape(label)}</span></div>')
    out.append("</div>")
    for label, bars in chart["groups"]:
        # A chart of one group is titled on the page; its group needs no label of its own.
        shape = "" if label is None else f'<div class="bench-shape">{html.escape(label)}</div>'
        out.append(f'<div class="bench-group">{shape}')
        # The win colour marks the fastest bar of each group, whoever it is (a tie at the
        # printed precision marks both); rugo is always listed first.
        fastest = ms(min(value(k) for _, k, _ in bars))
        for name, key, rugo in bars:
            v = value(key)
            win = " is-rugo" if ms(v) == fastest else ""
            us = " is-us" if rugo else ""  # rugo's own rows read brighter even when they don't win
            width = max(0.4, v / top * 78)  # the longest bar leaves room for its value
            out.append(
                f'<div class="bar-row" title="{html.escape(name)}: {ms(v)}">'
                f'<span class="bar-name{us}">{html.escape(name)}</span>'
                f'<span class="bar-track"><span class="bar{win}{us}" style="width:{width:.2f}%"></span>'
                f'<span class="bar-val{win}">{ms(v)}</span></span></div>')
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


def main():
    with open(PAGE) as f:
        page = f.read()
    for chart in CHARTS:
        cid = chart["id"]
        pattern = re.compile(rf"(<!-- chart:{re.escape(cid)} -->)(.*?)(<!-- /chart:{re.escape(cid)} -->)", re.S)
        if len(pattern.findall(page)) != 1:
            raise SystemExit(f"docs/index.html needs exactly one <!-- chart:{cid} --> ... <!-- /chart:{cid} --> pair")
        page = pattern.sub(lambda m: m.group(1) + "\n" + render(chart) + "\n" + m.group(3), page)
        print("rendered", cid)
    with open(PAGE, "w") as f:
        f.write(page)


if __name__ == "__main__":
    main()
