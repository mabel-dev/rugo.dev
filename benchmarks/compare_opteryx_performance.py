#!/usr/bin/env python3
"""
Performance comparison between rugo, Opteryx, and PyArrow JSON Lines readers.

This benchmark focuses on Python 3.11+ on Linux with 50-column datasets
to provide direct performance comparisons between the three implementations.

Note: This benchmark tests against:
- Opteryx's JSONL reader
  - Release 0.25.1: Uses Python decoder with csimdjson C/C++ extension
  - Main branch (0.26.0+): Includes Cython-based fast decoder with SIMD optimizations
- PyArrow's JSON reader (pyarrow.json.read_json)

To test against the latest Opteryx main branch:
    pip install git+https://github.com/mabel-dev/opteryx.git
"""
import json
import os
import platform
import sys
import time
from io import BytesIO
from typing import List
from typing import Tuple

import pyarrow.json as paj


# Add rugo to path if running from source
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(1, os.path.join(sys.path[0], "../opteryx"))

import opteryx
import rugo.jsonl as rj

# Check if Opteryx is available
try:
    import opteryx
    from opteryx.utils.file_decoders import jsonl_decoder as opteryx_jsonl_decoder
    HAS_OPTERYX = True
    OPTERYX_VERSION = opteryx.__version__ if hasattr(opteryx, '__version__') else "unknown"
    
except ImportError:
    HAS_OPTERYX = False
    OPTERYX_VERSION = None
    print("Warning: Opteryx not available. Install with: pip install opteryx")

# Check if PyArrow is available
try:
    import pyarrow as pa
    HAS_PYARROW = True
    PYARROW_VERSION = pa.__version__
except ImportError:
    HAS_PYARROW = False
    PYARROW_VERSION = None
    print("Warning: PyArrow not available. Install with: pip install pyarrow")


def generate_50_column_data(num_rows: int = 10000) -> bytes:
    """
    Generate test JSON Lines data with 50 columns.
    
    Columns include various data types:
    - Integer fields (id, counters)
    - String fields (names, emails, descriptions)
    - Float fields (measurements, scores)
    - Boolean fields (flags)
    
    Args:
        num_rows: Number of rows to generate
        
    Returns:
        Bytes containing JSONL data
    """
    data = []
    for i in range(num_rows):
        row = {
            # Integer columns (10 columns)
            'id': i,
            'user_id': 1000000 + i,
            'session_id': 2000000 + (i % 1000),
            'counter_a': i % 100,
            'counter_b': i % 500,
            'counter_c': i % 1000,
            'rank': i % 10000,
            'level': i % 50,
            'points': i * 10,
            'score_int': i % 10000,
            
            # String columns (15 columns)
            'username': f'user_{i}',
            'email': f'user{i}@example.com',
            'first_name': f'FirstName{i}',
            'last_name': f'LastName{i}',
            'city': ['New York', 'London', 'Tokyo', 'Paris', 'Berlin'][i % 5],
            'country': ['USA', 'UK', 'Japan', 'France', 'Germany'][i % 5],
            'department': ['Engineering', 'Sales', 'Marketing', 'HR', 'Finance'][i % 5],
            'job_title': ['Engineer', 'Manager', 'Analyst', 'Director', 'VP'][i % 5],
            'product_name': f'Product_{i % 100}',
            'category': ['Electronics', 'Clothing', 'Food', 'Books', 'Toys'][i % 5],
            'description': f'This is a description for item {i} with some text content',
            'notes': f'Additional notes and comments for record {i}',
            'tags': f'tag1,tag2,tag{i % 10}',
            'status': ['active', 'inactive', 'pending', 'archived'][i % 4],
            'reference_id': f'REF{i:010d}',
            
            # Float columns (15 columns)
            'price': 10.99 + (i % 1000) * 0.5,
            'discount': 0.0 + (i % 50) * 0.01,
            'tax_rate': 0.08 + (i % 10) * 0.001,
            'shipping_cost': 5.99 + (i % 20) * 0.25,
            'weight': 0.5 + (i % 100) * 0.1,
            'height': 10.0 + (i % 50) * 0.5,
            'width': 5.0 + (i % 30) * 0.3,
            'depth': 3.0 + (i % 20) * 0.2,
            'temperature': 20.0 + (i % 40) * 0.5,
            'humidity': 40.0 + (i % 60) * 0.5,
            'latitude': 40.7128 + (i % 100) * 0.01,
            'longitude': -74.0060 + (i % 100) * 0.01,
            'rating': 1.0 + (i % 50) * 0.1,
            'confidence_score': 0.5 + (i % 50) * 0.01,
            'probability': 0.0 + (i % 100) * 0.01,
            
            # Boolean columns (10 columns)
            'is_active': i % 2 == 0,
            'is_verified': i % 3 == 0,
            'is_premium': i % 5 == 0,
            'is_featured': i % 7 == 0,
            'has_discount': i % 4 == 0,
            'has_shipping': i % 3 == 0,
            'requires_approval': i % 6 == 0,
            'is_public': i % 2 == 0,
            'is_deleted': i % 100 == 0,
            'is_locked': i % 50 == 0,
        }
        data.append(json.dumps(row))
    
    return '\n'.join(data).encode('utf-8')


