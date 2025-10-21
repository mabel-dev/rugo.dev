#!/usr/bin/env python3
"""
Benchmark script to measure JSON lines reader performance improvements.
"""
import json
import sys
import time

import rugo.jsonl as rj

sys.path.insert(0, '/home/runner/work/rugo/rugo')



def generate_test_data(num_rows=100000):
    """Generate test JSON lines data with varied field types."""
    data = []
    for i in range(num_rows):
        row = {
            'id': i,
            'name': f'user_{i}',
            'email': f'user{i}@example.com',
            'age': 20 + (i % 50),
            'salary': 30000.0 + (i % 100) * 1000.0,
            'active': i % 2 == 0,
            'score': 85.5 + (i % 15),
            'department': ['Engineering', 'Sales', 'Marketing', 'HR'][i % 4],
        }
        data.append(json.dumps(row))
    return '\n'.join(data).encode('utf-8')


def benchmark_full_read(data, iterations=5):
    """Benchmark reading all columns."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = rj.read_jsonl(data)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    rows = result['num_rows']
    return avg_time, rows / avg_time


def benchmark_projection(data, columns, iterations=5):
    """Benchmark reading specific columns."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = rj.read_jsonl(data, columns=columns)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    rows = result['num_rows']
    return avg_time, rows / avg_time


def benchmark_schema(data, iterations=10):
    """Benchmark schema extraction."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        schema = rj.get_jsonl_schema(data)
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    return avg_time


def main():
    print("=" * 70)
    print("JSON Lines Reader SIMD Performance Benchmark")
    print("=" * 70)
    
    for num_rows in [10000, 50000, 100000, 250000]:
        print(f"\n### Testing with {num_rows:,} rows ###\n")
        data = generate_test_data(num_rows)
        
        # Full read
        avg_time, throughput = benchmark_full_read(data, iterations=5)
        print("Full read (all 8 columns):")
        print(f"  Time: {avg_time:.4f}s")
        print(f"  Throughput: {throughput:,.0f} rows/sec")
        print(f"  Data size: {len(data) / 1024 / 1024:.2f} MB")
        
        # Projection: 3 columns
        avg_time, throughput = benchmark_projection(data, ['id', 'name', 'salary'], iterations=5)
        print("\nProjection (3 columns: id, name, salary):")
        print(f"  Time: {avg_time:.4f}s")
        print(f"  Throughput: {throughput:,.0f} rows/sec")
        
        # Projection: 2 columns
        avg_time, throughput = benchmark_projection(data, ['id', 'email'], iterations=5)
        print("\nProjection (2 columns: id, email):")
        print(f"  Time: {avg_time:.4f}s")
        print(f"  Throughput: {throughput:,.0f} rows/sec")
        
        # Schema extraction
        avg_time = benchmark_schema(data, iterations=10)
        print("\nSchema extraction:")
        print(f"  Time: {avg_time:.6f}s")
    
    print("\n" + "=" * 70)
    print("Benchmark complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
