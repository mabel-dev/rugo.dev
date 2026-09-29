"""Generate deterministic benchmark data. Usage: gen_data.py OUTDIR [jsonl_rows]"""
import csv, json, os, random, sys
out = sys.argv[1]; jrows = int(sys.argv[2]) if len(sys.argv) > 2 else 200_000
os.makedirs(out, exist_ok=True)
rnd = random.Random(42)

def row(ncols):
    r = {"c000": rnd.randrange(1000), "c001": rnd.random() * 1000, "c002": f"v{rnd.randrange(10**6)}"}
    for i in range(3, ncols):
        k = i % 3
        r[f"c{i:03d}"] = rnd.randrange(10**6) if k == 0 else round(rnd.random() * 100, 3) if k == 1 else f"text-{rnd.randrange(10**5)}"
    return r

with open(f"{out}/wide.jsonl", "w") as f:
    for _ in range(jrows): f.write(json.dumps(row(110)) + "\n")
with open(f"{out}/wide.csv", "w", newline="") as f:
    w = None
    for _ in range(200_000):
        r = row(50)
        if w is None: w = csv.DictWriter(f, fieldnames=list(r)); w.writeheader()
        w.writerow(r)

import pyarrow as pa, pyarrow.parquet as pq
n = 2_000_000
status = [200 if x < .92 else 500 if x < .94 else 404 for x in (rnd.random() for _ in range(n))]
t = pa.table({"event_id": list(range(n)), "status": status,
              "response_ms": [rnd.gauss(149, 30) for _ in range(n)],
              **{f"c{i}": [rnd.randrange(10**6) for _ in range(n)] for i in range(5)},
              "url": [f"/api/{rnd.randrange(50)}" for _ in range(n)]})
pq.write_table(t, f"{out}/events.parquet", row_group_size=n // 20, compression="zstd")
