---
# Copy this file, rename it (the filename becomes the URL: guides/my-guide.md ->
# rugo.dev/guides/my-guide/), fill it in, then run `python3 tools/build_guides.py`.
# Files starting with `_` are ignored.

title: Reading a Parquet footer with rugo info   # keep under ~60 characters
summary: One sentence for the card and the search-result snippet, ~150 characters.
formats: [parquet]            # parquet | jsonl | csv | avro | orc. Each one is a filter tab.
verbs: [info, inspect]        # the rugo commands the guide uses; shown on the card
kind: workflow                # optional: comparison | workflow. Adds a Comparisons/Workflows tab.
published: 2026-11-18
# updated: 2026-12-01         # optional
# reading_time: 4             # optional; minutes. Worked out from word count when omitted.
verified_with: 0.5.12         # the rugo release you ran tools/verify_guides.py against
viewer: false                 # true adds a link to the browser viewer (rugo.dev/viewer/) under "Try it"
# description: ...            # optional; defaults to `summary`. Used for <meta name="description">.
# draft: true                 # optional; keeps the guide out of the build

# Shown in the "Try it" box at the top of the page. Keep it short: download a sample,
# run the one command the guide is about.
try_it: |
  curl -LO https://rugo.dev/data/space_missions.parquet
  rugo info space_missions.parquet
---

Intro paragraph. Don't repeat the title as a `# ` heading: the page already has one.

## A step

Every ```bash block is run by `python3 tools/verify_guides.py`, in order, in an empty
directory. Put the expected output in an ```output block straight after it and the
verifier checks that too.

```bash
rugo info space_missions.parquet
```

```output
path        : space_missions.parquet
format      : parquet
size_bytes  : 93169
num_rows    : 4630
num_columns : 8
```