def benchmark_rugo_full_read(data: bytes, iterations: int = 5) -> Tuple[float, int]:
    """Benchmark rugo reading all columns."""
    times = []
    result = None
    
    for _ in range(iterations):
        start = time.perf_counter()
        result = rj.read_jsonl(data)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    rows = result['num_rows']
    return avg_time, rows


def benchmark_rugo_projection(data: bytes, columns: List[str], iterations: int = 5) -> Tuple[float, int]:
    """Benchmark rugo reading specific columns."""
    times = []
    result = None
    
    for _ in range(iterations):
        start = time.perf_counter()
        result = rj.read_jsonl(data, columns=columns)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    rows = result['num_rows']
    return avg_time, rows


def benchmark_opteryx_full_read(data: bytes, iterations: int = 5) -> Tuple[float, int]:
    """Benchmark Opteryx reading all columns."""
    if not HAS_OPTERYX:
        return None, None
    
    times = []
    
    for _ in range(iterations):
        start = time.perf_counter()
        rows, cols, size, table = opteryx_jsonl_decoder(data)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    return avg_time, rows


def benchmark_opteryx_projection(data: bytes, columns: List[str], iterations: int = 5) -> Tuple[float, int]:
    """
    Benchmark Opteryx reading specific columns.
    
    Note: Opteryx's jsonl_decoder doesn't support true projection pushdown
    like rugo does. It reads all data and then filters columns after parsing.
    This is a fundamental difference in architecture.
    """
    if not HAS_OPTERYX:
        return None, None
    
    times = []
    
    # Opteryx reads all columns then selects, so we'll measure full read + select
    # to be fair in comparison
    for _ in range(iterations):
        start = time.perf_counter()
        rows, cols, size, table = opteryx_jsonl_decoder(data)
        # Simulate projection by selecting columns from the result
        if table and columns:
            try:
                table = table.select(columns)
            except KeyError:
                # If some columns don't exist, just use the full table
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    return avg_time, rows


def benchmark_pyarrow_full_read(data: bytes, iterations: int = 5) -> Tuple[float, int]:
    """Benchmark PyArrow reading all columns."""
    if not HAS_PYARROW:
        return None, None
    
    times = []
    result = None
    
    for _ in range(iterations):
        # PyArrow requires a file-like object
        start = time.perf_counter()
        result = paj.read_json(BytesIO(data))
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    rows = len(result) if result else 0
    return avg_time, rows


def benchmark_pyarrow_projection(data: bytes, columns: List[str], iterations: int = 5) -> Tuple[float, int]:
    """
    Benchmark PyArrow reading specific columns.
    
    Note: PyArrow's read_json doesn't support column projection at parse time.
    It reads all data and then we select columns after parsing, similar to Opteryx.
    """
    if not HAS_PYARROW:
        return None, None
    
    times = []
    result = None
    
    for _ in range(iterations):
        start = time.perf_counter()
        result = pa.json.read_json(BytesIO(data))
        # Select only requested columns
        if result and columns:
            try:
                result = result.select(columns)
            except KeyError:
                # If some columns don't exist, just use the full table
                pass
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    rows = len(result) if result else 0
    return avg_time, rows


