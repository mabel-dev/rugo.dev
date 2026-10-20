#!/usr/bin/env python3
"""Draw the diagrams for the "Avro vs Parquet vs JSON Lines" post.

    uv run --with pillow python tools/build_format_diagrams.py

Each figure is hand-built SVG with its own dark background, so it reads the same
on rugo.dev and on Medium (which has no tables, no inline SVG and no dark mode).
The SVG is rendered to a PNG at 2x with headless Microsoft Edge, and the PNGs are
what the post links. File sizes come straight from docs/data; the Parquet column
chunk sizes and footer size were read from the file's own metadata with PyArrow
(`ParquetFile(...).metadata.row_group(0).column(i).total_compressed_size`), and
the Avro block count from fastavro's block_reader.
"""
import os, subprocess, tempfile, textwrap
from html import escape

from PIL import Image

EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA = f"{ROOT}/docs/data"
OUT = f"{ROOT}/docs/blog/img/avro-vs-parquet-vs-jsonl"

# Palette: the blog's own tokens. The three format colours passed
# validate_palette.js on the dark surface (CVD dE 9.1, normal-vision dE 24.3) and
# every mark is also labelled directly, so colour is never the only signal.
BG, SURFACE, BORDER = "#161920", "#0d0f14", "#252830"
TEXT, MUTED = "#e2e6f0", "#8a90a8"
SKIP = "#2a2f3a"
JSONL, AVRO, PARQUET = "#e8873a", "#4f8ef7", "#3ecf8e"
COLS = ["#8b7cf6", "#2fb7c9", "#e0607e"]  # A, B, C in the row/column figure
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
W = 760


def svg(height, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
            f'viewBox="0 0 {W} {height}" font-family="{SANS}">'
            f'<rect x="0.5" y="0.5" width="{W-1}" height="{height-1}" rx="12" fill="{BG}" stroke="{BORDER}"/>'
            f'{body}</svg>')


def rect(x, y, w, h, fill, stroke=None, rx=4, dash=False):
    s = f' stroke="{stroke}"' if stroke else ""
    d = ' stroke-dasharray="4 3"' if dash else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{s}{d}/>'


def text(x, y, s, size=13, fill=TEXT, weight=400, anchor="start", mono=False):
    fam = f' font-family="{MONO}"' if mono else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}"{fam}>{escape(s)}</text>')


def para(x, y, s, width, size=12.5, fill=MUTED, lead=18):
    lines = textwrap.wrap(s, width)
    return "".join(text(x, y + i * lead, ln, size, fill) for i, ln in enumerate(lines))


def line(x1, y1, x2, y2, color=MUTED, dash=True):
    d = ' stroke-dasharray="4 3"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.2"{d}/>'


def arrow(x1, y1, x2, y2, color=MUTED):
    return (line(x1, y1, x2, y2, color, dash=False)
            + f'<path d="M{x2-7},{y2-4.5} L{x2},{y2} L{x2-7},{y2+4.5}" fill="none" stroke="{color}" stroke-width="1.2"/>')


def title(t, sub=None):
    out = text(28, 40, t, 19, TEXT, 700)
    if sub:
        out += text(28, 62, sub, 13, MUTED)
    return out


# ── 1. Same data, three files ────────────────────────────────────────────────
def fig_sizes():
    sizes = {k: os.path.getsize(f"{DATA}/space_missions.{k}") for k in ("jsonl", "avro", "parquet")}
    top = sizes["jsonl"]
    rows = [("JSON Lines", JSONL, sizes["jsonl"]), ("Avro", AVRO, sizes["avro"]),
            ("Parquet", PARQUET, sizes["parquet"])]
    b = title("The same 4,630 launches, three files", "Bytes on disk, drawn to scale")
    x0, full = 150, 430
    for i, (name, color, n) in enumerate(rows):
        y = 96 + i * 52
        w = max(full * n / top, 3)
        b += text(28, y + 17, name, 14, TEXT, 600)
        b += rect(x0, y, w, 24, color, rx=4)
        label = f"{n/1e6:.2f} MB" if n >= 1e6 else f"{round(n/1e3)} KB"
        if i:
            label += f"  ·  {top/n:.1f}× smaller"
        b += text(x0 + w + 10, y + 17, label, 13.5, TEXT)
    b += text(28, 262, "JSON Lines as written, Avro with deflate, Parquet with zstd. Same rows, same fields.",
              12, MUTED)
    return svg(284, b), sizes


