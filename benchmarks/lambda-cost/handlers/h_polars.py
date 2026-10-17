import polars as pl

from common import PRUNE_HI, PRUNE_LO, run


def _mean(path, predicate):
    df = (
        pl.scan_parquet(path)
        .filter(predicate)
        .select(pl.len().alias("rows"), pl.col("response_ms").mean().alias("mean"))
        .collect()
    )
    return [df["rows"][0], round(df["mean"][0], 4)]


def _footer(path):
    lf = pl.scan_parquet(path)
    return [lf.select(pl.len()).collect().item(), len(lf.collect_schema())]


QUERIES = {
    "broad": lambda p: _mean(p, pl.col("status") == 200),
    "selective": lambda p: _mean(p, pl.col("status") == 500),
    "pruned": lambda p: _mean(
        p, (pl.col("event_id") >= PRUNE_LO) & (pl.col("event_id") < PRUNE_HI)
    ),
    "footer": _footer,
}


def handler(event, context):
    return run(event, QUERIES)