def format_throughput(rows: int, time_sec: float) -> str:
    """Format throughput in a human-readable way."""
    throughput = rows / time_sec
    if throughput >= 1_000_000:
        return f"{throughput / 1_000_000:.2f}M rows/sec"
    elif throughput >= 1_000:
        return f"{throughput / 1_000:.2f}K rows/sec"
    else:
        return f"{throughput:.0f} rows/sec"


def print_system_info():
    """Print system information."""
    print("=" * 80)
    print("System Information")
    print("=" * 80)
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"Processor: {platform.processor()}")
    print(f"Architecture: {platform.machine()}")
    if HAS_OPTERYX:
        print(f"Opteryx version: {OPTERYX_VERSION}")
        decoder_type = "Cython-based (fast)"
        print(f"Opteryx decoder: {decoder_type}")
    if HAS_PYARROW:
        print(f"PyArrow version: {PYARROW_VERSION}")
    print()


def print_benchmark_header(num_rows: int, data_size: int):
    """Print benchmark header."""
    print("=" * 80)
    print("JSONL Performance Comparison: rugo vs Opteryx vs PyArrow")
    print("=" * 80)
    print(f"Dataset: {num_rows:,} rows, 50 columns")
    print(f"Data size: {data_size / 1024 / 1024:.2f} MB")
    print("Iterations: 5 per test (averaged)")
    print()