# ── 2. Row vs column ─────────────────────────────────────────────────────────
def fig_row_vs_col():
    b = title("Row-oriented or column-oriented", "Three records, three fields. The same values, stored in a different order.")
    names = ["Company", "Rocket", "Price"]
    cw, ch, x0, y0 = 92, 30, 28, 84
    for c, n in enumerate(names):
        b += text(x0 + c * (cw + 4) + cw / 2, y0 + 18, n, 12, MUTED, 600, "middle")
    for r in range(3):
        for c in range(3):
            x, y = x0 + c * (cw + 4), y0 + 26 + r * (ch + 4)
            b += rect(x, y, cw, ch, COLS[c])
            b += text(x + cw / 2, y + 20, f"{'ABC'[c]}{r+1}", 13, SURFACE, 700, "middle")
    b += para(364, y0 + 38, "Logically it is a table. On disk it has to become one long line of bytes, "
                            "and the order you pick decides which reads are cheap.", 46, 14, TEXT, 21)

    def strip(y, label, order, groups, glabels, note):
        s = text(70, y, label, 14, TEXT, 700)
        w, g, gg = 64, 3, 14
        x = (W - (3 * (3 * w + 2 * g) + 2 * gg)) / 2
        for gi in range(3):
            gx = x
            for cell in order[gi]:
                s += rect(x, y + 12, w, 34, COLS["ABC".index(cell[0])])
                s += text(x + w / 2, y + 34, cell, 13, SURFACE, 700, "middle")
                x += w + g
            s += text((gx + x - g) / 2, y + 66, glabels[gi], 12, MUTED, 400, "middle")
            x += gg - g
        s += text(70, y + 92, note, 12.5, MUTED)
        return s

    rows = [["A1", "B1", "C1"], ["A2", "B2", "C2"], ["A3", "B3", "C3"]]
    cols = [["A1", "A2", "A3"], ["B1", "B2", "B3"], ["C1", "C2", "C3"]]
    b += strip(262, "Row-oriented: JSON Lines, Avro", rows, 3, ["record 1", "record 2", "record 3"],
               "Adding a record is cheap. Reading one column means stepping through every record.")
    b += strip(392, "Column-oriented: Parquet", cols, 3, ["Company", "Rocket", "Price"],
               "Reading one column is one contiguous run. Skipping the others is free.")
    return svg(520, b)


# ── 3. JSON Lines anatomy ────────────────────────────────────────────────────
def fig_jsonl():
    b = title("JSON Lines: one record per line", "The first three rows of the dataset (4 of the 8 fields shown)")
    b += rect(28, 76, 704, 112, SURFACE, BORDER, rx=8)
    recs = [("RVSN USSR", "Sputnik 8K71PS", "null", "Success"),
            ("RVSN USSR", "Sputnik 8K71PS", "null", "Success"),
            ("US Navy", "Vanguard", "null", "Failure")]
    for i, (co, ro, pr, st) in enumerate(recs):
        y = 108 + i * 30
        b += text(46, y, str(i + 1), 12, MUTED, mono=True)
        k = lambda s: f'<tspan fill="{JSONL}">"{s}"</tspan>'
        v = lambda s: f'"{s}"'
        b += (f'<text x="72" y="{y}" font-size="12" font-family="{MONO}" fill="{TEXT}">'
              f'{{{k("Company")}:{v(co)},{k("Rocket")}:{v(ro)},{k("Price")}:<tspan fill="{MUTED}">{pr}</tspan>,'
              f'{k("Mission_Status")}:{v(st)}}}</text>')
    b += text(732 - 12, 204, "keys in orange", 11.5, MUTED, anchor="end")
    cards = [("Self-describing", "Every line carries its own keys, so any line can be read alone. "
                                 "The keys are also paid for 4,630 times."),
             ("Append-friendly", "A new record is a new line. There is no header to update and no footer to rewrite."),
             ("Everything is text", "Numbers, timestamps and nulls are strings to parse, "
                                    "and there is no schema to check them against.")]
    for i, (h, body) in enumerate(cards):
        x = 28 + i * 240
        b += rect(x, 224, 224, 128, BG, BORDER, rx=8)
        b += rect(x, 224, 224, 3, JSONL, rx=1.5)
        b += text(x + 14, 252, h, 14, TEXT, 700)
        b += para(x + 14, 274, body, 30, 12.5, MUTED, 18)
    return svg(376, b)


