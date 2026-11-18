---
title: Validating JSONL line by line
summary: A JSONL file has no footer and no schema, so the only way to trust it is to parse every line. Here's how to find the broken ones fast.
formats: [jsonl]
kind: workflow
verbs: [count, diff]
published: 2026-11-18
verified_with: 0.5.12
try_it: |
  curl -LO https://rugo.dev/data/space_missions.jsonl
  rugo count space_missions.jsonl
---

JSON Lines is one JSON object per line, which makes it easy to write and easy to get subtly wrong: a crashed writer leaves a half-finished record, a stray log message lands in the middle, two producers disagree about a field. There is no footer to consult and no schema to check against. A JSONL file is valid when every line parses.

`rugo` parses every line whenever it reads a JSONL file, and when a line is bad it tells you which one. That makes `rugo count` a one-command validator. Install with `pip install rugo` and run the box above to get a sample file.

## A clean file

```bash
rugo count space_missions.jsonl; echo "exit code: $?"
```

```output
4630
exit code: 0
```

4,630 lines parsed, nothing wrong, exit code 0.

## A broken file

Build a copy with a truncated record on line 4 and a stray line on line 8:

```bash
{
  head -n 3 space_missions.jsonl
  echo '{"Company": "RVSN USSR", "Price":'
  sed -n '4,6p' space_missions.jsonl
  echo 'not json'
  sed -n '7p' space_missions.jsonl
} > broken.jsonl
rugo count broken.jsonl >/dev/null 2>&1; echo "exit code: $?"
```

```output
exit code: 1
```

The exit code is what a pipeline needs. The message is what a person needs:

```bash
rugo count broken.jsonl 2>&1 | tail -n 1
```

```output
ValueError: Malformed JSONL at line 4 (byte offset 696): '{"Company": "RVSN USSR", "Price":'
```

The line number is 1-based, and the byte offset is where that line starts (696 is the size of the three good lines before it), so you can jump straight to it with `sed -n 4p broken.jsonl` or an editor.

## Finding every bad line

`rugo` stops at the first malformed line, which is what you want in a gate: fail early, say where. When you're cleaning a file up and need the whole list, a few lines of Python give you every line at once:

```bash
python3 -c "
import json, sys
for n, line in enumerate(open(sys.argv[1], 'rb'), start=1):
    if line.strip():
        try:
            json.loads(line)
        except ValueError:
            print(f'line {n}: invalid JSON')
" broken.jsonl
```

```output
line 4: invalid JSON
line 8: invalid JSON
```

Drop those lines (or send them to a dead-letter file), and the rest of the file is good:

```bash
sed '4d;8d' broken.jsonl > fixed.jsonl
rugo count fixed.jsonl
```

```output
7
```

## What rugo lets through

Blank lines are skipped and the last line doesn't need a trailing newline, so neither will trip your validation:

```bash
{ head -n 2 space_missions.jsonl; echo; sed -n 3p space_missions.jsonl; } > spaced.jsonl
rugo count spaced.jsonl
```

```output
3
```

## Catching schema drift

Valid JSON can still be the wrong shape. `rugo diff` compares the schemas of two files and exits 1 when they differ. Here a producer starts sending a new `Crew` field on one record:

```bash
sed '3s/^{/{"Crew": 3, /' space_missions.jsonl > drifted.jsonl
rugo diff space_missions.jsonl drifted.jsonl; echo "exit code: $?"
```

```output
+ added:   Crew
exit code: 1
```

One record out of 4,630 was enough to show up. Run it between yesterday's file and today's and you'll hear about added and removed columns the day they appear.

## A validation gate for a folder

```bash
for f in *.jsonl; do
  rugo count "$f" >/dev/null 2>&1 || echo "invalid: $f"
done
```

```output
invalid: broken.jsonl
```

Swap the `echo` for `exit 1` and it's a CI step.
