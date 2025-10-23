#!/usr/bin/env python3
"""
Compare CSV read performance between rugo and PyArrow.

Generates an in-memory CSV dataset and benchmarks full read and projection.
"""
import os
import sys
import time
from io import BytesIO
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyarrow.csv as pacsv

import rugo.csv as rc


def generate_csv_bytes(num_rows: int = 10000) -> bytes:
    lines = []
    header = ["id", "name", "value_int", "value_float", "flag"]
    lines.append(",".join(header))
    for i in range(num_rows):
        row = [
            str(i),
            f'user_{i}',
            str(i % 1000),
            f"{float(i) * 0.01}",
            "true" if i % 2 == 0 else "false",
        ]
        lines.append(",".join(row))
    return "\n".join(lines).encode("utf-8")


def benchmark_rugo_csv(data: bytes, columns: List[str] = None, iterations: int = 5) -> Tuple[float, int]:
    times = []
    rows = 0
    for _ in range(iterations):
        start = time.perf_counter()
        res = rc.read_csv(data, columns=columns)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        rows = res.get('num_rows', rows)
    return sum(times) / len(times), rows


def benchmark_pyarrow_csv(data: bytes, columns: List[str] = None, iterations: int = 5) -> Tuple[float, int]:
    times = []
    rows = 0
    for _ in range(iterations):
        start = time.perf_counter()
        table = pacsv.read_csv(BytesIO(data))
        if columns:
            try:
                table = table.select(columns)
            except KeyError:
                # some pyarrow versions may raise KeyError for missing columns
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        rows = len(table)
    return sum(times) / len(times), rows


def format_throughput(rows: int, time_sec: float) -> str:
    if time_sec == 0:
        return "inf"
    rate = rows / time_sec
    if rate >= 1_000_000:
        return f"{rate/1_000_000:.2f}M rows/sec"
    if rate >= 1_000:
        return f"{rate/1_000:.2f}K rows/sec"
    return f"{rate:.0f} rows/sec"


def main():
    num_rows = 100000
    print(f"Generating CSV with {num_rows:,} rows...")
    data = generate_csv_bytes(num_rows)
    print(f"Generated {len(data):,} bytes of CSV data")

    projection = ['id', 'name', 'value_float']

    r_time, r_rows = benchmark_rugo_csv(data, columns=None)
    pa_time, pa_rows = benchmark_pyarrow_csv(data, columns=None)
    print(f"rugo full read: {r_time:.4f}s ({format_throughput(r_rows, r_time)})")
    print(f"pyarrow full read: {pa_time:.4f}s ({format_throughput(pa_rows, pa_time)})")

    r_time_p, _ = benchmark_rugo_csv(data, columns=projection)
    pa_time_p, _ = benchmark_pyarrow_csv(data, columns=projection)
    print(f"rugo projection: {r_time_p:.4f}s")
    print(f"pyarrow projection: {pa_time_p:.4f}s")


if __name__ == '__main__':
    main()
