#!/usr/bin/env python3
"""Render every table in a rugo.dev blog post to a PNG, for Medium.

    uv run --with pillow python tools/medium_table_images.py docs/blog/<post>.html <out_dir>

Medium has no tables: a story imported from rugo.dev keeps its headings, text and
code, but each table has to go back in as an image. This renders each
`<div class="table-scroll">` in the post on its own page with the blog's own
stylesheet (headless Microsoft Edge, 2x scale), trims the empty background, and
writes <out_dir>/table-1.png, table-2.png, ... in page order, printing which
section each one belongs under.
"""
import os, re, subprocess, sys, tempfile

from PIL import Image

EDGE = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
DOCS = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs"))
PAD = 32  # px of background kept round the table, at 2x scale

post, out = sys.argv[1], sys.argv[2]
html = open(post, encoding="utf-8").read()
os.makedirs(out, exist_ok=True)

# Each table with the last <h2> above it, so the caller knows where it goes.
tables = []
for m in re.finditer(r'<div class="table-scroll">.*?</table>\s*</div>', html, re.S):
    headings = re.findall(r"<h2>(.*?)</h2>", html[: m.start()], re.S)
    tables.append((headings[-1].strip() if headings else "(top)", m.group(0)))
if not tables:
    sys.exit(f"no tables in {post}")

with tempfile.TemporaryDirectory() as tmp:
    for n, (section, table) in enumerate(tables, 1):
        page = f"{tmp}/table-{n}.html"
        with open(page, "w", encoding="utf-8") as f:
            f.write(f"""<!doctype html><html><head><meta charset="UTF-8">
<link rel="stylesheet" href="file://{DOCS}/blog.css">
<style>body{{padding:16px}} .table-scroll{{overflow:visible;margin:0}}</style>
</head><body>{table}</body></html>""")
        raw = f"{tmp}/raw-{n}.png"
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=2", "--window-size=760,1600",
                        f"--screenshot={raw}", f"file://{page}"],
                       check=True, capture_output=True)
        img = Image.open(raw).convert("RGB")
        bg = img.getpixel((0, 0))
        diff = [(x, y) for y in range(0, img.height, 2) for x in range(0, img.width, 4)
                if img.getpixel((x, y)) != bg]
        if not diff:
            sys.exit(f"table {n} rendered empty")
        x0 = max(min(x for x, _ in diff) - PAD, 0)
        y0 = max(min(y for _, y in diff) - PAD, 0)
        x1 = min(max(x for x, _ in diff) + PAD, img.width)
        y1 = min(max(y for _, y in diff) + PAD, img.height)
        dest = f"{out}/table-{n}.png"
        img.crop((x0, y0, x1, y1)).save(dest)
        print(f"{dest}  ->  under '{section}'")
