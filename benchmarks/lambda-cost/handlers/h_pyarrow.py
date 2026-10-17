import pyarrow.compute as pc
import pyarrow.parquet as pq

from common import PRUNE_HI, PRUNE_LO, run


def _mean(path, columns, filters):
    table = pq.read_table(path, columns=columns, filters=filters)
    return [table.num_rows, round(pc.mean(table["response_ms"]).as_py(), 4)]


def _footer(path):
    meta = pq.read_metadata(path)
    return [meta.num_rows, meta.num_columns]


QUERIES = {
    "broad": lambda p: _mean(p, ["status", "response_ms"], [("status", "==", 200)]),
    "selective": lambda p: _mean(p, ["response_ms"], [("status", "==", 500)]),
    "pruned": lambda p: _mean(
        p, ["response_ms"], [("event_id", ">=", PRUNE_LO), ("event_id", "<", PRUNE_HI)]
    ),
    "footer": _footer,
}


def handler(event, context):
    return run(event, QUERIES)
