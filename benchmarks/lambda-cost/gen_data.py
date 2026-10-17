"""Generate the web-traffic shaped Parquet file used by the Lambda benchmark.

2M rows, 8 columns, 20 row groups, ZSTD. event_id is monotonic (prunable);
status is random (not prunable).
"""
import sys

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

N = 2_000_000
rng = np.random.default_rng(42)

status = rng.choice(
    [200, 201, 301, 304, 404, 500],
    size=N,
    p=[0.92, 0.01, 0.01, 0.02, 0.02, 0.02],
).astype(np.int64)
paths = np.array([f"/api/v1/resource/{i}" for i in range(500)])
agents = np.array([f"Mozilla/5.0 (agent {i})" for i in range(50)])
regions = np.array(["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-2"])

table = pa.table(
    {
        "event_id": pa.array(np.arange(N, dtype=np.int64)),
        "ts": pa.array(1_780_000_000_000 + np.arange(N, dtype=np.int64) * 13),
        "status": pa.array(status),
        "response_ms": pa.array(np.round(rng.gamma(4.0, 37.3, N), 3)),
        "path": pa.array(paths[rng.integers(0, len(paths), N)]),
        "user_agent": pa.array(agents[rng.integers(0, len(agents), N)]),
        "bytes": pa.array(rng.integers(200, 200_000, N, dtype=np.int64)),
        "region": pa.array(regions[rng.integers(0, len(regions), N)]),
    }
)

pq.write_table(table, sys.argv[1], row_group_size=N // 20, compression="zstd")
