# JSON parser benchmark: 20261004T195928Z

```
stamp: 20261004T195928Z
files: 100
repeat: 5 (+1 warm-up)
threads: 32
Linux ip-172-30-0-94 7.0.0-1013-aws #13~24.04.1-Ubuntu SMP PREEMPT Sat Sep  5 01:10:01 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
CPU(s):                                  32
Model name:                              Intel(R) Xeon(R) Platinum 8375C CPU @ 2.90GHz
Thread(s) per core:                      2
Core(s) per socket:                      16
Socket(s):                               1
Flags: (has avx512_vpopcntdq ...)
L1d cache:                               768 KiB (16 instances)
L1i cache:                               512 KiB (16 instances)
L2 cache:                                20 MiB (16 instances)
L3 cache:                                54 MiB (1 instance)
NUMA node(s):                            1
Vulnerability L1tf:                      Not affected
               total        used        free      shared  buff/cache   available
Mem:             123           1          62           0          60         121
ec2: m6i.8xlarge
cxx: g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
cc: gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
flags: -O3 -DNDEBUG -march=native -std=c++20 -pthread -Icpp -Ideps/unordered_dense/include
sonic_flags: -mavx2 -mpclmul -mbmi -mlzcnt
simdjson: v5.0.2 c9030726ebbf5f9fe9f9facb4a401f6d3ccd77a2
yyjson: 0.13.0 6447536015f3d600f3d65323b10976103b337ca7
sonic: v1.0.2 f5d0117adbe4fb3b9f8a2d6f24155119527a2ddd
unordered_dense: v5.3.1 c164976d1426d623d87b98833ff60c7263fde4e1
python 3.14.8 | opteryx 0.9.155 | rugo 0.4.42
data manifest sha256: 9aa655fe13ccb687
```

## Pass: multi

