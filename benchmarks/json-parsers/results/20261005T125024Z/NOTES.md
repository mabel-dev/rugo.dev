# Notes on this run (Apple M5 Pro, 18 threads, 2026-10-05)

- **rugo and Opteryx were built from a local, uncommitted opteryx-core tree** (on top of
  7b40af35): the widened JSONL raw prefilter (IN lists, AND clauses confirmed per line,
  literals down to 2 bytes, a NEON two-byte sieve for needles <= 16 bytes, per-4MB-window
  re-decision) and the `simd_contains_cs` fix in `src/cpp/volnitsky.h`. `env.txt` says
  "opteryx 0.9.155": that line imports the venv's installed wheel, but the Opteryx rows ran
  the local tree (`OPTERYX_CORE_SRC` → `py/bench_opteryx.py` sys.path insert).
- The harness was a copy of this folder at 54fbe17, with three extra workloads added
  (`filter_in`, `filter_and`, `filter_short`) that this run did NOT include. Only the
  standard nine were run. The drivers' code for the nine is unchanged.
- No `onecore` pass: it needs `taskset`, which macOS lacks. `fincore` is also missing, so the
  page-cache residency in progress.log is blank (the file is read twice before the pass).
- The prefilter only changes selective filters. Of the nine workloads only `filter_lo` moved
  (0.473 s → 0.461 s, now 100% of the floor); everything else is the same engine as before.
- sonic-cpp `ondemand` DIFF on `freq_lo`/`freq_hi` is expected: it accepts the malformed
  lines every other method rejects (rejected = 0).
