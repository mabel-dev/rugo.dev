# Blog backlog (RUGO-4)

Everything here was checked against **rugo 0.5.12**, the current PyPI release, on 18 November 2026.
Where an idea depends on something that has not shipped, it says so and what it is waiting for.

**How-to marking.** A post marked `GUIDE: yes` also works as a how-to and can be adapted into a guide
for the guides hub (RUGO-3, `guides/*.md`, built by `tools/build_guides.py`). The line gives the
front-matter values to start from (`formats`, `verbs`, `kind`). A guide is the stripped-down,
runnable version: no narrative, `bash`/`output` blocks that `tools/verify_guides.py` can replay,
sample data from `https://rugo.dev/data/`. Posts marked `GUIDE: no` are opinion, news or
benchmarks and stay posts.

## Status at a glance

| # | Working title | Status | Target reader | GUIDE |
|---|---------------|--------|---------------|-------|
| 0 | Validate Parquet files the moment they land in S3 | **Ready to publish** | Data engineer on AWS | partly |
| 1 | Fail the build on bad JSONL | **Drafted** (1,453 words) | Dev with data files in a repo | yes |
| 2 | Catch schema drift with rugo diff | **Published** 20 Nov 2026 | Data engineer / analytics engineer | yes |
| 3 | A data-quality report on every pull request | Idea | Maintainer of a data repo | yes |
| 4 | Inspect a whole lake folder with one command | Blocked: glob/directory support | Platform / lake owner | yes |
| 5 | The rugo browser viewer is here | Blocked: RUGO-2 | Analyst, anyone without a terminal | no |
| 6 | Why rugo is a handful of small verbs | Idea | Engineers who like Unix tools | no |
| 7 | Right-size your Parquet files with split and merge | Idea | Data engineer with a small-files problem | yes |
| 8 | CSV in, validated Parquet out: S3 + Lambda, part two | Idea | Readers of #0 | yes |
| 9 | Reading ORC without PyArrow | Idea (benchmark exists) | Hadoop/Hive migrants, Lambda users | no |
| 10 | A field guide to broken Parquet files | Idea | Anyone who has been paged for one | yes |

**Why #1 and #2 were drafted first.** Both run entirely on a laptop today, so every command in
them is verified; both are searchable, practical problems (JSONL in CI, schema drift) with a
"paste this and it works" payoff; and `rugo diff` is the one verb nothing else in this space
has, so it deserves the early slot. #6 is the next best, but it is stronger after a few how-tos
exist for it to point at. #4 and #5 would rank near the top once unblocked.

---

## 0. Validate Parquet files the moment they land in S3: ready to publish

`drafts/s3-lambda-parquet-validation/` + post `validate-parquet-in-s3-with-lambda.html`.
**Angle:** a ~100-line Lambda that gates a bucket: `incoming/` goes in, `validated/` or
`quarantine/` (with a JSON report) comes out. Four checks: it is Parquet, the schema matches the
contract, every row group decodes and the counts agree, required columns are never null.
**Verbs / API:** `parquet.read_metadata`, `parquet.read_parquet` with predicates; CLI `info`, `diff`,
`convert` for building the test files. **Reader:** data engineers on AWS.
**GUIDE: partly.** The local half (`validate()` against good and broken files) is a clean guide:
"Validating a Parquet file in Python" (`formats: [parquet]`, `verbs: [info, diff]`, `kind: workflow`).
The AWS half cannot be replayed without an account.

## 1. Fail the build on bad JSONL: drafted

`drafts/jsonl-ci-validation/`. **Angle:** every `.jsonl` file in a repo gets read on each pull
request. A malformed line fails the build with its line number; a wrong type fails with the column
and value; required fields are checked with one `is null` predicate; results become GitHub
annotations. The contract is a JSON file reviewed in the same PR as the data.
**Verbs / API:** `count` (CLI smoke test), `jsonl.read_jsonl` with `explicit_schema` and predicates.
**Reader:** developers with fixtures, seed data or eval sets in git. **GUIDE: yes**, as "Validating
JSONL against a contract" (`formats: [jsonl]`, `verbs: [count]`, `kind: workflow`). It sits right
after the existing guide `validating-jsonl-line-by-line`: link the two both ways at publish time.

