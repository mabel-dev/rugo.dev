# JSON parser benchmark: 20261005T125024Z

```
stamp: 20261005T125024Z
layout: single
files: 42
workloads: parse filter_hi filter_lo minmax freq_lo freq_hi filter_agg deep langs
repeat: 5 (+1 warm-up)
threads: 18
Darwin Justins-MacBook-Pro.local 25.6.0 Darwin Kernel Version 25.6.0: Fri Jul 31 19:19:08 PDT 2026; root:xnu-12377.161.14~5/RELEASE_ARM64_T6050 arm64
Apple M5 Pro
cxx: Apple clang version 21.0.0 (clang-2100.3.34.2)
cc: Apple clang version 21.0.0 (clang-2100.3.34.2)
flags: -O3 -DNDEBUG -mcpu=native -std=c++20 -pthread -Icpp -Ideps/unordered_dense/include
sonic_flags: 
simdjson: v5.0.2 c9030726ebbf5f9fe9f9facb4a401f6d3ccd77a2
yyjson: 0.13.0 6447536015f3d600f3d65323b10976103b337ca7
sonic: v1.0.2 f5d0117adbe4fb3b9f8a2d6f24155119527a2ddd
unordered_dense: v5.3.1 c164976d1426d623d87b98833ff60c7263fde4e1
rugo (opteryx-core): /Users/justin/Nextcloud/opteryx-core opteryx-0.9.153-8-g7b40af35-dirty 7b40af35e48dcabf65b990c1cfb220f26cd564fd
python 3.14.5 | opteryx 0.9.155 | rugo 0.4.42
data manifest sha256: 9aa655fe13ccb687
```

## Pass: multi

