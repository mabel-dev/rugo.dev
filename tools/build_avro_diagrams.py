#!/usr/bin/env python3
"""Draw the diagrams for the "Understanding Avro" post.

    uv run --with pillow python tools/build_avro_diagrams.py

Same method as build_format_diagrams.py, whose palette and drawing helpers this
reuses: hand-built SVG on a dark background, rendered to a 2x PNG with headless
Microsoft Edge, so the figures read the same on rugo.dev and on Medium.

Every number comes from the file. docs/data/space_missions.avro is parsed here with
nothing but the spec (magic, metadata map, sync marker, blocks), and the first
record is cut out of the first block by inflating it. The codec sizes were measured
by re-writing the same 4,630 records with fastavro 1.13 at each codec's defaults;
see CODEC_SIZES.
"""
import os, struct, tempfile, zlib

from build_format_diagrams import (AVRO, BG, BORDER, MUTED, MONO, SANS, SURFACE, TEXT, arrow, line, para,
                                   rect, render as _render, svg, text, title)
import build_format_diagrams as base

ROOT = base.ROOT
DATA = base.DATA
OUT = f"{ROOT}/docs/blog/img/understanding-avro"
base.OUT = OUT

W = 760
CODEC_SIZES = [("none", 462688), ("snappy", 145591), ("zstd", 119517), ("bzip2", 113258),
               ("deflate", 112731), ("xz", 98731)]
AMBER, TEAL, ROSE, VIOLET = "#e8873a", "#2fb7c9", "#e0607e", "#8b7cf6"
AVRO_DARK = "#2f5db0"


# ── read the real file ───────────────────────────────────────────────────────
def varint(d, p):
    n = s = 0
    while True:
        b = d[p]
        p += 1
        n |= (b & 0x7F) << s
        s += 7
        if not b & 0x80:
            return (n >> 1) ^ -(n & 1), p


def read_avro_file(path):
    d = open(path, "rb").read()
    assert d[:4] == b"Obj\x01"
    p = 4
    count, p = varint(d, p)
    meta = {}
    for _ in range(abs(count)):
        kl, p = varint(d, p)
        k = d[p:p + kl].decode()
        p += kl
        vl, p = varint(d, p)
        meta[k] = d[p:p + vl]
        p += vl
    _, p = varint(d, p)  # end of map
    sync = d[p:p + 16]
    p += 16
    header_bytes = p
    blocks = []
    first = None
    while p < len(d):
        n, p = varint(d, p)
        size, p = varint(d, p)
        if first is None:
            first = zlib.decompress(d[p:p + size], -15)
        blocks.append((n, size))
        p += size + 16
    return dict(size=len(d), header=header_bytes, schema_len=len(meta["avro.schema"]), blocks=blocks, first=first)


FILE = read_avro_file(f"{DATA}/space_missions.avro")
RECORDS = sum(n for n, _ in FILE["blocks"])
JSONL_LINE = len(open(f"{DATA}/space_missions.jsonl", "rb").readline())


def first_record_fields():
    """Cut the first record into its fields using the schema, returning (name, bytes, note)."""
    b, p = FILE["first"], 0
    out = []

    def string():
        nonlocal p
        n, q = varint(b, p)
        s = b[q:q + n].decode()
        return s, q + n

    def take(name, note, start, end):
        out.append((name, b[start:end], note))

    for name in ("Company", "Location"):
        s, q = string()
        take(name, f'length {len(s)}, "{s if len(s) < 14 else s[:11] + "…"}"', p, q)
        p = q
    br, q = varint(b, p)
    take("Price", "branch 0: null", p, q)
    p = q
    br, q = varint(b, p)
    _, q2 = varint(b, q)
    take("Lauched_at", "branch 1, then a long", p, q2)
    p = q2
    s, q = string()
    take("Rocket.Name", f'length {len(s)}, "{s}"', p, q)
    p = q
    sym, q = varint(b, p)
    take("Rocket.Status", f"symbol {sym}: {['Active', 'Retired'][sym]}", p, q)
    p = q
    for name in ("Mission", "Mission_Status"):
        s, q = string()
        take(name, f'length {len(s)}, "{s}"', p, q)
        p = q
    return out


