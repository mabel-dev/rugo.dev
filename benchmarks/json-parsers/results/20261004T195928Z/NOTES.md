# Notes on this run (m6i.8xlarge, 2026-10-04)

These results are evidence, not a publishable comparison. Two kinds of rows were measured
with harness code that has since changed:

- **`freq_hi`, every C/C++ row** used the earlier aggregation: per-thread maps merged
  afterwards (now `--agg merge`). The harness now defaults to row routing (`--agg route`).
  A spot check on this box with row routing gave simdjson `ondemand-st` 1.98 s, against
  5.83 s in this report. Re-run `freq_hi` before quoting it.
- **rugo** rows read one file at a time. `--file-workers 4` (now also run by run.sh) was
  not measured here.

The page-cache residency figure in progress.log is blank: `fincore` wasn't installed (it
is now in `aws/bootstrap_ubuntu.sh`). `free -g` showed 60 GB cached against 45 GiB of data,
and a spot check with fincore showed the files fully resident.
