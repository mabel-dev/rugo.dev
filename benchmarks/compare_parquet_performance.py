#!/usr/bin/env python3
"""
Compare Parquet read performance between rugo and PyArrow.

Produces an in-memory Parquet dataset (using pyarrow) and measures:
- full read (all columns)
- projection (subset of columns)

Requires pyarrow to generate and read Parquet data. If pyarrow is not
installed the script will exit with a helpful message.
"""
import os
import sys
import time
import gc
import statistics
import argparse
from io import BytesIO
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyarrow as pa
import pyarrow.parquet as pq

import rugo.parquet as rp


# ANSI colors
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_RED = "\x1b[31m"
_RESET = "\x1b[0m"


def generate_table(num_rows: int = 10000) -> pa.Table:
    import pandas as pd

    # Generate a table containing only the column types rugo currently
    # supports/aims to support for this benchmark: int64 and UTF-8 strings.
    # If rugo learns additional types later we can add them here.
    df = pd.DataFrame({
        'int64_col': pd.Series(range(num_rows), dtype='int64'),
        'str_col': pd.Series([f'user_{i}' for i in range(num_rows)], dtype='object'),
    })
    return pa.Table.from_pandas(df)


def table_to_parquet_bytes(table: pa.Table) -> bytes:
    buf = BytesIO()
    pq.write_table(table, buf)
    buf.seek(0)
    return buf.getvalue()


def benchmark_rugo_parquet(data: bytes, columns: List[str] = None, iterations: int = 5, warmup: int = 1) -> Tuple[float, int]:
    # Warmup iterations (not timed)
    for _ in range(warmup):
        gc.collect()
        _ = rp.read_parquet(data, column_names=columns)

    times = []
    rows = 0
    for _ in range(iterations):
        gc.collect()
        start = time.perf_counter()
        res = rp.read_parquet(data, column_names=columns)
        elapsed = time.perf_counter() - start
        times.append(elapsed)

        # rugo.read_parquet returns a dict. Prefer explicit 'num_rows' if present.
        if isinstance(res, dict):
            if 'num_rows' in res and res['num_rows'] is not None:
                rows = res['num_rows']
            else:
                # Try to infer row count from 'row_groups' structure
                rg = res.get('row_groups')
                if rg:
                    total = 0
                    for group in rg:
                        found = False
                        for col in group:
                            if isinstance(col, (list, tuple)):
                                total += len(col)
                                found = True
                                break
                        if not found:
                            continue
                    if total > 0:
                        rows = total
                else:
                    cols = res.get('columns')
                    if cols and isinstance(cols, list) and len(cols) > 0:
                        try:
                            rows = len(cols[0])
                        except Exception:
                            pass

    avg = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0.0
    return avg, std, rows


def benchmark_pyarrow_parquet(data: bytes, columns: List[str] = None, iterations: int = 5, warmup: int = 1) -> Tuple[float, int]:
    # Warmup iterations (not timed)
    for _ in range(warmup):
        gc.collect()
        _ = pq.read_table(BytesIO(data), columns=columns)

    times = []
    rows = 0
    for _ in range(iterations):
        gc.collect()
        start = time.perf_counter()
        table = pq.read_table(BytesIO(data), columns=columns)
        # Materialize into Python lists to match rugo's returned structure
        try:
            pyd = table.to_pydict()
        except KeyError:
            # Fallback: materialize columns individually
            pyd = {name: table.column(i).to_pylist() for i, name in enumerate(table.column_names)}
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        rows = len(next(iter(pyd.values()))) if pyd else 0

    avg = statistics.mean(times)
    std = statistics.stdev(times) if len(times) > 1 else 0.0
    return avg, std, rows


def format_throughput(rows: int, time_sec: float) -> str:
    if time_sec == 0:
        return "inf"
    rate = rows / time_sec
    if rate >= 1_000_000:
        return f"{rate/1_000_000:.2f}M r/s"
    if rate >= 1_000:
        return f"{rate/1_000:.2f}K r/s"
    return f"{rate:.0f} r/s"


