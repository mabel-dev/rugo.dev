"""Generate the Parquet files for the read benchmark. Usage: gen_parquet.py OUTDIR [rows]

wide.parquet   rows x 100 columns, zstd, 20 row groups. `id` is monotonic (so the file is
               sorted on it), `k` is uniform 0..999 and unsorted, `a` is a float and `b` a
               short string; the other 96 columns are filler ints, floats and strings.
narrow.parquet rows x 4 columns (id, k, a, b), same generator, 20 row groups.
"""
import os, random, sys
import pyarrow as pa, pyarrow.parquet as pq

out = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 1_000_000
os.makedirs(out, exist_ok=True)
rnd = random.Random(42)

core = {"id": list(range(n)),
        "k": [rnd.randrange(1000) for _ in range(n)],
        "a": [rnd.random() * 1000 for _ in range(n)],
        "b": [f"v{rnd.randrange(10**6)}" for _ in range(n)]}

def filler(i):
    m = i % 3
    if m == 0: return [rnd.randrange(10**6) for _ in range(n)]
    if m == 1: return [round(rnd.random() * 100, 3) for _ in range(n)]
    return [f"text-{rnd.randrange(10**5)}" for _ in range(n)]

pq.write_table(pa.table(core), f"{out}/narrow.parquet", row_group_size=n // 20, compression="zstd")
pq.write_table(pa.table({**core, **{f"c{i:02d}": filler(i) for i in range(96)}}),
               f"{out}/wide.parquet", row_group_size=n // 20, compression="zstd")