# ── 4. Avro anatomy ──────────────────────────────────────────────────────────
def fig_avro():
    b = title("Avro: a header, then blocks", "The sample file: 4,630 records in 29 blocks, about 160 records per block")
    y, h = 80, 44
    b += rect(28, y, 112, h, AVRO) + text(84, y + 27, "Header", 14, SURFACE, 700, "middle")
    xs = [144, 268, 392]
    for i, x in enumerate(xs):
        b += rect(x, y, 120, h, SURFACE, AVRO) + text(x + 60, y + 27, f"Block {i+1}", 13.5, TEXT, 600, "middle")
    b += text(528, y + 28, "…", 18, MUTED, 600, "middle")
    b += rect(544, y, 120, h, SURFACE, AVRO) + text(604, y + 27, "Block 29", 13.5, TEXT, 600, "middle")
    # connectors
    b += line(84, y + h, 84, 172) + line(452, y + h, 452, 172)
    # header detail
    b += rect(28, 172, 330, 204, BG, BORDER, rx=8) + rect(28, 172, 330, 3, AVRO, rx=1.5)
    b += text(44, 202, "Header: once per file", 14, TEXT, 700)
    items = [("magic", "Obj + version byte"), ("schema", "JSON: every field name and type"),
             ("codec", "deflate (or null, snappy, zstd…)"), ("sync marker", "16 random bytes")]
    for i, (k, v) in enumerate(items):
        yy = 232 + i * 30
        b += text(44, yy, k, 12.5, MUTED) + text(138, yy, v, 12.5, TEXT)
    b += para(44, 350, "The schema travels with the data, so the file explains itself.", 52, 12.5, MUTED, 18)
    # block detail
    b += rect(382, 172, 350, 204, BG, BORDER, rx=8) + rect(382, 172, 350, 3, AVRO, rx=1.5)
    b += text(398, 202, "Block: repeated", 14, TEXT, 700)
    parts = [("count", 52), ("size", 48), ("records, compressed", 150), ("sync", 52)]
    x = 398
    for name, w in parts:
        fill = SURFACE if name != "records, compressed" else "#1b2740"
        b += rect(x, 216, w, 36, fill, AVRO) + text(x + w / 2, 239, name, 11.5, TEXT, 500, "middle")
        x += w + 4
    b += para(398, 280, "Records sit back to back with no keys and no tags. The schema says what every byte means.",
              48, 12.5, MUTED, 18)
    b += para(398, 326, "Each block is compressed alone and ends with the sync marker, so a reader can "
                        "start at any block.", 48, 12.5, MUTED, 18)
    return svg(400, b)


# ── 5. Parquet anatomy ───────────────────────────────────────────────────────
CHUNKS = [("Company", 3108), ("Location", 5686), ("Price", 1759), ("Lauched_at", 37261),
          ("Rocket", 7579), ("Rocket_Status", 384), ("Mission", 34226), ("Mission_Status", 691)]
FOOTER = 1688
READ = {"Company", "Price", "Mission_Status"}


