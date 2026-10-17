from rugo import parquet

from common import PRUNE_HI, PRUNE_LO, run


def _mean(path, columns, predicates):
    total, rows = 0.0, 0
    with parquet.read_parquet(path, columns=columns, predicates=predicates) as reader:
        for morsel in reader:
            total += morsel.column("response_ms").sum()
            rows += len(morsel)
    return [rows, round(total / rows, 4)]


QUERIES = {
    "broad": lambda p: _mean(p, ["status", "response_ms"], [("status", "==", 200)]),
    "selective": lambda p: _mean(p, ["response_ms"], [("status", "==", 500)]),
    "pruned": lambda p: _mean(
        p, ["response_ms"], [("event_id", ">=", PRUNE_LO), ("event_id", "<", PRUNE_HI)]
    ),
    "footer": lambda p: [parquet.read_metadata(p).num_rows, len(parquet.read_metadata(p).schema_columns)],
}


def handler(event, context):
    return run(event, QUERIES)