Floor (count newlines over the same mmap'd chunks, same threads): 0.461 s, 43.9 GB/s over 20.23 GB in 1 files

### parse: full parse of every document, nothing extracted

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| yyjson dom | 0.666 | 0.679 | 30.38 | 69% | 41,999,994 | 6 | ok |
| simdjson dom | 0.667 | 0.675 | 30.31 | 69% | 41,999,994 | 6 | ok |
| simdjson dom-st | 0.681 | 0.697 | 29.71 | 68% | 41,999,994 | 6 | ok |
| rugo chunked | 0.971 | 1.067 | 20.82 | 47% | 41,999,994 | 6 | ok |
| sonic-cpp dom | 1.483 | 1.485 | 13.63 | 31% | 41,999,994 | 6 | ok |

### filter_hi: did of rows where commit.collection = 'app.bsky.feed.like' (~45% of rows)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand | 0.659 | 0.666 | 30.69 | 70% | 41,999,994 | 6 | ok |
| simdjson ondemand-st | 0.664 | 0.685 | 30.47 | 69% | 41,999,994 | 6 | ok |
| simdjson dom | 0.795 | 0.821 | 25.45 | 58% | 41,999,994 | 6 | ok |
| yyjson dom | 0.835 | 0.837 | 24.22 | 55% | 41,999,994 | 6 | ok |
| simdjson dom-st | 0.844 | 0.858 | 23.98 | 55% | 41,999,994 | 6 | ok |
| sonic-cpp ondemand | 0.890 | 0.895 | 22.72 | 52% | 42,000,000 | 0 | ok |
| opteryx sql | 1.005 | 1.022 | 20.12 | 46% | 41,999,994 | – | ok |
| rugo chunked | 1.098 | 1.110 | 18.42 | 42% | – | 6 | ok |
| sonic-cpp dom | 1.853 | 1.906 | 10.92 | 25% | 41,999,994 | 6 | ok |

### filter_lo: did of rows where commit.collection = 'app.bsky.graph.block' (~1.4% of rows)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| opteryx sql | 0.461 | 0.465 | 43.83 | 100% | 41,999,994 | – | ok |
| rugo chunked | 0.475 | 0.477 | 42.61 | 97% | – | 6 | ok |
| simdjson ondemand | 0.621 | 0.637 | 32.58 | 74% | 41,999,994 | 6 | ok |
| simdjson ondemand-st | 0.627 | 0.632 | 32.24 | 74% | 41,999,994 | 6 | ok |
| sonic-cpp ondemand | 0.696 | 0.708 | 29.07 | 66% | 42,000,000 | 0 | ok |
| simdjson dom | 0.776 | 0.791 | 26.06 | 59% | 41,999,994 | 6 | ok |
| yyjson dom | 0.784 | 0.792 | 25.80 | 59% | 41,999,994 | 6 | ok |
| simdjson dom-st | 0.800 | 0.810 | 25.29 | 58% | 41,999,994 | 6 | ok |
| sonic-cpp dom | 1.560 | 1.614 | 12.97 | 30% | 41,999,994 | 6 | ok |

### minmax: MIN and MAX of time_us

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| sonic-cpp ondemand | 0.586 | 0.608 | 34.50 | 79% | 41,999,997 | 3 | ok |
| simdjson ondemand-st | 0.601 | 0.603 | 33.65 | 77% | 41,999,994 | 6 | ok |
| simdjson ondemand | 0.604 | 0.618 | 33.48 | 76% | 41,999,994 | 6 | ok |
| rugo chunked | 0.728 | 0.739 | 27.79 | 63% | 41,999,994 | 6 | ok |
| yyjson dom | 0.731 | 0.732 | 27.68 | 63% | 41,999,994 | 6 | ok |
| simdjson dom | 0.747 | 0.763 | 27.07 | 62% | 41,999,994 | 6 | ok |
| simdjson dom-st | 0.766 | 0.776 | 26.42 | 60% | 41,999,994 | 6 | ok |
| opteryx sql | 0.777 | 0.785 | 26.04 | 59% | 41,999,994 | – | ok |
| sonic-cpp dom | 1.308 | 1.543 | 15.46 | 35% | 41,999,994 | 6 | ok |

### freq_lo: count per commit.collection (~20 distinct values)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.591 | 0.610 | 34.20 | 78% | 41,999,994 | 6 | ok |
| simdjson ondemand | 0.605 | 0.611 | 33.43 | 76% | 41,999,994 | 6 | ok |
| sonic-cpp ondemand | 0.687 | 0.704 | 29.44 | 67% | 42,000,000 | 0 | DIFF |
| yyjson dom | 0.725 | 0.740 | 27.91 | 64% | 41,999,994 | 6 | ok |
| simdjson dom | 0.737 | 0.740 | 27.45 | 63% | 41,999,994 | 6 | ok |
| opteryx sql | 0.755 | 0.759 | 26.79 | 61% | 41,999,994 | – | ok |
| simdjson dom-st | 0.756 | 0.775 | 26.75 | 61% | 41,999,994 | 6 | ok |
| rugo chunked | 0.904 | 0.909 | 22.36 | 51% | 41,999,994 | 6 | ok |
| sonic-cpp dom | 1.559 | 1.592 | 12.97 | 30% | 41,999,994 | 6 | ok |

### freq_hi: count per did (millions of distinct values)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| opteryx sql | 0.708 | 0.727 | 28.56 | 65% | 41,999,994 | – | ok |
| sonic-cpp ondemand | 0.762 | 0.986 | 26.53 | 60% | 42,000,000 | 0 | DIFF |
| simdjson ondemand-st | 0.823 | 1.089 | 24.59 | 56% | 41,999,994 | 6 | ok |
| simdjson dom | 0.952 | 1.348 | 21.25 | 48% | 41,999,994 | 6 | ok |
| rugo chunked | 0.979 | 1.377 | 20.65 | 47% | 41,999,994 | 6 | ok |
| simdjson dom-st | 0.988 | 0.991 | 20.47 | 47% | 41,999,994 | 6 | ok |
| simdjson ondemand | 0.989 | 1.547 | 20.45 | 47% | 41,999,994 | 6 | ok |
| yyjson dom | 1.042 | 1.246 | 19.42 | 44% | 41,999,994 | 6 | ok |
| sonic-cpp dom | 1.516 | 1.938 | 13.34 | 30% | 41,999,994 | 6 | ok |

### filter_agg: count per commit.collection where kind = 'commit' AND commit.operation = 'create'

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.605 | 0.621 | 33.45 | 76% | 41,999,994 | 6 | ok |
| simdjson ondemand | 0.613 | 0.616 | 32.97 | 75% | 41,999,994 | 6 | ok |
| yyjson dom | 0.727 | 0.740 | 27.82 | 63% | 41,999,994 | 6 | ok |
| simdjson dom | 0.751 | 0.757 | 26.95 | 61% | 41,999,994 | 6 | ok |
| simdjson dom-st | 0.789 | 0.799 | 25.63 | 58% | 41,999,994 | 6 | ok |
| opteryx sql | 0.995 | 1.017 | 20.33 | 46% | 41,999,994 | – | ok |
| rugo chunked | 1.061 | 1.088 | 19.06 | 43% | – | 6 | ok |
| sonic-cpp ondemand | 1.260 | 1.398 | 16.05 | 37% | 42,000,000 | 0 | ok |
| sonic-cpp dom | 1.737 | 1.756 | 11.64 | 27% | 41,999,994 | 6 | ok |

### deep: count rows with commit.record.reply.parent.uri (5 levels deep, absent on ~95%)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand | 0.587 | 0.596 | 34.44 | 79% | 41,999,994 | 6 | ok |
| simdjson ondemand-st | 0.590 | 0.603 | 34.28 | 78% | 41,999,994 | 6 | ok |
| yyjson dom | 0.719 | 0.732 | 28.12 | 64% | 41,999,994 | 6 | ok |
| simdjson dom | 0.723 | 0.728 | 27.97 | 64% | 41,999,994 | 6 | ok |
| simdjson dom-st | 0.744 | 0.755 | 27.19 | 62% | 41,999,994 | 6 | ok |
| sonic-cpp ondemand | 0.934 | 0.951 | 21.66 | 49% | 41,999,997 | 3 | ok |
| sonic-cpp dom | 1.245 | 1.281 | 16.25 | 37% | 41,999,994 | 6 | ok |
| opteryx sql | 2.547 | 2.602 | 7.94 | 18% | 41,999,994 | – | ok |

### langs: unnest commit.record.langs (array), count per language

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.595 | 0.611 | 34.00 | 78% | 41,999,994 | 6 | ok |
| simdjson ondemand | 0.596 | 0.603 | 33.92 | 77% | 41,999,994 | 6 | ok |
| yyjson dom | 0.722 | 0.732 | 28.00 | 64% | 41,999,994 | 6 | ok |
| simdjson dom | 0.727 | 0.730 | 27.81 | 63% | 41,999,994 | 6 | ok |
| simdjson dom-st | 0.753 | 0.758 | 26.87 | 61% | 41,999,994 | 6 | ok |
| sonic-cpp ondemand | 0.997 | 1.028 | 20.28 | 46% | 41,999,997 | 3 | ok |
| sonic-cpp dom | 1.565 | 1.689 | 12.93 | 29% | 41,999,994 | 6 | ok |
| opteryx sql | 2.170 | 2.360 | 9.32 | 21% | 41,999,994 | – | ok |
