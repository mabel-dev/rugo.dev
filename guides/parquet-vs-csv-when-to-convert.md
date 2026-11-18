---
title: "Parquet vs CSV: when to convert"
summary: CSV is the file everyone can open. Parquet is the one your pipeline wants to read. Convert one file and see what changes.
formats: [parquet, csv]
kind: comparison
verbs: [convert, info, schema, describe, preview]
published: 2026-11-18
verified_with: 0.5.12
try_it: |
  curl -LO https://rugo.dev/data/space_missions.csv
  rugo convert space_missions.csv space_missions.parquet
---

CSV wins on reach: every spreadsheet, script and person can open it. Parquet wins on everything a program cares about: size, types, column access and metadata. You rarely have to choose, because `rugo convert` turns one into the other in a single command, in either direction, and it takes a fraction of a second on the 4,630-row sample used here.

Install with `pip install rugo`, run the box above, and compare the two files side by side.

## Convert

```bash
rugo convert space_missions.csv space_missions.parquet
```

```output
space_missions.csv (csv, 4630 rows) -> space_missions.parquet (parquet)
```

The destination format comes from the file extension: `.parquet`, `.csv`, `.jsonl` or `.avro`.

## Size

```bash
rugo info space_missions.csv | grep size_bytes
rugo info space_missions.parquet | grep size_bytes
```

```output
size_bytes  : 576263
size_bytes  : 88143
```

The Parquet file is **6.5x smaller**. Parquet stores each column together, so repeated values like `Company` and `Rocket_Status` compress far better than they can in a text file where every row repeats them in full.

## Types

CSV is text all the way down, so rugo reports every CSV column as `string`:

```bash
rugo schema space_missions.csv
```

```output
name            type    nullable
--------------  ------  --------
Company         string  True
Location        string  True
Price           string  True
Lauched_at      string  True
Rocket          string  True
Rocket_Status   string  True
Mission         string  True
Mission_Status  string  True
```

When it writes Parquet, `convert` gives numeric columns real types:

```bash
rugo schema space_missions.parquet
```

```output
name            type     nullable
--------------  -------  --------
Company         varchar  True
Location        varchar  True
Price           float64  True
Lauched_at      varchar  True
Rocket          varchar  True
Rocket_Status   varchar  True
Mission         varchar  True
Mission_Status  varchar  True
```

`Price` is now a `float64` that downstream code can sum without parsing. `Lauched_at` stays text, because a CSV can't say a column is a date. The ready-made [space_missions.parquet](/data/space_missions.parquet) keeps the same column as a real `timestamp[us]`.

## Metadata without reading the data

Parquet keeps column statistics in its footer, and `rugo describe` reads them from there:

```bash
rugo describe space_missions.parquet | grep -E '^(name|-|Price|Rocket_Status)'
```

```output
name            type     null_count  min               max               distinct_count
--------------  -------  ----------  ----------------  ----------------  --------------
Price           float64  3380        2.5               450.0             63
Rocket_Status   varchar  0           Active            Retired           2
```

Prices span 2.5 to 450.0 across 63 distinct values, 3,380 launches have no price, and `Rocket_Status` only ever holds two values. None of that needed a pass over the data.

CSV has no footer, so there is nothing to read:

```bash
rugo describe space_missions.csv 2>&1; echo "exit code: $?"
```

```output
rugo: error: 'space_missions.csv' is csv, not parquet — describe/stats/inspect read column statistics from the Parquet footer, which csv/jsonl don't have
exit code: 1
```

## Reading only the columns you need

Parquet stores columns separately, so a reader can fetch just the ones you ask for. `-c` projects them:

```bash
rugo preview space_missions.parquet -n 3 -c Company,Mission,Mission_Status
```

```output
Company    Mission       Mission_Status
---------  ------------  --------------
RVSN USSR  Sputnik-1     Success
RVSN USSR  Sputnik-2     Success
US Navy    Vanguard TV3  Failure
```

## Nothing is lost on the way

Convert back and compare. For this file the round trip is byte-for-byte identical:

```bash
rugo convert space_missions.parquet roundtrip.csv
cmp space_missions.csv roundtrip.csv && echo "round trip is byte-identical"
```

```output
space_missions.parquet (parquet, 4630 rows) -> roundtrip.csv (csv)
round trip is byte-identical
```

So converting is a decision about which file your pipeline reads, not a one-way door.

## When to convert

**Convert to Parquet when:**

- the file is read more than once, or by a program rather than a person;
- you only need some of the columns;
- size matters: storage, transfer, or cold-start time in a Lambda;
- you want typed columns and a footer you can check before reading.

**Keep CSV when:**

- people open it in a spreadsheet or edit it by hand;
- another system hands it to you and expects CSV back;
- it's a one-off you'll read once and throw away.

**The usual answer is both:** keep CSV at the edges where people and other systems touch the data, and convert to Parquet for everything in between. For how Parquet compares with Avro and JSONL, see [Avro vs Parquet vs JSONL](/blog/avro-vs-parquet-vs-jsonl.html).
