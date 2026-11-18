---
title: Reading a Parquet footer with rugo info
summary: Row count, schema and per-column statistics sit in the last few KB of a Parquet file. Read them without touching the data.
formats: [parquet]
verbs: [info, schema, inspect, describe]
published: 2026-11-18
verified_with: 0.5.12
viewer: true
try_it: |
  curl -LO https://rugo.dev/data/space_missions.parquet
  rugo info space_missions.parquet
---

A Parquet file ends with a **footer**: the schema, the row groups, and for every column the null count and min/max values. Everything you want to know before you read a file is already in there, in the last couple of kilobytes. `rugo info`, `schema`, `inspect` and `describe` read that footer and nothing else, so you can check a file without paying to read it.

The examples use 4,630 orbital launches, from Sputnik onwards. Install rugo with `pip install rugo`, run the box above, and follow along.

## The one-minute summary: rugo info

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

Pass `--json` when a script is reading it:

```bash
rugo info --json space_missions.parquet
```

```output
{
  "path": "space_missions.parquet",
  "format": "parquet",
  "size_bytes": 93169,
  "num_rows": 4630,
  "num_columns": 8
}
```

## The schema

```bash
rugo schema space_missions.parquet
```

```output
name            type           nullable
--------------  -------------  --------
Company         varchar        True
Location        varchar        True
Price           float64        True
Lauched_at      timestamp[us]  True
Rocket          varchar        True
Rocket_Status   varchar        True
Mission         varchar        True
Mission_Status  varchar        True
```

(`Lauched_at` is spelled that way in the source dataset. The footer records column names exactly as they were written.)

## What the footer looks like on disk

The last eight bytes of every Parquet file are a 4-byte footer length followed by the magic bytes `PAR1`. A reader starts there and works backwards:

```bash
python3 -c "
import struct
data = open('space_missions.parquet', 'rb').read()
print('footer:', struct.unpack('<I', data[-8:-4])[0], 'bytes of', len(data))
print('magic :', data[-4:])
"
```

```output
footer: 1688 bytes of 93169
magic : b'PAR1'
```

All of the metadata above fits in 1,688 bytes: 1.8% of the file.

## Row groups and column statistics: rugo inspect

```bash
rugo inspect space_missions.parquet
```

```output
path            : space_missions.parquet
size_bytes      : 93169
num_rows        : 4630
num_row_groups  : 1

schema:
name            type           nullable
--------------  -------------  --------
Company         varchar        True
Location        varchar        True
Price           float64        True
Lauched_at      timestamp[us]  True
Rocket          varchar        True
Rocket_Status   varchar        True
Mission         varchar        True
Mission_Status  varchar        True

row group 0  (rows=4630):
name            physical_type  logical_type   null_count  distinct_count  bloom  min/max
--------------  -------------  -------------  ----------  --------------  -----  -------
Company         byte_array     varchar        0                           False  True
Location        byte_array     varchar        0                           False  True
Price           float64        float64        3380                        False  True
Lauched_at      int64          timestamp[us]  127                         False  True
Rocket          byte_array     varchar        0                           False  True
Rocket_Status   byte_array     varchar        0                           False  True
Mission         byte_array     varchar        0                           False  True
Mission_Status  byte_array     varchar        0                           False  True
```

Reading it:

- **One row group**, holding all 4,630 rows. Larger files have many, and each one carries its own statistics, which is what lets a reader skip row groups that can't match a filter.
- **`physical_type` vs `logical_type`**: how the bytes are stored versus what they mean. `Lauched_at` is stored as an `int64` and means `timestamp[us]`.
- **`null_count`**: `Price` is empty on 3,380 of 4,630 rows (73%). You've learned that without reading a single value.
- **`min/max`**: `True` means the footer holds a minimum and maximum for that column.

## The statistics themselves: rugo describe

```bash
rugo describe space_missions.parquet
```

```output
name            type           null_count  min                                              max                                     distinct_count
--------------  -------------  ----------  -----------------------------------------------  --------------------------------------  --------------
Company         varchar        0           AEB                                              i-Space
Location        varchar        0           Blue Origin Launch Site, West Texas, Texas, USA  Xichang Satellite Launch Center, China
Price           float64        3380        2.5                                              450.0
Lauched_at      timestamp[us]  127         -386310720000000                                 1659101280000000
Rocket          varchar        0           ASLV                                             Zoljanah
Rocket_Status   varchar        0           Active                                           Retired
Mission         varchar        0           -TJS_6.00                                        iPStar-1
Mission_Status  varchar        0           Failure                                          Success
```

Prices run from 2.5 to 450.0. Timestamp bounds are shown as raw microseconds since 1970-01-01, so the minimum is negative: it is the first launch in the file.

```bash
python3 -c "
from datetime import datetime, timedelta, timezone
print(datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=-386310720000000))
"
```

```output
1957-10-04 19:28:00+00:00
```

Sputnik 1, on the day it launched.

## Proof that it never reads the data

Zero out most of the file, everything between the 4-byte header and the footer, and keep the footer intact:

```bash
python3 -c "
data = bytearray(open('space_missions.parquet', 'rb').read())
data[4:80000] = bytes(79996)
open('hollow.parquet', 'wb').write(data)
"
rugo info hollow.parquet
```

```output
path        : hollow.parquet
format      : parquet
size_bytes  : 93169
num_rows    : 4630
num_columns : 8
```

The footer commands don't notice. Asking for the rows themselves does:

```bash
rugo preview hollow.parquet -n 2 >/dev/null 2>&1; echo "preview exit code: $?"
```

```output
preview exit code: 1
```

## When to reach for this

- **Triage a pile of files.** Row count, size and schema for each one, without paying to read any of them.
- **Gate a pipeline.** `rugo info --json` and compare `num_rows` and the schema against what you expect before loading.
- **Plan a query.** `null_count` and `min/max` tell you which columns are worth reading and which row groups can be skipped.

Next: [Parquet vs CSV: when to convert](/guides/parquet-vs-csv-when-to-convert/).
