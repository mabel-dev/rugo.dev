# Lambda cost benchmark

Measures what rugo, PyArrow, DuckDB and Polars cost to run on AWS Lambda: init time,
cold and warm billed duration, and peak memory, across four query shapes, two
architectures and three memory sizes. Written up in
[When rugo makes your Lambda cheaper](../../docs/blog/lambda-cost-break-even.html).

```bash
pip install boto3 numpy pyarrow
python gen_data.py events.parquet   # 2M rows, 8 columns, 20 row groups, ZSTD
./build.sh                          # one ZIP per library and architecture
python deploy.py up                 # bucket, role, 8 functions (us-east-1)
python measure.py results.jsonl                      # 1024 and 512 MB
MEMORY=256 python measure.py results_256.jsonl       # 256 MB
python analyze2.py results/results.jsonl results/results_256.jsonl
python deploy.py down               # delete everything again
```

Each cold sample changes the function's configuration first, which retires its
execution environment; five cold samples per shape, then ten warm calls on the same
environment. Numbers come from Lambda's own `REPORT` lines.

`analyze2.py` reduces noise in the cold-call figures: init time is the median over all
cold samples for a library (it doesn't depend on the query), and the S3 download, which
is the same work for every library, uses one shared median per architecture and memory
size. `analyze.py` gives the raw medians.

Raw results from the run on 17 October 2026 (rugo 0.5.4, pyarrow 26.0.0, duckdb 1.5.6,
polars 2.0.0, Python 3.12) are in `results/`.
