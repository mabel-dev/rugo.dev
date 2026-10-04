# JSON parser benchmark: NDJSON queries, not just parsing

How fast can you answer a question about a pile of newline-delimited JSON? This compares
the parsers generally considered the fastest (simdjson, yyjson, sonic-cpp) with rugo
(the JSONL reader in [opteryx-core](https://github.com/mabel-dev/opteryx-core)) and with
Opteryx, the SQL engine built on rugo, on the same files, machine and workloads.

Parsing into key/value pairs is rarely the actual job, so most workloads here are questions:
find rows, take a min/max, count values. Every method must produce the **same answer**,
and the report checks it.

## Data

[JSONBench](https://github.com/ClickHouse/JSONBench)'s Bluesky dataset: real AT Protocol
events, one JSON document per line, ~480 bytes per document. `./fetch_data.sh 100`
downloads the first 100 files (100M documents, 47.8 GB decompressed), the same files
JSONBench uses at its 100m scale.

**The headline layout is one file.** Real data rarely arrives in tidy ~480 MB pieces, so
`run.sh` concatenates the files byte for byte into one 47.8 GB file (`--layout single`, the
default). `--layout files` runs on the 100 files as JSONBench ships them.

Of the first 100M documents, 32 lines are genuinely invalid JSON (e.g. `file_0005` has raw
control characters inside strings). Every method skips them and carries on.

## Workloads

| workload | question | why it is different |
|---|---|---|
| `parse` | parse every document fully, extract nothing | the classic parser benchmark |
| `filter_hi` | `did` of rows where `commit.collection = 'app.bsky.feed.like'` (~45% of rows) | filter with a large output |
| `filter_lo` | same with `'app.bsky.graph.block'` (~1.4%) | filter with little output: rewards skipping |
| `minmax` | MIN and MAX of `time_us` | number parsing, one value per row |
| `freq_lo` | count per `commit.collection` (~20 values) | small hash table, extraction-bound |
| `freq_hi` | count per `did` (millions of values) | large hash table, memory-bound |
| `filter_agg` | count per `commit.collection` where `kind = 'commit' AND commit.operation = 'create'` | a predicate on two keys + group: the shape of most real queries |
| `deep` | count rows that have `commit.record.reply.parent.uri` | five levels deep, absent on ~95% of rows |
| `langs` | unnest `commit.record.langs` (an array), count per language | arrays |

Plus a **floor**: counting newlines over the same memory with the same threads. No NDJSON
reader can beat touching every byte once, so each result is also shown as a % of it.

## Methods

| method | API | validates | output |
|---|---|---|---|
| simdjson `ondemand` | `iterate_many(..., stream_format::newline_delimited)`, fields read in document order | UTF-8 and structure of the whole input (stage 1); values only where read; the unread rest of a line is skipped | values extracted per row |
| simdjson `dom` | `parse_many` | every document fully | DOM per document |
| yyjson `dom` | `yyjson_read_opts` per line, strict | every document fully | DOM per document |
| sonic-cpp `dom` | `Document::Parse` per line | every document fully | DOM per document |
| sonic-cpp `ondemand` | `GetOnDemand(line, pointer)` per field | only the path to each target | raw JSON text of each target |
| rugo `chunked` | its C++ reader (the calls under `read_jsonl`), fed 128 MiB chunks one thread each, as Opteryx drives it; projection + predicate pushdown, prefilter on | structural, per line | typed columns (draken vectors) |
| rugo `whole` | the same reader given a whole file with its own threads, as `read_jsonl(path)` does (per-file layout only, see caveats) | as above | as above |
| Opteryx `sql` | `READ_JSONL(..., ignore_errors => true)` + SQL, from Python | as rugo | a result table |

simdjson, yyjson and sonic-cpp are libraries, so each workload is a short hand-written loop
per parser, in `cpp/bench_*.cpp`. Read them. rugo is called from C++ too
(`cpp/bench_rugo.cpp`), built from the opteryx-core release tag with the same flags. It
reads the columns a workload needs (filters pushed down), and the harness then counts
from those columns with the same hash-map code as every other parser. rugo projects one
level of nesting (`key->>'sub'`), so `deep` and `langs` are Opteryx-only on that side.
Opteryx runs everything in full, from Python, as people use it.

## What we did so the parsers run at full speed

We tried to answer in advance the "of course it was slow, you used it wrong" objections:

- **Latest releases**, pinned in `versions.env`, built from source with `-O3 -DNDEBUG -march=native`.
  simdjson is the amalgamated build with runtime dispatch (the report records the kernel
  it picked, e.g. `icelake`). sonic-cpp also gets its own CMake arch flags.
- **Each library's recommended fast path.** simdjson: a reused parser, On-Demand,
  `iterate_many` with the v5 `newline_delimited` format, fields read in document order.
  yyjson: a reused pool allocator sized by `yyjson_read_max_memory_usage`, so no `malloc`
  per document. sonic: a reused Document whose pool sits on a per-thread buffer, cleared
  per line, plus its `GetOnDemand` API as a second option.
- **Both variants where a library has a switch.** simdjson streams run stage 1 on a helper
  thread by default; at 32 workers that oversubscribes, so `-st` variants turn it off.
  sonic and simdjson are each measured with both their DOM and their selective API.
  The report lists every variant; pick the best.
- **No copies, no I/O differences.** Files are mmap'd, with readable padding after every
  file so simdjson needs no copy. Chunks are pre-faulted (`MADV_POPULATE_READ`). All
  C/C++ drivers share this code (`cpp/common.hpp`).
- **Parallelism inside one file.** simdjson, yyjson and sonic can't split a file across
  threads themselves, so the harness does it for them: the input is cut into 128 MiB
  chunks at line boundaries, pulled from one queue by every thread. This is the same
  scheme (and chunk size) Opteryx uses to drive rugo, and rugo `chunked` uses it too. A
  user of those libraries would have to write this themselves.
- **The same hash map for everyone** (ankerl::unordered_dense). High-cardinality counts
  route each key to a partition owned by one thread (as a query engine does). That step is timed: the answer
  has to exist in one place.
- **Malformed lines don't stop anyone.** simdjson's streams stop at the first error, so
  the driver re-reads that region one line at a time and restarts after it. All valid
  documents are read, and the report shows docs read and rejected per method.
- **Answers are checked.** Every method's result is digested (CRC-32 of the strings,
  summed) after the clock stops and compared with yyjson's.

## Caveats (read before quoting a number)

- **Validation differs.** The DOM methods validate every byte. simdjson On-Demand validates
  structure and UTF-8 for everything, but with `newline_delimited` it does not walk
  the unread rest of a line. sonic `ondemand` validates almost nothing, so it accepts the
  malformed lines the others reject, and its answer can differ by those rows (shown as
  `DIFF`). rugo and Opteryx check structure per line.
- **Output differs.** The simdjson/yyjson/sonic loops keep only what each workload needs.
  rugo builds typed columns first (then the harness counts from them). Opteryx builds
  a result table and runs from Python.
- **rugo `whole` can't read a buffer over 4 GiB** at opteryx-0.9.155: its 32-bit offsets
  overflow, giving wrong answers (rows silently dropped) or an exception. That includes
  the public `rugo.jsonl.read_jsonl(path)` on a file over 4 GiB. Opteryx is unaffected (it
  feeds rugo 128 MiB chunks). So `whole` only runs on the per-file layout and the
  one-core pass.
- **One core** (the `onecore` pass, one ~480 MB file) pins every process to one CPU with `taskset`, and every driver is told
  to use one thread (rugo `max_threads = 1`, Opteryx `MAX_EXECUTION_WORKERS=1`).
- **Build flags:** every C/C++ driver, rugo included, is built `-march=native`. The Opteryx
  row uses the PyPI wheel, built `-march=haswell` (AVX2, no AVX-512).
- **Warm page cache, not disk.** Files are read twice before each pass and residency is
  logged (`fincore`). Cold reads on a cloud volume measure the volume.
- Best of 5 timed runs after one warm-up, in one process per measurement. Python import
  and process start are not timed. Both best and median are reported.

## Run it

On a fresh Ubuntu 24.04 machine (the published numbers use AWS m6i.8xlarge: 32 vCPU,
128 GB, so the 48 GB dataset stays in the page cache):

```bash
./aws/bootstrap_ubuntu.sh        # compiler, pigz, Python 3.14
./build.sh                       # fetch pinned parser sources, build drivers
PYTHON=python3.14 ./setup_python.sh
./fetch_data.sh 100              # ~14 GB download, 48 GB decompressed
./run.sh                         # full matrix; ~1 h on 32 vCPU
./report.py results/<stamp>      # tables -> results/<stamp>/report.md
```

`./run.sh --files 10 --repeat 2` is a quick check; `--layout files` uses the separate files. `aws/ec2.sh up | run | down` does the
whole thing on a temporary EC2 instance and tears it down afterwards.

## Layout

```
cpp/common.hpp           mmap, chunking, threads, result accounting (shared by all C++ drivers)
cpp/bench_simdjson.cpp   simdjson On-Demand + DOM
cpp/bench_yyjson.cpp     yyjson
cpp/bench_sonic.cpp      sonic-cpp DOM + GetOnDemand
cpp/bench_floor.cpp      newline-count floor
cpp/bench_rugo.cpp       rugo's C++ JSONL reader (sources from opteryx-core, OPTERYX_CORE_REF)
py/bench_opteryx.py      Opteryx SQL
run.sh / report.py       matrix runner / summary
results/<stamp>/         env.txt, raw_<pass>.jsonl (one line per run), progress.log, report.md
```