## 2. Catch schema drift with rugo diff: drafted

`drafts/schema-drift-rugo-diff/`. **Angle:** added / removed / retyped columns in one command,
exit code 1 on any change, `--json` for scripts. A 15-line shell gate treats removed or retyped
columns as breaking and new ones as compatible, and a workflow compares each changed Parquet file
with its base-branch version. Footer-only, so it is instant on huge files.
**Verbs:** `diff`, `convert`, `schema`. **Reader:** data / analytics engineers.
**GUIDE: yes**: "Catching schema drift with rugo diff" (`formats: [parquet]`, `verbs: [diff, convert]`,
`kind: workflow`).

## 3. A data-quality report on every pull request

**Angle:** the "post-scan report". A workflow scans every data file the PR touches and writes a
Markdown table to the job summary (`$GITHUB_STEP_SUMMARY`): rows, columns, size, null counts per
column, and a schema diff against the base branch, with a pass/fail line at the top. Reviewers see
what the data change *is* without downloading anything. It is the reporting companion to #1 and #2.
**Verbs:** `info --json`, `describe --json` (Parquet only), `count`, `diff --json`; a few lines of
`jq` or Python to render the table. **Reader:** maintainers of repos that version data.
**GUIDE: yes**: "Summarising a data file as a Markdown table" (`formats: [parquet, jsonl]`,
`verbs: [info, describe, count, diff]`, `kind: workflow`).
**Check before drafting:** `describe` prints timestamp min/max as raw integers (microseconds), so the
report needs to convert them.

## 4. Inspect a whole lake folder with one command

**Blocked: glob and directory support has not shipped.** As of 0.5.12 `rugo count lake/` fails
("cannot infer format from extension"), and no verb understands a glob pattern itself (a shell-expanded
glob only works with `merge`, the one verb that takes many inputs). **Angle:** point rugo at a folder of
Parquet/JSONL files and get row counts, schema and drift across all of them, replacing the
`for f in *.parquet` loop everyone writes. Draft once the syntax is final; do not guess it.
**Verbs:** `info`, `count`, `schema`, `diff`, `merge` on folders. **Reader:** platform engineers and
lake owners. **GUIDE: yes**, and arguably the first guide to write when it ships
(`verbs: [info, count, schema]`, `kind: workflow`).

## 5. The rugo browser viewer is here

**Blocked: RUGO-2.** Launch post: drop a Parquet, Avro or JSONL file into a page and see schema,
row count and a preview, with no install and (the thing worth confirming before writing) no upload.
Open questions for RUGO-2 that the post needs answered: where it runs, whether files leave the
browser, size limits, which formats. **Verbs:** the viewer's equivalents of `info`, `schema`,
`preview`. **Reader:** analysts and anyone without a terminal. **GUIDE: no** for the launch
announcement. But the hub already has a `viewer: true` front-matter flag and a `VIEWER_URL`
placeholder in `tools/build_guides.py`, so set the URL when this ships and every existing guide
with `viewer: true` gets an "Open in the viewer" link for free.

## 6. Why rugo is a handful of small verbs