def run_benchmark_suite(num_rows: int):
    """Run complete benchmark suite for given row count."""
    print(f"\n{'─' * 80}")
    print(f"Testing with {num_rows:,} rows")
    print(f"{'─' * 80}\n")
    
    # Generate test data
    print("Generating test data...")
    data = generate_50_column_data(num_rows)
    print(f"Generated {len(data):,} bytes of JSONL data\n")
    
    # Test 1: Full read (all 50 columns)
    print("Test 1: Full Read (all 50 columns)")
    print("-" * 40)
    
    # Rugo
    rugo_time, rugo_rows = benchmark_rugo_full_read(data, iterations=5)
    rugo_throughput = format_throughput(rugo_rows, rugo_time)
    print(f"  rugo:    {rugo_time:.4f}s ({rugo_throughput})")
    
    # Opteryx
    if HAS_OPTERYX:
        opteryx_time, opteryx_rows = benchmark_opteryx_full_read(data, iterations=5)
        opteryx_throughput = format_throughput(opteryx_rows, opteryx_time)
        print(f"  Opteryx: {opteryx_time:.4f}s ({opteryx_throughput})")
        
        # Comparison
        if opteryx_time < rugo_time:
            speedup = rugo_time / opteryx_time
            print(f"  → Opteryx is {speedup:.2f}x faster than rugo")
        else:
            speedup = opteryx_time / rugo_time
            print(f"  → rugo is {speedup:.2f}x faster than Opteryx")
    else:
        print("  Opteryx: Not available")
    
    # PyArrow
    if HAS_PYARROW:
        pyarrow_time, pyarrow_rows = benchmark_pyarrow_full_read(data, iterations=5)
        pyarrow_throughput = format_throughput(pyarrow_rows, pyarrow_time)
        print(f"  PyArrow: {pyarrow_time:.4f}s ({pyarrow_throughput})")
        
        # Comparison
        if pyarrow_time < rugo_time:
            speedup = rugo_time / pyarrow_time
            print(f"  → PyArrow is {speedup:.2f}x faster than rugo")
        else:
            speedup = pyarrow_time / rugo_time
            print(f"  → rugo is {speedup:.2f}x faster than PyArrow")
    else:
        print("  PyArrow: Not available")
    
    print()
    
    # Test 2: Projection (10 columns)
    print("Test 2: Projection (10 columns)")
    print("-" * 40)
    
    projection_cols = [
        'id', 'username', 'email', 'city', 'country',
        'price', 'rating', 'is_active', 'is_verified', 'is_premium'
    ]
    
    # Rugo
    rugo_time, rugo_rows = benchmark_rugo_projection(data, projection_cols, iterations=5)
    rugo_throughput = format_throughput(rugo_rows, rugo_time)
    print(f"  rugo:    {rugo_time:.4f}s ({rugo_throughput})")
    
    # Opteryx
    if HAS_OPTERYX:
        opteryx_time, opteryx_rows = benchmark_opteryx_projection(data, projection_cols, iterations=5)
        opteryx_throughput = format_throughput(opteryx_rows, opteryx_time)
        print(f"  Opteryx: {opteryx_time:.4f}s ({opteryx_throughput})")
        
        # Comparison
        if opteryx_time < rugo_time:
            speedup = rugo_time / opteryx_time
            print(f"  → Opteryx is {speedup:.2f}x faster than rugo")
        else:
            speedup = opteryx_time / rugo_time
            print(f"  → rugo is {speedup:.2f}x faster than Opteryx")
    else:
        print("  Opteryx: Not available")
    
    # PyArrow
    if HAS_PYARROW:
        pyarrow_time, pyarrow_rows = benchmark_pyarrow_projection(data, projection_cols, iterations=5)
        pyarrow_throughput = format_throughput(pyarrow_rows, pyarrow_time)
        print(f"  PyArrow: {pyarrow_time:.4f}s ({pyarrow_throughput})")
        
        # Comparison
        if pyarrow_time < rugo_time:
            speedup = rugo_time / pyarrow_time
            print(f"  → PyArrow is {speedup:.2f}x faster than rugo")
        else:
            speedup = pyarrow_time / rugo_time
            print(f"  → rugo is {speedup:.2f}x faster than PyArrow")
    else:
        print("  PyArrow: Not available")
    
    print()
    
    # Test 3: Projection (5 columns)
    print("Test 3: Projection (5 columns)")
    print("-" * 40)
    
    projection_cols = ['id', 'username', 'email', 'price', 'rating']
    
    # Rugo
    rugo_time, rugo_rows = benchmark_rugo_projection(data, projection_cols, iterations=5)
    rugo_throughput = format_throughput(rugo_rows, rugo_time)
    print(f"  rugo:    {rugo_time:.4f}s ({rugo_throughput})")
    
    # Opteryx
    if HAS_OPTERYX:
        opteryx_time, opteryx_rows = benchmark_opteryx_projection(data, projection_cols, iterations=5)
        opteryx_throughput = format_throughput(opteryx_rows, opteryx_time)
        print(f"  Opteryx: {opteryx_time:.4f}s ({opteryx_throughput})")
        
        # Comparison
        if opteryx_time < rugo_time:
            speedup = rugo_time / opteryx_time
            print(f"  → Opteryx is {speedup:.2f}x faster than rugo")
        else:
            speedup = opteryx_time / rugo_time
            print(f"  → rugo is {speedup:.2f}x faster than Opteryx")
    else:
        print("  Opteryx: Not available")
    
    # PyArrow
    if HAS_PYARROW:
        pyarrow_time, pyarrow_rows = benchmark_pyarrow_projection(data, projection_cols, iterations=5)
        pyarrow_throughput = format_throughput(pyarrow_rows, pyarrow_time)
        print(f"  PyArrow: {pyarrow_time:.4f}s ({pyarrow_throughput})")
        
        # Comparison
        if pyarrow_time < rugo_time:
            speedup = rugo_time / pyarrow_time
            print(f"  → PyArrow is {speedup:.2f}x faster than rugo")
        else:
            speedup = pyarrow_time / rugo_time
            print(f"  → rugo is {speedup:.2f}x faster than PyArrow")
    else:
        print("  PyArrow: Not available")


def main():
    """Main benchmark execution."""
    print_system_info()
    
    warnings = []
    if not HAS_OPTERYX:
        warnings.append("⚠️  WARNING: Opteryx is not installed!")
        warnings.append("Install with: pip install opteryx")
    
    if not HAS_PYARROW:
        warnings.append("⚠️  WARNING: PyArrow is not installed!")
        warnings.append("Install with: pip install pyarrow")
    
    if warnings:
        for warning in warnings:
            print(warning)
        print()
    
    # Test with different dataset sizes
    for num_rows in [10_000, 50_000, 100_000]:
        run_benchmark_suite(num_rows)
    
    print("\n" + "=" * 80)
    print("Benchmark Complete!")
    print("=" * 80)
    
    notes = []
    if not HAS_OPTERYX:
        notes.append("Opteryx benchmarks were skipped. Install Opteryx to run full comparison.")
    if not HAS_PYARROW:
        notes.append("PyArrow benchmarks were skipped. Install PyArrow to run full comparison.")
    
    if notes:
        print("\nNote:")
        for note in notes:
            print(f"  - {note}")


if __name__ == "__main__":
    main()