Floor (count newlines over the same mmap'd chunks, same threads): 0.649 s, 73.7 GB/s over 47.81 GB in 100 files

### parse: full parse of every document, nothing extracted

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson dom-st | 1.372 | 1.375 | 34.84 | 47% | 99,999,968 | 32 | ok |
| simdjson dom | 1.514 | 1.541 | 31.58 | 43% | 99,999,968 | 32 | ok |
| yyjson dom | 1.825 | 1.837 | 26.20 | 36% | 99,999,968 | 32 | ok |
| sonic-cpp dom | 2.234 | 2.236 | 21.41 | 29% | 99,999,968 | 32 | ok |
| rugo read_jsonl:read-all-columns | 35.183 | 36.064 | 1.36 | 2% | 99,999,968 | – | ok (rows) |

### filter_hi: did of rows where commit.collection = 'app.bsky.feed.like' (~45% of rows)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 1.594 | 1.641 | 30.00 | 41% | 99,999,968 | 32 | ok |
| sonic-cpp ondemand | 1.597 | 1.603 | 29.94 | 41% | 100,000,000 | 0 | ok |
| simdjson ondemand | 1.879 | 1.982 | 25.45 | 35% | 99,999,968 | 32 | ok |
| simdjson dom-st | 2.148 | 2.248 | 22.25 | 30% | 99,999,968 | 32 | ok |
| opteryx sql | 2.270 | 2.278 | 21.07 | 29% | 99,999,968 | – | ok |
| simdjson dom | 2.283 | 2.447 | 20.94 | 28% | 99,999,968 | 32 | ok |
| yyjson dom | 2.569 | 2.717 | 18.61 | 25% | 99,999,968 | 32 | ok |
| sonic-cpp dom | 3.374 | 3.492 | 14.17 | 19% | 99,999,968 | 32 | ok |
| rugo read_jsonl:full | 6.212 | 6.249 | 7.70 | 10% | – | – | ok |

### filter_lo: did of rows where commit.collection = 'app.bsky.graph.block' (~1.4% of rows)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| sonic-cpp ondemand | 0.853 | 0.858 | 56.07 | 76% | 100,000,000 | 0 | ok |
| simdjson ondemand-st | 0.894 | 0.900 | 53.46 | 73% | 99,999,968 | 32 | ok |
| opteryx sql | 1.060 | 1.082 | 45.13 | 61% | 99,999,968 | – | ok |
| simdjson ondemand | 1.259 | 1.301 | 37.98 | 52% | 99,999,968 | 32 | ok |
| simdjson dom-st | 1.521 | 1.526 | 31.44 | 43% | 99,999,968 | 32 | ok |
| simdjson dom | 1.650 | 1.656 | 28.98 | 39% | 99,999,968 | 32 | ok |
| yyjson dom | 1.960 | 1.975 | 24.39 | 33% | 99,999,968 | 32 | ok |
| sonic-cpp dom | 2.659 | 2.670 | 17.98 | 24% | 99,999,968 | 32 | ok |
| rugo read_jsonl:full | 2.994 | 3.002 | 15.97 | 22% | – | – | ok |

### minmax: MIN and MAX of time_us

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| sonic-cpp ondemand | 0.600 | 0.601 | 79.69 | 108% | 99,999,984 | 16 | ok |
| simdjson ondemand-st | 0.787 | 0.793 | 60.74 | 82% | 99,999,968 | 32 | ok |
| simdjson ondemand | 1.234 | 1.253 | 38.75 | 53% | 99,999,968 | 32 | ok |
| simdjson dom-st | 1.402 | 1.404 | 34.10 | 46% | 99,999,968 | 32 | ok |
| simdjson dom | 1.524 | 1.565 | 31.37 | 43% | 99,999,968 | 32 | ok |
| yyjson dom | 1.849 | 1.855 | 25.86 | 35% | 99,999,968 | 32 | ok |
| opteryx sql | 2.051 | 2.057 | 23.31 | 32% | 99,999,968 | – | ok |
| sonic-cpp dom | 2.308 | 2.313 | 20.71 | 28% | 99,999,968 | 32 | ok |
| rugo read_jsonl:full | 6.452 | 6.574 | 7.41 | 10% | 99,999,968 | – | ok |

### freq_lo: count per commit.collection (~20 distinct values)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| sonic-cpp ondemand | 0.887 | 0.958 | 53.89 | 73% | 100,000,000 | 0 | DIFF |
| simdjson ondemand-st | 0.958 | 0.990 | 49.89 | 68% | 99,999,968 | 32 | ok |
| simdjson ondemand | 1.292 | 1.357 | 37.02 | 50% | 99,999,968 | 32 | ok |
| simdjson dom-st | 1.611 | 1.668 | 29.67 | 40% | 99,999,968 | 32 | ok |
| simdjson dom | 1.775 | 1.792 | 26.93 | 37% | 99,999,968 | 32 | ok |
| opteryx sql | 2.047 | 2.060 | 23.36 | 32% | 99,999,968 | – | ok |
| yyjson dom | 2.055 | 2.129 | 23.26 | 32% | 99,999,968 | 32 | ok |
| sonic-cpp dom | 2.467 | 2.528 | 19.38 | 26% | 99,999,968 | 32 | ok |
| rugo read_jsonl:extract-only | 9.301 | 9.396 | 5.14 | 7% | 99,999,968 | – | ok (rows) |

### freq_hi: count per did (millions of distinct values)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| opteryx sql | 2.360 | 2.388 | 20.26 | 27% | 99,999,968 | – | ok |
| sonic-cpp ondemand | 5.164 | 5.207 | 9.26 | 13% | 100,000,000 | 0 | DIFF |
| simdjson ondemand-st | 5.826 | 5.887 | 8.21 | 11% | 99,999,968 | 32 | ok |
| simdjson ondemand | 5.891 | 5.918 | 8.12 | 11% | 99,999,968 | 32 | ok |
| yyjson dom | 6.204 | 6.372 | 7.71 | 10% | 99,999,968 | 32 | ok |
| simdjson dom-st | 6.668 | 6.682 | 7.17 | 10% | 99,999,968 | 32 | ok |
| simdjson dom | 6.777 | 6.784 | 7.06 | 10% | 99,999,968 | 32 | ok |
| sonic-cpp dom | 6.823 | 6.874 | 7.01 | 10% | 99,999,968 | 32 | ok |
| rugo read_jsonl:extract-only | 12.956 | 13.054 | 3.69 | 5% | 99,999,968 | – | ok (rows) |

### filter_agg: count per commit.collection where kind = 'commit' AND commit.operation = 'create'

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.959 | 1.000 | 49.88 | 68% | 99,999,968 | 32 | ok |
| simdjson ondemand | 1.314 | 1.324 | 36.38 | 49% | 99,999,968 | 32 | ok |
| simdjson dom-st | 1.709 | 1.760 | 27.99 | 38% | 99,999,968 | 32 | ok |
| simdjson dom | 1.838 | 1.853 | 26.02 | 35% | 99,999,968 | 32 | ok |
| sonic-cpp ondemand | 1.879 | 1.938 | 25.45 | 35% | 100,000,000 | 0 | DIFF |
| yyjson dom | 2.015 | 2.063 | 23.73 | 32% | 99,999,968 | 32 | ok |
| sonic-cpp dom | 2.690 | 2.740 | 17.78 | 24% | 99,999,968 | 32 | ok |
| opteryx sql | 3.050 | 3.061 | 15.68 | 21% | 99,999,968 | – | ok |
| rugo read_jsonl:extract-only | 10.805 | 10.858 | 4.43 | 6% | – | – | ok (rows) |

### deep: count rows with commit.record.reply.parent.uri (5 levels deep, absent on ~95%)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.940 | 0.943 | 50.87 | 69% | 99,999,968 | 32 | ok |
| sonic-cpp ondemand | 1.198 | 1.200 | 39.92 | 54% | 99,999,984 | 16 | ok |
| simdjson ondemand | 1.266 | 1.334 | 37.77 | 51% | 99,999,968 | 32 | ok |
| simdjson dom-st | 1.489 | 1.491 | 32.12 | 44% | 99,999,968 | 32 | ok |
| simdjson dom | 1.614 | 1.623 | 29.62 | 40% | 99,999,968 | 32 | ok |
| yyjson dom | 2.013 | 2.019 | 23.76 | 32% | 99,999,968 | 32 | ok |
| sonic-cpp dom | 2.477 | 2.482 | 19.30 | 26% | 99,999,968 | 32 | ok |
| opteryx sql | 8.260 | 8.278 | 5.79 | 8% | 99,999,968 | – | ok |

### langs: unnest commit.record.langs (array), count per language

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.939 | 0.944 | 50.90 | 69% | 99,999,968 | 32 | ok |
| sonic-cpp ondemand | 1.261 | 1.261 | 37.93 | 51% | 99,999,984 | 16 | ok |
| simdjson ondemand | 1.308 | 1.327 | 36.54 | 50% | 99,999,968 | 32 | ok |
| simdjson dom-st | 1.487 | 1.492 | 32.16 | 44% | 99,999,968 | 32 | ok |
| simdjson dom | 1.604 | 1.619 | 29.80 | 40% | 99,999,968 | 32 | ok |
| yyjson dom | 2.003 | 2.008 | 23.87 | 32% | 99,999,968 | 32 | ok |
| sonic-cpp dom | 2.447 | 2.450 | 19.54 | 27% | 99,999,968 | 32 | ok |
| opteryx sql | 8.068 | 8.190 | 5.93 | 8% | 99,999,968 | – | ok |

## Pass: single

Floor (count newlines over the same mmap'd chunks, same threads): 0.113 s, 4.2 GB/s over 0.48 GB in 1 files

### parse: full parse of every document, nothing extracted

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson dom-st | 0.213 | 0.213 | 2.26 | 53% | 1,000,000 | 0 | ok |
| simdjson dom | 0.227 | 0.227 | 2.12 | 50% | 1,000,000 | 0 | ok |
| yyjson dom | 0.314 | 0.315 | 1.53 | 36% | 1,000,000 | 0 | ok |
| sonic-cpp dom | 0.398 | 0.399 | 1.21 | 28% | 1,000,000 | 0 | ok |
| rugo read_jsonl:read-all-columns | 0.959 | 0.959 | 0.50 | 12% | 1,000,000 | – | ok (rows) |

### filter_hi: did of rows where commit.collection = 'app.bsky.feed.like' (~45% of rows)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.157 | 0.159 | 3.06 | 72% | 1,000,000 | 0 | ok |
| simdjson ondemand | 0.169 | 0.170 | 2.85 | 67% | 1,000,000 | 0 | ok |
| sonic-cpp ondemand | 0.217 | 0.217 | 2.22 | 52% | 1,000,000 | 0 | ok |
| simdjson dom-st | 0.252 | 0.254 | 1.91 | 45% | 1,000,000 | 0 | ok |
| simdjson dom | 0.263 | 0.264 | 1.83 | 43% | 1,000,000 | 0 | ok |
| yyjson dom | 0.339 | 0.339 | 1.42 | 34% | 1,000,000 | 0 | ok |
| rugo read_jsonl:full | 0.397 | 0.399 | 1.21 | 29% | – | – | ok |
| sonic-cpp dom | 0.475 | 0.477 | 1.01 | 24% | 1,000,000 | 0 | ok |
| opteryx sql | 0.698 | 0.703 | 0.69 | 16% | 1,000,000 | – | ok |

### filter_lo: did of rows where commit.collection = 'app.bsky.graph.block' (~1.4% of rows)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.144 | 0.144 | 3.35 | 79% | 1,000,000 | 0 | ok |
| rugo read_jsonl:full | 0.144 | 0.144 | 3.33 | 79% | – | – | ok |
| simdjson ondemand | 0.155 | 0.155 | 3.10 | 73% | 1,000,000 | 0 | ok |
| sonic-cpp ondemand | 0.184 | 0.185 | 2.61 | 62% | 1,000,000 | 0 | ok |
| simdjson dom-st | 0.235 | 0.236 | 2.04 | 48% | 1,000,000 | 0 | ok |
| simdjson dom | 0.249 | 0.249 | 1.93 | 46% | 1,000,000 | 0 | ok |
| yyjson dom | 0.332 | 0.332 | 1.45 | 34% | 1,000,000 | 0 | ok |
| sonic-cpp dom | 0.437 | 0.438 | 1.10 | 26% | 1,000,000 | 0 | ok |
| opteryx sql | 0.447 | 0.452 | 1.08 | 25% | 1,000,000 | – | ok |

### minmax: MIN and MAX of time_us

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| sonic-cpp ondemand | 0.107 | 0.107 | 4.50 | 106% | 1,000,000 | 0 | ok |
| simdjson ondemand-st | 0.128 | 0.128 | 3.76 | 89% | 1,000,000 | 0 | ok |
| simdjson ondemand | 0.138 | 0.139 | 3.47 | 82% | 1,000,000 | 0 | ok |
| simdjson dom-st | 0.220 | 0.220 | 2.19 | 52% | 1,000,000 | 0 | ok |
| simdjson dom | 0.233 | 0.233 | 2.07 | 49% | 1,000,000 | 0 | ok |
| yyjson dom | 0.319 | 0.319 | 1.51 | 36% | 1,000,000 | 0 | ok |
| rugo read_jsonl:full | 0.360 | 0.361 | 1.34 | 32% | 1,000,000 | – | ok |
| sonic-cpp dom | 0.406 | 0.406 | 1.18 | 28% | 1,000,000 | 0 | ok |
| opteryx sql | 0.665 | 0.670 | 0.72 | 17% | 1,000,000 | – | ok |

### freq_lo: count per commit.collection (~20 distinct values)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.147 | 0.147 | 3.27 | 77% | 1,000,000 | 0 | ok |
| simdjson ondemand | 0.158 | 0.158 | 3.04 | 72% | 1,000,000 | 0 | ok |
| sonic-cpp ondemand | 0.190 | 0.191 | 2.53 | 60% | 1,000,000 | 0 | ok |
| simdjson dom-st | 0.235 | 0.235 | 2.05 | 48% | 1,000,000 | 0 | ok |
| simdjson dom | 0.249 | 0.250 | 1.93 | 46% | 1,000,000 | 0 | ok |
| yyjson dom | 0.340 | 0.340 | 1.41 | 33% | 1,000,000 | 0 | ok |
| rugo read_jsonl:extract-only | 0.411 | 0.414 | 1.17 | 28% | 1,000,000 | – | ok (rows) |
| sonic-cpp dom | 0.431 | 0.432 | 1.11 | 26% | 1,000,000 | 0 | ok |
| opteryx sql | 0.662 | 0.664 | 0.73 | 17% | 1,000,000 | – | ok |

### freq_hi: count per did (millions of distinct values)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| sonic-cpp ondemand | 0.317 | 0.318 | 1.52 | 36% | 1,000,000 | 0 | ok |
| simdjson ondemand-st | 0.372 | 0.374 | 1.29 | 30% | 1,000,000 | 0 | ok |
| simdjson ondemand | 0.380 | 0.380 | 1.27 | 30% | 1,000,000 | 0 | ok |
| rugo read_jsonl:extract-only | 0.420 | 0.421 | 1.14 | 27% | 1,000,000 | – | ok (rows) |
| simdjson dom-st | 0.471 | 0.473 | 1.02 | 24% | 1,000,000 | 0 | ok |
| simdjson dom | 0.481 | 0.482 | 1.00 | 24% | 1,000,000 | 0 | ok |
| yyjson dom | 0.553 | 0.555 | 0.87 | 21% | 1,000,000 | 0 | ok |
| sonic-cpp dom | 0.655 | 0.658 | 0.73 | 17% | 1,000,000 | 0 | ok |
| opteryx sql | 0.746 | 0.757 | 0.64 | 15% | 1,000,000 | – | ok |

### filter_agg: count per commit.collection where kind = 'commit' AND commit.operation = 'create'

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.154 | 0.154 | 3.13 | 74% | 1,000,000 | 0 | ok |
| simdjson ondemand | 0.165 | 0.166 | 2.91 | 69% | 1,000,000 | 0 | ok |
| simdjson dom-st | 0.257 | 0.257 | 1.87 | 44% | 1,000,000 | 0 | ok |
| simdjson dom | 0.271 | 0.271 | 1.77 | 42% | 1,000,000 | 0 | ok |
| yyjson dom | 0.341 | 0.342 | 1.41 | 33% | 1,000,000 | 0 | ok |
| sonic-cpp ondemand | 0.384 | 0.384 | 1.25 | 30% | 1,000,000 | 0 | ok |
| sonic-cpp dom | 0.458 | 0.459 | 1.05 | 25% | 1,000,000 | 0 | ok |
| rugo read_jsonl:extract-only | 0.501 | 0.501 | 0.96 | 23% | – | – | ok (rows) |
| opteryx sql | 0.808 | 0.809 | 0.60 | 14% | 1,000,000 | – | ok |

### deep: count rows with commit.record.reply.parent.uri (5 levels deep, absent on ~95%)

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.156 | 0.156 | 3.08 | 73% | 1,000,000 | 0 | ok |
| simdjson ondemand | 0.168 | 0.169 | 2.86 | 67% | 1,000,000 | 0 | ok |
| simdjson dom-st | 0.233 | 0.233 | 2.06 | 49% | 1,000,000 | 0 | ok |
| simdjson dom | 0.244 | 0.244 | 1.97 | 47% | 1,000,000 | 0 | ok |
| sonic-cpp ondemand | 0.293 | 0.294 | 1.64 | 39% | 1,000,000 | 0 | ok |
| yyjson dom | 0.340 | 0.340 | 1.41 | 33% | 1,000,000 | 0 | ok |
| sonic-cpp dom | 0.427 | 0.427 | 1.13 | 27% | 1,000,000 | 0 | ok |
| opteryx sql | 1.814 | 1.821 | 0.27 | 6% | 1,000,000 | – | ok |

### langs: unnest commit.record.langs (array), count per language

| method | best s | median s | GB/s | % of floor | docs | rejected | answer |
|---|---:|---:|---:|---:|---:|---:|---|
| simdjson ondemand-st | 0.157 | 0.157 | 3.07 | 72% | 1,000,000 | 0 | ok |
| simdjson ondemand | 0.168 | 0.168 | 2.86 | 67% | 1,000,000 | 0 | ok |
| simdjson dom-st | 0.231 | 0.231 | 2.08 | 49% | 1,000,000 | 0 | ok |
| simdjson dom | 0.244 | 0.245 | 1.97 | 46% | 1,000,000 | 0 | ok |
| sonic-cpp ondemand | 0.291 | 0.292 | 1.65 | 39% | 1,000,000 | 0 | ok |
| yyjson dom | 0.342 | 0.343 | 1.40 | 33% | 1,000,000 | 0 | ok |
| sonic-cpp dom | 0.417 | 0.419 | 1.15 | 27% | 1,000,000 | 0 | ok |
| opteryx sql | 1.753 | 1.761 | 0.27 | 6% | 1,000,000 | – | ok |
