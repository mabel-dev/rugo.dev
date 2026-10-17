import duckdb

from common import PRUNE_HI, PRUNE_LO, run

_con = duckdb.connect()


def _mean(path, where):
    rows, mean = _con.execute(
        f"SELECT count(*), avg(response_ms) FROM read_parquet('{path}') WHERE {where}"
    ).fetchone()
    return [rows, round(mean, 4)]


def _footer(path):
    rows = _con.execute(f"SELECT sum(num_rows) FROM parquet_file_metadata('{path}')").fetchone()[0]
    cols = _con.execute(
        f"SELECT count(*) FROM parquet_schema('{path}') WHERE num_children IS NULL"
    ).fetchone()[0]
    return [int(rows), cols]


QUERIES = {
    "broad": lambda p: _mean(p, "status = 200"),
    "selective": lambda p: _mean(p, "status = 500"),
    "pruned": lambda p: _mean(p, f"event_id >= {PRUNE_LO} AND event_id < {PRUNE_HI}"),
    "footer": _footer,
}


def handler(event, context):
    return run(event, QUERIES)