def main():
    parser = argparse.ArgumentParser(description="Parquet performance comparison: rugo vs pyarrow")
    parser.add_argument("--rows", type=int, default=200000, help="Number of rows to generate (default: 200000)")
    parser.add_argument("--iterations", type=int, default=5, help="Benchmark iterations per test (default: 5)")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup iterations before timing (default: 1)")
    parser.add_argument("--projection-cols", type=str, default="int64_col,str_col",
                        help="Comma-separated list of projection columns (default: int64_col,str_col)")
    args = parser.parse_args()

    num_rows = args.rows
    iterations = args.iterations
    warmup = args.warmup
    projection = [c.strip() for c in args.projection_cols.split(",") if c.strip()]

    print(f"Generating Parquet table with {num_rows:,} rows...")
    table = generate_table(num_rows)
    data = table_to_parquet_bytes(table)
    print(f"Generated {len(data):,} bytes of Parquet data")

    # Detect which columns rugo decodes by doing a single quick read.
    # Make this robust by scanning all row_groups and marking a column
    # decoded if any row_group contains a list/tuple for that column index.
    sample = rp.read_parquet(data, column_names=None)
    decoded = set()
    if isinstance(sample, dict):
        row_groups = sample.get('row_groups') or []
        col_names = sample.get('column_names') or []
        # iterate over row groups and columns, mark column as decoded
        for rg in row_groups:
            if not isinstance(rg, (list, tuple)):
                continue
            for idx, col in enumerate(rg):
                name = col_names[idx] if idx < len(col_names) else f"col{idx}"
                if isinstance(col, (list, tuple)):
                    decoded.add(name)
        # also check 'columns' key as a fallback
        if not decoded and 'columns' in sample and isinstance(sample['columns'], list):
            cols = sample['columns']
            for idx, col in enumerate(cols):
                name = col_names[idx] if idx < len(col_names) else f"col{idx}"
                if isinstance(col, (list, tuple)):
                    decoded.add(name)

    # Types rugo currently supports (int64 and strings)
    intended = ['int64_col', 'str_col']

    # Build colored status line
    status_parts = []
    for c in intended:
        found = any(c == name for name, _ in decoded)
        if found:
            status_parts.append(f"{_GREEN}{c}{_RESET}")
        else:
            status_parts.append(f"{_RED}{c}{_RESET}")
    status = ", ".join(status_parts)
    print(f"rugo decoded columns (green=decoded, red=not decoded): {status}")

    # Ensure the requested projection columns exist in the generated table
    available_columns = list(table.column_names)
    proj_before = projection[:]
    projection = [c for c in projection if c in available_columns]
    if not projection:
        # fallback to the first two available columns
        projection = available_columns[:2]
        print(f"Requested projection {proj_before} not found in table; using {projection} instead")

    # Collect results for full read and projection (rugo)
    print("Running full-read benchmarks (rugo)...")
    r_full_avg, r_full_std, r_rows = benchmark_rugo_parquet(data, columns=None, iterations=iterations, warmup=warmup)

    print("Running projection benchmarks (rugo)...")
    r_proj_avg, r_proj_std, _ = benchmark_rugo_parquet(data, columns=projection, iterations=iterations, warmup=warmup)

    # Summary table
    print("\n" + "=" * 120)
    print("Parquet benchmark summary (avg ± std; parse vs materialize for pyarrow)")
    print("=" * 120)

    colfmt = "{:<14} {:>14} {:>14} {:>14} {:>14} {:>14} {:>14} {:>12}"
    print(colfmt.format("Test", "rugo (s)", "pyarrow_parse", "pyarrow_mat", "pyarrow_tot", "rugo rps", "pyarrow rps", "ratio"))
    print("-" * 120)

    def compute_speedup(r_avg, pa_tot):
        if r_avg == 0:
            return float('inf')
        return pa_tot / r_avg

    def format_row(test_name, r_avg, pa_parse_avg, pa_mat_avg, total_rows):
        pa_tot_avg = pa_parse_avg + pa_mat_avg
        # Use the generated total row count for throughput comparisons
        r_th = format_throughput(total_rows, r_avg)
        pa_th = format_throughput(total_rows, pa_tot_avg)
        speedup = compute_speedup(r_avg, pa_tot_avg)
        ratio = f"{speedup:.2f}x"
        return colfmt.format(
            test_name,
            f"{r_avg:.4f}",
            f"{pa_parse_avg:.4f}",
            f"{pa_mat_avg:.4f}",
            f"{pa_tot_avg:.4f}",
            f"{r_th}",
            f"{pa_th}",
            ratio,
        )

    # For pyarrow we measured total (parse+mat). We need to split parse vs mat:
    # We measured pa_full_avg as parse+mat combined (read_table + to_pydict()).
    # To get a parse-only and materialize-only measurement, run a quick parse-only/materialize-only sampling now.
    # Parse-only sample (small number of iterations)
    pa_parse_avg, _, _ = benchmark_pyarrow_parquet(data, columns=None, iterations=3, warmup=1)
    # Materialize-only sample: read_table once, then time to_pydict repeatedly
    tbl = pq.read_table(BytesIO(data))
    mat_times = []
    for _ in range(3):
        gc.collect()
        t0 = time.perf_counter()
        tbl.to_pydict()
        mat_times.append(time.perf_counter() - t0)
    pa_mat_avg = statistics.mean(mat_times)

    # Projection parse/materialize samples
    pa_parse_p_avg, _, _ = benchmark_pyarrow_parquet(data, columns=projection, iterations=3, warmup=1)
    tbl_p = pq.read_table(BytesIO(data), columns=projection)
    mat_times_p = []
    for _ in range(3):
        gc.collect()
        t0 = time.perf_counter()
        tbl_p.to_pydict()
        mat_times_p.append(time.perf_counter() - t0)
    pa_mat_p_avg = statistics.mean(mat_times_p)

    print(format_row("Full read", r_full_avg, pa_parse_avg, pa_mat_avg, num_rows))
    print(format_row("Projection", r_proj_avg, pa_parse_p_avg, pa_mat_p_avg, num_rows))




if __name__ == '__main__':
    main()