**Angle:** design notes. `info`, `schema`, `columns`, `count`, `preview`, `describe`, `inspect`,
`diff`, `convert`, `merge`, `split`: each does one thing, takes plain file paths, prints
something a person can read and (with `--json`) something a script can parse, and signals with
its exit code. Show the compositions this buys: `rugo diff --json | jq` feeding a gate (#2), `convert`
followed by `diff` to prove a round trip is lossless (an Avro → Parquet round trip compares
identical), `split` then `merge` as an inverse pair. Honest about scope: what rugo deliberately does not do (there is no query language) and why small verbs suit
that choice. **Verbs:** all twelve. **Reader:** engineers who like
Unix tools and are wary of another framework. **GUIDE: no**; an opinion piece. Its "composition"
section could seed a guide later.

## 7. Right-size your Parquet files with split and merge

**Angle:** too many tiny files make every reader slow, one giant file cannot be parallelised.
Show `split --rows` to cut a file into evenly sized parts, `merge` to combine many into one, and
`diff` + `count` to prove nothing was lost (4,630 rows in, 4,630 out, schemas identical). Tie in
Lambda: a few mid-sized files fit its memory and parallelism better than one huge one or a
thousand tiny ones; link the existing Lambda cost posts. **Verbs:** `split`, `merge`, `count`,
`diff`, `info`. **Reader:** data engineers with a small-files problem. **GUIDE: yes**: "Splitting and
merging Parquet files" (`formats: [parquet]`, `verbs: [split, merge, count]`, `kind: workflow`).
**Check before drafting:** split output is named `<name>.part0000.<ext>`; merge needs
schema-identical inputs, so show what happens when they are not.

## 8. CSV in, validated Parquet out: S3 + Lambda, part two

**Angle:** the sequel to #0. Partners drop CSVs; the Lambda validates the CSV's schema against a
contract with `rugo diff`, converts it to Parquet with `convert`, and files it under `validated/`
(or quarantines it). Lead with the size win from the existing formats post (JSONL 1.09 MB → Parquet
93 KB on the sample data). **Verbs:** `convert`, `diff`, `count`, `info`. **Reader:** readers of #0.
**GUIDE: yes** for the local part ("Converting CSV to Parquet and checking the schema",
`formats: [csv, parquet]`, `verbs: [convert, diff]`, `kind: workflow`). Overlaps the existing guide
`parquet-vs-csv-when-to-convert`; keep the guide to the contract-check step.
**Check before drafting:** CSV type inference decides the Parquet types (a timestamp with an offset
came out as `varchar` on the sample data), so the post should either pin types or make that the
point of the drift check.

## 9. Reading ORC without PyArrow

**Angle:** a read benchmark already exists (`benchmarks/*orc*.py`,
`benchmarks/results/2026-10-28-orc-read.json`) but there is no post. Frame it like the Avro one:
the same file read three ways, package size and read time, with a Lambda-sized footprint story.
ORC is Python-API only (`from rugo import orc`; there are no CLI verbs for it), so the post is
code, not commands. **Verbs / API:** `orc.read_metadata`, `orc.read_orc`. **Reader:** teams migrating
off Hive/Hadoop, and Lambda users who inherit ORC. **GUIDE: no**; a benchmark post. Re-run the
benchmark on the current release before quoting numbers: the stored result predates 0.5.12.

## 10. A field guide to broken Parquet files

**Angle:** what rugo says when a file is not what it claims, and what each message means:
`Not a parquet file` (wrong magic bytes: a CSV in disguise, or a truncated upload),
`File too small to be a parquet file` (zero-byte object), `Invalid string length` (footer damaged),
and `row group 10, column 'id': Zstd decompression failed` (data block damaged; the error names
the row group and column). How to tell truncated from corrupt, how to find the last good row group,
and what no Parquet reader can detect (a flipped bit inside an uncompressed page: that is what S3
checksums are for). **Verbs:** `info`, `inspect`, `count`; Python `read_parquet`. **Reader:** anyone
who has been paged over a bad file. **GUIDE: yes** ("Diagnosing a damaged Parquet file", `verbs:
[info, inspect, count]`, `kind: workflow`); it must not duplicate `parquet-footer-rugo-info`.
**Check before drafting:** on a damaged file `rugo info` currently ends in a Python traceback (the
useful message is its last line), so either fix that first or show `2>&1 | tail -n 1`.