FIELDS = first_record_fields()
RECORD_BYTES = sum(len(f[1]) for f in FIELDS)


def hexs(bs, n=5):
    s = " ".join(f"{x:02x}" for x in bs[:n])
    return s + (" …" if len(bs) > n else "")


# ── 1. One record ────────────────────────────────────────────────────────────
def fig_record():
    b = title(f"One record, {RECORD_BYTES} bytes", f"The first launch in the sample file, cut out of the first block. "
                                                       f"The same launch is {JSONL_LINE} bytes as a JSON Lines row.")
    x0, y0, tw = 28, 84, 704
    scale = tw / RECORD_BYTES
    palette = [AVRO, AVRO_DARK]
    x = x0
    pos = []
    for i, (name, bs, note) in enumerate(FIELDS):
        w = len(bs) * scale
        b += rect(x, y0, w - 1.5, 30, palette[i % 2], rx=3)
        pos.append((x, w))
        x += w
    # field table
    yy = 168
    b += text(28, yy - 26, "field", 11.5, MUTED) + text(160, yy - 26, "bytes (hex)", 11.5, MUTED)
    b += text(360, yy - 26, "what they say", 11.5, MUTED) + text(732, yy - 26, "size", 11.5, MUTED, anchor="end")
    for i, (name, bs, note) in enumerate(FIELDS):
        y = yy + i * 26
        b += rect(28, y - 11, 10, 10, palette[i % 2], rx=2)
        b += text(46, y, name, 13, TEXT, 600)
        b += text(160, y, hexs(bs), 12.5, TEXT, mono=True)
        b += text(360, y, note, 12.5, MUTED)
        b += text(732, y, f"{len(bs)} B", 12.5, MUTED, anchor="end")
    h = yy + len(FIELDS) * 26 + 18
    b += line(28, h - 18, 732, h - 18, BORDER, dash=False)
    b += text(28, h + 6, "No field names. No quotes, colons or commas. Lengths come first, so a reader never "
                         "scans for a delimiter.", 12.5, MUTED)
    return svg(h + 30, b)


# ── 2. Zigzag and varint ─────────────────────────────────────────────────────
def fig_varint():
    b = title("Two tricks that make small numbers small", "Avro writes every int and long the same way")
    # left: zigzag
    b += rect(28, 84, 340, 308, BG, BORDER, rx=8) + rect(28, 84, 340, 3, AVRO, rx=1.5)
    b += text(44, 114, "1. Zigzag: signs stay out of the way", 14, TEXT, 700)
    b += para(44, 138, "A negative number written the usual way fills every byte. Zigzag interleaves "
                       "the signs, so small values stay small.", 46, 12.5, MUTED, 18)
    pairs = [(0, 0), (-1, 1), (1, 2), (-2, 3), (2, 4), (-64, 127), (63, 126)]
    b += text(44, 206, "value", 11.5, MUTED) + text(44, 226, "zigzag", 11.5, MUTED)
    cell = 44
    for i, (v, z) in enumerate(pairs[:5]):
        cx = 100 + i * (cell + 8)
        b += rect(cx, 190, cell, 44, SURFACE, AVRO)
        b += text(cx + cell / 2, 208, str(v), 13, TEXT, 600, "middle") + text(cx + cell / 2, 226, str(z), 13, AVRO, 600, "middle")
    for i, (v, z) in enumerate(pairs[5:]):
        cx = 100 + i * (cell + 8)
        b += rect(cx, 246, cell, 44, SURFACE, AVRO)
        b += text(cx + cell / 2, 264, str(v), 13, TEXT, 600, "middle") + text(cx + cell / 2, 282, str(z), 13, AVRO, 600, "middle")
    b += para(44, 322, "-64 to 63 land on 0 to 127, which is the range one byte can hold.", 50, 12.5, MUTED, 18)
    # right: varint
    b += rect(392, 84, 340, 308, BG, BORDER, rx=8) + rect(392, 84, 340, 3, AVRO, rx=1.5)
    b += text(408, 114, "2. Varint: 7 bits a byte", 14, TEXT, 700)
    b += para(408, 138, "The top bit of each byte says whether another byte follows.", 50, 12.5, MUTED, 18)
    rows = [("20", "40", [("28", "0 0101000")]),
            ("-1", "1", [("01", "0 0000001")]),
            ("300", "600", [("d8", "1 1011000"), ("04", "0 0000100")])]
    b += text(408, 190, "value", 11.5, MUTED) + text(468, 190, "zigzag", 11.5, MUTED) + text(536, 190, "bytes on disk", 11.5, MUTED)
    for i, (v, z, bs) in enumerate(rows):
        y = 218 + i * 42
        b += text(408, y + 4, v, 13, TEXT, 600) + text(468, y + 4, z, 13, MUTED)
        for j, (hx, bits) in enumerate(bs):
            bx = 536 + j * 96
            b += rect(bx, y - 17, 88, 36, SURFACE, AVRO)
            b += text(bx + 44, y - 2, hx, 13, TEXT, 600, "middle", mono=True) + text(bx + 44, y + 12, bits, 10, MUTED, anchor="middle", mono=True)
    b += para(408, 346, "Small values take one byte. Large ones grow as they need to.", 50, 12.5, MUTED, 18)
    return svg(416, b)


