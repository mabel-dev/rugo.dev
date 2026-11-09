"""Generate the ORC files for the read benchmark. Usage: gen_orc.py OUTDIR [rows] [stripe_bytes]

Same data as gen_parquet.py (same seed, same columns), written with pyarrow.orc (Apache ORC C++):
wide.orc   rows x 100 columns, zstd. `id` is monotonic (so the file is sorted on it), `k` is
           uniform 0..999 and unsorted, `a` is a float and `b` a short string; the other 96
           columns are filler ints, floats and strings.
narrow.orc rows x 4 columns (id, k, a, b), same generator.
ORC stripes are sized in bytes, not rows, so the stripe count is not fixed at 20 the way the
Parquet row-group count is; measure_orc.py records the actual stripe count of each file.
"""
import os, random, sys
import pyarrow as pa, pyarrow.orc as orc

out = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 1_000_000
stripe = int(sys.argv[3]) if len(sys.argv) > 3 else 64 << 20
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

narrow = pa.table(core)
wide = pa.table({**core, **{f"c{i:02d}": filler(i) for i in range(96)}})
# aim for ~20 stripes per file, like the Parquet files' 20 row groups
for name, t in (("narrow", narrow), ("wide", wide)):
    orc.write_table(t, f"{out}/{name}.orc", compression="zstd",
                    stripe_size=max(stripe if len(sys.argv) > 3 else t.nbytes // 20, 1 << 20))