def fig_parquet():
    b = title("Parquet: column chunks, and a footer that maps them", "The sample file has one row group; larger files have many")
    y, h = 80, 44
    b += rect(28, y, 52, h, SURFACE, PARQUET) + text(54, y + 27, "PAR1", 12, TEXT, 600, "middle", True)
    b += rect(84, y, 170, h, SURFACE, PARQUET) + text(169, y + 27, "Row group 1", 13.5, TEXT, 600, "middle")
    b += rect(258, y, 170, h, SURFACE, PARQUET) + text(343, y + 27, "Row group 2", 13.5, TEXT, 600, "middle")
    b += text(452, y + 28, "…", 18, MUTED, 600, "middle")
    b += rect(476, y, 140, h, PARQUET) + text(546, y + 27, "Footer", 14, SURFACE, 700, "middle")
    b += rect(620, y, 112, h, SURFACE, PARQUET) + text(676, y + 27, "len · PAR1", 12, TEXT, 600, "middle", True)
    b += line(169, y + h, 169, 168) + line(546, y + h, 546, 340)
    # row group detail
    b += rect(28, 168, 704, 150, BG, BORDER, rx=8) + rect(28, 168, 704, 3, PARQUET, rx=1.5)
    b += text(44, 196, "Row group 1: one chunk per column", 14, TEXT, 700)
    b += text(716, 196, "each chunk is a run of compressed pages", 11.5, MUTED, anchor="end")
    cw, gap, x = 82, 4, 38
    for name, size in CHUNKS:
        sel = name in READ
        b += rect(x, 210, cw, 50, PARQUET if sel else SURFACE, None if sel else BORDER, dash=not sel)
        col = SURFACE if sel else MUTED
        parts = name.split("_")
        if len(parts) == 2 and len(name) > 11:
            b += text(x + cw / 2, 232, parts[0] + "_", 10.5, col, 600, "middle")
            b += text(x + cw / 2, 246, parts[1], 10.5, col, 600, "middle")
        else:
            b += text(x + cw / 2, 239, name, 10.5, col, 600, "middle")
        b += text(x + cw / 2, 276, f"{size/1000:.1f} KB", 11.5, TEXT if sel else MUTED, 500, "middle")
        x += cw + gap
    b += text(44, 304, "Filled: the three chunks a query for Company, Price and Mission_Status reads. "
                       "Dashed: never touched.", 12, MUTED)
    # footer detail
    b += rect(28, 340, 704, 112, BG, BORDER, rx=8) + rect(28, 340, 704, 3, PARQUET, rx=1.5)
    b += text(44, 368, "Footer: read first", 14, TEXT, 700)
    b += text(44, 394, "schema", 12.5, MUTED) + text(150, 394, "every column's name and type", 12.5, TEXT)
    b += text(44, 418, "per chunk", 12.5, MUTED) + text(150, 418, "byte offset · size · min · max · null count", 12.5, TEXT)
    b += text(44, 442, "for example", 12.5, MUTED) + text(150, 442, "Price: 1,759 bytes, min 2.5, max 450.0",
                                                          12.5, TEXT)
    return svg(472, b)