# ── 3. File anatomy ──────────────────────────────────────────────────────────
def fig_file():
    nb = len(FILE["blocks"])
    sizes = [s for _, s in FILE["blocks"]]
    counts = [n for n, _ in FILE["blocks"]]
    b = title("An Avro file, byte by byte", f"The sample file: {FILE['size']:,} bytes, a {FILE['header']}-byte header "
                                           f"and {nb} blocks")
    y, h = 84, 40
    b += rect(28, y, 110, h, AVRO) + text(83, y + 25, "Header", 14, SURFACE, 700, "middle")
    gap, dots = 6, 30
    bw = (732 - 142 - dots - 4 * gap) / 4
    xs = [142 + i * (bw + gap) for i in range(3)]
    for i, x in enumerate(xs):
        b += rect(x, y, bw, h, SURFACE, AVRO) + text(x + bw / 2, y + 25, f"Block {i+1}", 13.5, TEXT, 600, "middle")
    dx = xs[2] + bw + gap
    b += text(dx + dots / 2, y + 26, "…", 18, MUTED, 600, "middle")
    lx = dx + dots + gap
    b += rect(lx, y, bw, h, SURFACE, AVRO) + text(lx + bw / 2, y + 25, f"Block {nb}", 13.5, TEXT, 600, "middle")
    cx = xs[2] + bw / 2
    b += line(83, y + h, 83, 166) + line(cx, y + h, cx, 166)
    # header
    b += rect(28, 166, 330, 214, BG, BORDER, rx=8) + rect(28, 166, 330, 3, AVRO, rx=1.5)
    b += text(44, 196, "Header: once", 14, TEXT, 700)
    items = [("4 B", "magic", "O b j 01"),
             (f"{FILE['schema_len']} B", "avro.schema", "the schema, as JSON"),
             ("7 B", "avro.codec", "deflate"),
             ("16 B", "sync marker", "random, unique to this file")]
    for i, (sz, k, v) in enumerate(items):
        yy = 226 + i * 30
        b += text(44, yy, sz, 12.5, AVRO, 600) + text(100, yy, k, 12.5, MUTED) + text(190, yy, v, 12.5, TEXT)
    b += para(44, 352, f"The schema is most of it: {FILE['schema_len']} of {FILE['header']} bytes, "
                       f"{FILE['header'] / FILE['size']:.1%} of the file.", 52, 12.5, MUTED, 18)
    # block
    b += rect(382, 166, 350, 214, BG, BORDER, rx=8) + rect(382, 166, 350, 3, AVRO, rx=1.5)
    b += text(398, 196, "Block: repeated", 14, TEXT, 700)
    parts = [("count", 54), ("size", 48), ("records, compressed", 144), ("sync", 54)]
    x = 398
    for name, w in parts:
        fill = SURFACE if name != "records, compressed" else "#1b2740"
        b += rect(x, 210, w, 34, fill, AVRO) + text(x + w / 2, 232, name, 11.5, TEXT, 500, "middle")
        x += w + 4
    b += text(398, 266, f"Block 1: {counts[0]} records, {sizes[0]:,} bytes after deflate", 12.5, TEXT)
    b += para(398, 290, f"The {nb} blocks hold {min(counts)} to {max(counts)} records each. Count and size are "
                        "varints, and the sync marker repeats the header's.", 50, 12.5, MUTED, 18)
    b += para(398, 352, "A block is the unit of compression, of skipping ahead and of splitting.", 50, 12.5, MUTED, 18)
    return svg(400, b)


