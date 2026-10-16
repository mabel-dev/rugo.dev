"""Write the Avro comparison file: deterministic rows, written by fastavro.

    python gen_avro.py <out.avro> <rows> <codec>

Called by measure_avro.py inside its virtualenv. fastavro writes the file every
reader is timed on, so no reader is timed on its own writer's output.

20 fields in roughly the mix of an event or log stream: fixed-width scalars,
short and long strings, fixed(16), nullable unions in both branch orders,
enums, timestamp-micros, date, decimal(12,2) on bytes, and nested values - a
record, an array of strings and a map of doubles. Blocks are cut every 64,000
bytes, the JVM writer's default (what Kafka Connect, Spark and Iceberg write
with).
"""
import datetime, decimal, random, sys

import fastavro

COUNTRIES = ["AU", "BR", "CA", "CN", "DE", "ES", "FR", "GB", "IN", "IT",
             "JP", "KR", "MX", "NL", "NZ", "PL", "SE", "SG", "US", "ZA"]
EVENTS = ["click", "view", "purchase", "signup", "logout", "search", "share"]
OSES = ["android", "ios", "linux", "macos", "windows"]
WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel",
         "india", "juliet", "kilo", "lima", "mike", "november", "oscar", "papa"]

SCHEMA = {
    "type": "record",
    "name": "Event",
    "fields": [
        {"name": "id", "type": "long"},
        {"name": "user_id", "type": "long"},
        {"name": "small", "type": "int"},
        {"name": "amount", "type": "double"},
        {"name": "ratio", "type": "float"},
        {"name": "flag", "type": "boolean"},
        {"name": "event", "type": "string"},
        {"name": "country", "type": {"type": "enum", "name": "Country", "symbols": COUNTRIES}},
        {"name": "name", "type": "string"},
        {"name": "url", "type": "string"},
        {"name": "note", "type": ["null", "string"]},
        {"name": "score", "type": ["double", "null"]},
        {"name": "created_at", "type": {"type": "long", "logicalType": "timestamp-micros"}},
        {"name": "event_date", "type": {"type": "int", "logicalType": "date"}},
        {"name": "price", "type": {"type": "bytes", "logicalType": "decimal", "precision": 12, "scale": 2}},
        {"name": "session", "type": {"type": "fixed", "name": "Session", "size": 16}},
        {"name": "counter", "type": ["null", "long"]},
        {"name": "device", "type": {"type": "record", "name": "Device", "fields": [
            {"name": "os", "type": {"type": "enum", "name": "Os", "symbols": OSES}},
            {"name": "version", "type": "string"},
            {"name": "model", "type": ["null", "string"]},
        ]}},
        {"name": "tags", "type": {"type": "array", "items": "string"}},
        {"name": "metrics", "type": {"type": "map", "values": "double"}},
    ],
}

EPOCH = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
DAY0 = datetime.date(2026, 1, 1)


def records(n):
    rnd = random.Random(20261010)
    for i in range(n):
        yield {
            "id": i,
            "user_id": rnd.randrange(1, 5_000_000),
            "small": rnd.randrange(-1000, 1000),
            "amount": round(rnd.uniform(0, 10_000), 4),
            "ratio": rnd.random(),
            "flag": rnd.random() < 0.3,
            "event": rnd.choice(EVENTS),
            "country": rnd.choice(COUNTRIES),
            "name": " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(1, 4))),
            "url": f"https://example.com/{rnd.choice(WORDS)}/{rnd.randrange(1_000_000)}?ref={rnd.choice(WORDS)}",
            "note": None if rnd.random() < 0.7 else " ".join(rnd.choice(WORDS) for _ in range(rnd.randint(1, 8))),
            "score": None if rnd.random() < 0.1 else rnd.gauss(50, 15),
            "created_at": EPOCH + datetime.timedelta(microseconds=i * 31_536 + rnd.randrange(1_000_000)),
            "event_date": DAY0 + datetime.timedelta(days=rnd.randrange(365)),
            "price": decimal.Decimal(rnd.randrange(-10_000_000, 100_000_000)).scaleb(-2),
            "session": rnd.randbytes(16),
            "counter": None if rnd.random() < 0.5 else rnd.randrange(1 << 40),
            "device": {
                "os": rnd.choice(OSES),
                "version": f"{rnd.randint(1, 17)}.{rnd.randint(0, 9)}.{rnd.randint(0, 20)}",
                "model": None if rnd.random() < 0.2 else f"model-{rnd.randrange(500)}",
            },
            "tags": [rnd.choice(WORDS) for _ in range(rnd.randint(0, 3))],
            "metrics": {rnd.choice(WORDS): rnd.random() for _ in range(rnd.randint(0, 3))},
        }


if __name__ == "__main__":
    path, rows, codec = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    with open(path, "wb") as f:
        fastavro.writer(f, fastavro.parse_schema(SCHEMA), records(rows), codec=codec, sync_interval=64_000)
