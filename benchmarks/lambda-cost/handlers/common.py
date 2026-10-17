import os
import time

import boto3

BUCKET = os.environ.get("BUCKET", "")
KEY = os.environ.get("KEY", "events.parquet")
LOCAL = os.environ.get("LOCAL", "/tmp/events.parquet")

# pruned shape: a 50,000-row window inside one row group
PRUNE_LO = 1_000_000
PRUNE_HI = 1_050_000

_s3 = boto3.client("s3") if BUCKET else None


def run(event, queries):
    shape = event.get("shape", "broad")
    t0 = time.perf_counter()
    downloaded = False
    if not os.path.exists(LOCAL):
        _s3.download_file(BUCKET, KEY, LOCAL)
        downloaded = True
    t1 = time.perf_counter()
    result = queries[shape](LOCAL)
    t2 = time.perf_counter()
    return {
        "shape": shape,
        "result": result,
        "downloaded": downloaded,
        "download_ms": round((t1 - t0) * 1000, 2),
        "query_ms": round((t2 - t1) * 1000, 2),
    }