# ── 4. Codecs ────────────────────────────────────────────────────────────────
def fig_codecs():
    b = title("The same 4,630 records, six codecs", "Block-by-block compression, re-written with fastavro at each codec's defaults")
    base_size = CODEC_SIZES[0][1]
    x0, bw = 110, 460
    mx = base_size
    for i, (name, sz) in enumerate(CODEC_SIZES):
        y = 92 + i * 38
        w = max(4, bw * sz / mx)
        fill = MUTED if name == "none" else AVRO
        b += text(x0 - 14, y + 18, name, 13.5, TEXT, 600, "end" if False else "end")
        b += rect(x0, y, w, 26, fill, rx=3)
        label = f"{sz / 1000:,.0f} KB" if name == "none" else f"{sz / 1000:,.0f} KB  ·  {base_size / sz:.1f}× smaller"
        b += text(x0 + w + 10, y + 18, label, 12.5, TEXT if name != "null" else MUTED)
    b += text(28, 92 + len(CODEC_SIZES) * 38 + 22,
              "none = no compression. Every codec works on one block at a time, so any block can be read alone.",
              12, MUTED)
    return svg(92 + len(CODEC_SIZES) * 38 + 48, b)


# ── 5. Schema resolution ─────────────────────────────────────────────────────
def fig_evolution():
    b = title("Two schemas, one read", "The file was written last year. The reader asks for the schema it wants today.")

    def card(x, w, head, rows, color):
        out = rect(x, 84, w, 40 + len(rows) * 30, SURFACE, color, rx=8) + rect(x, 84, 4, 40 + len(rows) * 30, color, rx=2)
        out += text(x + 18, 108, head, 13.5, TEXT, 700)
        for i, (n, t, tag) in enumerate(rows):
            yy = 140 + i * 30
            out += text(x + 18, yy, n, 12.5, TEXT, 600, mono=True) + text(x + 108, yy, t, 12.5, MUTED, mono=True)
            if tag:
                out += text(x + w - 14, yy, tag, 12, color, 600, "end")
        return out

    b += card(28, 330, "Writer schema (in the file)", [("Company", "string", ""), ("Price", "[null, double]", "")], MUTED)
    b += card(402, 330, "Reader schema (in your code)",
              [("Company", "string", ""), ("Price", "[null, double]", ""), ("Crewed", "boolean = false", "new")], AVRO)
    b += arrow(358, 136, 400, 136)
    # result
    b += text(28, 262, "What the reader gets", 13.5, TEXT, 700)
    cells = [("Company", "from the file", MUTED), ("Price", "from the file", MUTED), ("Crewed", "the default: false", AVRO)]
    for i, (n, how, c) in enumerate(cells):
        x = 28 + i * 240
        b += rect(x, 274, 226, 46, SURFACE, c, rx=6)
        b += text(x + 14, 295, n, 13, TEXT, 600) + text(x + 14, 312, how, 12, MUTED)
    # rules
    b += text(28, 358, "What a reader schema may change", 13.5, TEXT, 700)
    ok = ["Add a field with a default", "Drop a field", "Rename a field (with an alias)", "Widen a number: int → long → float → double"]
    no = ["Add a field with no default", "Change string to int"]
    for i, r in enumerate(ok):
        x, y = 28 + (i % 2) * 358, 372 + (i // 2) * 28
        b += text(x, y + 15, "✓", 14, "#3ecf8e", 700) + text(x + 22, y + 15, r, 12.5, TEXT)
    for i, r in enumerate(no):
        x, y = 28 + (i % 2) * 358, 372 + 56 + (i // 2) * 28
        b += text(x, y + 15, "✗", 14, ROSE, 700) + text(x + 22, y + 15, r, 12.5, MUTED)
    return svg(466, b)


# ── 6. Reading a few fields ──────────────────────────────────────────────────
def fig_walk():
    b = title("Reading three fields of eight", "Records are packed back to back, so a reader has to walk past what it doesn't want")
    names = [f[0] for f in FIELDS]
    wanted = {"Company", "Price", "Mission_Status"}
    lens = [len(f[1]) for f in FIELDS]
    # equalise widths a little so tiny fields are visible
    widths = [max(l, 6) for l in lens]
    scale = 704 / sum(widths)
    for r in range(3):
        y = 104 + r * 46
        x = 28
        for n, w in zip(names, widths):
            ww = w * scale
            if n in wanted:
                b += rect(x, y, ww - 2, 34, AVRO, rx=3)
            else:
                b += rect(x, y, ww - 2, 34, SKIP_FILL, BORDER, rx=3)
            if r == 0 and n in wanted:
                last = n == names[-1]
                b += text(x + ww - 2 if last else x + 1, 96, n, 11.5, TEXT, 600, "end" if last else "start")
            x += ww
    b += text(28, 262, "3 records of the block, drawn to the width of their fields", 11.5, MUTED)
    b += rect(28, 282, 14, 14, AVRO, rx=3) + text(50, 294, "decoded and kept: Company, Price, Mission_Status", 12.5, TEXT)
    b += rect(28, 306, 14, 14, SKIP_FILL, BORDER, rx=3) + text(50, 318, "decoded just far enough to find where the next field starts", 12.5, MUTED)
    b += para(28, 356, "Strings carry a length, so a reader can hop over them. Numbers don't: it has to read bytes "
                       "until one has a clear top bit. Either way every byte of every block is inflated first, and "
                       "there are no statistics to say a block can be ignored.", 112, 12.5, MUTED, 18)
    return svg(420, b)


SKIP_FILL = "#2a2f3a"


# ── 7. Splitting ─────────────────────────────────────────────────────────────
def fig_split():
    b = title("Splitting a file without opening it", "Sync markers let any reader land mid-file and find its feet")
    x0, tw, y, h = 28, 704, 96, 44
    sizes = [s for _, s in FILE["blocks"]]
    total = FILE["header"] + sum(sizes) + 16 * len(sizes)
    scale = tw / total
    x = x0 + FILE["header"] * scale
    b += rect(x0, y, FILE["header"] * scale, h, AVRO, rx=2)
    for s in sizes:
        w = (s + 16 + 2) * scale
        b += rect(x, y, w - 1.2, h, SURFACE, AVRO, rx=2)
        b += rect(x + w - 3.2, y, 2, h, AMBER, rx=0)
        x += w
    b += text(x0, y - 10, "header", 11.5, MUTED) + text(732, y - 10, "each orange tick is a sync marker", 11.5, AMBER, anchor="end")
    colors = [VIOLET, TEAL, ROSE]
    share = tw / 3
    for i, c in enumerate(colors):
        ox = x0 + share * i
        b += line(ox, y + h, ox, 176, c, dash=False)
        b += rect(ox + 3, 176, share - 6, 5, c, rx=2)
        b += rect(ox + 3, 196, share - 6, 112, SURFACE, c, rx=8)
        b += text(ox + 18, 220, f"Worker {i+1}", 13.5, TEXT, 700)
        steps = ["start at byte " + (f"{int(total * i / 3):,}" if i else "0"),
                 "scan to the next sync marker" if i else "read the header",
                 "read blocks until its share ends"]
        for j, st in enumerate(steps):
            b += text(ox + 18, 244 + j * 20, st, 11.5, MUTED)
    b += para(28, 340, "The same trick lets a query engine fan one file out across workers, and lets a writer "
                       "append: add blocks after the last one, with the header's sync marker.", 112, 12.5, MUTED, 18)
    return svg(386, b)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    figs = [("fig-1-record", fig_record()), ("fig-2-varint", fig_varint()), ("fig-3-file", fig_file()),
            ("fig-4-codecs", fig_codecs()), ("fig-6-evolution", fig_evolution()), ("fig-7-walk", fig_walk()),
            ("fig-5-split", fig_split())]
    with tempfile.TemporaryDirectory() as tmp:
        for name, s in figs:
            _render(name, s, tmp)
