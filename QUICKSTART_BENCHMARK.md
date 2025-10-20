# Quick Start: Running the Performance Comparison

This guide helps you quickly run the rugo vs Opteryx performance comparison.

## Prerequisites

- Python 3.11+ (tested with 3.12)
- Linux x86_64 (for optimal SIMD performance)

## Installation

### Option 1: Quick Install (PyPI)

```bash
# Install rugo and opteryx
pip install rugo opteryx

# Run the benchmark
python -m benchmarks.compare_opteryx_performance
```

### Option 2: From Source

```bash
# Clone the repository
git clone https://github.com/mabel-dev/rugo.git
cd rugo

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
pip install opteryx

# Compile rugo (if needed)
make compile

# Run the benchmark
python benchmarks/compare_opteryx_performance.py
```

## Running the Benchmark

The benchmark automatically tests:
- 3 dataset sizes: 10K, 50K, 100K rows
- 50 columns with mixed types
- 3 operations: Full read, 10-column projection, 5-column projection

### Expected Output

```
================================================================================
System Information
================================================================================
Python version: 3.12.3
Platform: Linux-6.11.0-1018-azure-x86_64-with-glibc2.39
...

────────────────────────────────────────────────────────────────────────────────
Testing with 100,000 rows
────────────────────────────────────────────────────────────────────────────────

Test 1: Full Read (all 50 columns)
----------------------------------------
  rugo:    0.918s (109K rows/sec)
  Opteryx: 2.864s (35K rows/sec)
  → rugo is 3.12x faster
```

## Without Opteryx

The benchmark works even without Opteryx installed:

```bash
# Install only rugo
pip install rugo

# Run benchmark (rugo-only mode)
python benchmarks/compare_opteryx_performance.py
```

It will show a warning and run rugo benchmarks only.

## Customizing the Benchmark

Edit `benchmarks/compare_opteryx_performance.py` to:

- Change dataset sizes: Modify the `for num_rows in [10_000, 50_000, 100_000]` line
- Add more column configurations: Edit the projection_cols lists
- Adjust iterations: Change `iterations=5` parameter in benchmark functions

## Interpreting Results

- **Throughput**: Higher is better (rows/second)
- **Speedup**: How many times faster rugo is compared to Opteryx
- **Projection benefit**: Notice how rugo gets faster with fewer columns (true pushdown)

## Troubleshooting

### "Module not found" error

```bash
# Make sure you're in the rugo directory
cd /path/to/rugo

# Install in development mode
pip install -e .
```

### Slow performance on non-x86 platforms

SIMD optimizations (AVX2/SSE2) are for x86_64 only. ARM platforms use NEON or scalar fallback.

### Memory errors with large datasets

The benchmark generates data in memory. Reduce dataset sizes if you run out of RAM:

```python
# In compare_opteryx_performance.py, change:
for num_rows in [10_000, 50_000]  # Removed 100_000
```

## Results Documentation

After running, see:
- `PERFORMANCE_COMPARISON.md` - Detailed analysis
- `BENCHMARK_SUMMARY.md` - Executive summary
- `JSONL_SIMD_OPTIMIZATIONS.md` - Technical details

## Contributing

Found a performance issue or want to add more benchmarks? Please open an issue or PR at:
https://github.com/mabel-dev/rugo/issues