# ── 6. Reading three columns ─────────────────────────────────────────────────
def fig_reading(sizes):
    b = title("Reading 3 columns of 8", "")
    b += text(28, 62, "SELECT Company, Price, Mission_Status WHERE Company = 'SpaceX'", 12.5, MUTED, mono=True)
    x0, full = 28, 704
    for i, (name, color, size, pct, desc) in enumerate([
        ("JSON Lines", JSONL, sizes["jsonl"], "100% of the file",
         f"All {sizes['jsonl']:,} bytes are scanned. Fields you don't name are skipped, but every line is walked."),
        ("Avro", AVRO, sizes["avro"], "100% of the file",
         f"All {sizes['avro']:,} bytes: every one of the 29 blocks is inflated and walked."),
        ("Parquet", PARQUET, sizes["parquet"], None, None)]):
        base = 92 + i * 84
        b += text(28, base + 14, name, 14, TEXT, 700)
        if name != "Parquet":
            b += text(732, base + 14, pct, 13, TEXT, 600, "end")
            b += rect(x0, base + 22, full, 22, color) + text(28, base + 64, desc, 12, MUTED)
            continue
        total = size
        read_bytes = sum(s for n, s in CHUNKS if n in READ) + FOOTER + 8
        segs = [("magic", 4, False)] + [(n, s, n in READ) for n, s in CHUNKS]
        segs.append(("other", total - 4 - sum(s for _, s in CHUNKS) - FOOTER - 8, False))
        segs.append(("footer", FOOTER + 8, True))
        x = x0
        for n, s, sel in segs:
            w = full * s / total
            b += rect(x, base + 22, max(w - 2, 1.5), 22, PARQUET if sel else SKIP, rx=2 if w > 6 else 0)
            x += w
        b += text(732, base + 14, f"{read_bytes / total:.0%} of the file", 13, TEXT, 600, "end")
        b += text(28, base + 64, f"The footer, then 3 of 8 column chunks: {read_bytes:,} of {total:,} bytes. "
                                 "The rest is never read.", 12, MUTED)
    return svg(364, b)


# ── 7. Pipeline ──────────────────────────────────────────────────────────────
def fig_pipeline():
    b = title("A common shape: row formats in, Parquet at rest")

    def box(x, y, w, h, head, sub, color, wrap=26):
        return (rect(x, y, w, h, SURFACE, color, rx=8) + rect(x, y, 4, h, color, rx=2)
                + text(x + 18, y + 26, head, 14, TEXT, 700) + para(x + 18, y + 46, sub, wrap, 12, MUTED, 16))

    b += box(28, 112, 150, 72, "Producers", "apps, services, devices", MUTED, 22)
    b += box(232, 82, 190, 66, "Avro", "event streams, queues", AVRO)
    b += box(232, 164, 190, 66, "JSON Lines", "logs, API exports", JSONL)
    b += box(480, 112, 124, 72, "Parquet", "object storage", PARQUET)
    b += box(644, 112, 88, 72, "Reads", "queries", MUTED, 12)
    b += arrow(178, 136, 230, 115) + arrow(178, 160, 230, 197)
    b += arrow(422, 115, 478, 136) + arrow(422, 197, 478, 160)
    b += arrow(604, 148, 642, 148)
    b += text(232, 74, "append one record at a time", 12, MUTED)
    b += text(480, 104, "compact in batches", 12, MUTED)
    b += text(644, 202, "a few columns,", 12, MUTED) + text(644, 218, "many times", 12, MUTED)
    return svg(250, b)


def render(name, svg_text, tmp):
    page = f"{tmp}/{name}.html"
    open(page, "w", encoding="utf-8").write(
        f'<!doctype html><html><body style="margin:0;background:#fff">{svg_text}</body></html>')
    raw = f"{tmp}/{name}-raw.png"
    height = int(svg_text.split('height="')[1].split('"')[0])
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=2", f"--window-size={W},{height + 120}",
                    f"--screenshot={raw}", f"file://{page}"], check=True, capture_output=True)
    img = Image.open(raw).convert("RGB").crop((0, 0, W * 2, height * 2))
    dest = f"{OUT}/{name}.png"
    img.save(dest, optimize=True)
    print(f"{dest}  {img.width}x{img.height}")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    sizes_svg, sizes = fig_sizes()
    figs = [("fig-1-sizes", sizes_svg), ("fig-2-rows-vs-columns", fig_row_vs_col()),
            ("fig-3-jsonl", fig_jsonl()), ("fig-4-avro", fig_avro()), ("fig-5-parquet", fig_parquet()),
            ("fig-6-reading", fig_reading(sizes)), ("fig-7-pipeline", fig_pipeline())]
    with tempfile.TemporaryDirectory() as tmp:
        for name, s in figs:
            render(name, s, tmp)
