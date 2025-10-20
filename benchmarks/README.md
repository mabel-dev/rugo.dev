# Benchmarks

This directory contains performance benchmarks for the rugo library.

## Available Benchmarks

### compare_opteryx_performance.py

Comprehensive performance comparison between rugo and Opteryx JSONL readers.

**What it tests:**
- 50-column dataset with mixed types (integers, strings, floats, booleans)
- Multiple dataset sizes (10K, 50K, 100K rows)
- Full read operations (all columns)
- Projection operations (subset of columns)

**How to run:**
```bash
# With Opteryx installed for full comparison
pip install opteryx
python benchmarks/compare_opteryx_performance.py

# Without Opteryx (rugo-only benchmarks)
python benchmarks/compare_opteryx_performance.py
```

**Example output:**
```
================================================================================
System Information
================================================================================
Python version: 3.12.3 (main, Aug 14 2025, 17:47:21) [GCC 13.3.0]
Platform: Linux-6.11.0-1018-azure-x86_64-with-glibc2.39

────────────────────────────────────────────────────────────────────────────────
Testing with 100,000 rows
────────────────────────────────────────────────────────────────────────────────

Test 1: Full Read (all 50 columns)
----------------------------------------
  rugo:    0.918s (109K rows/sec)
  Opteryx: 2.864s (35K rows/sec)
  → rugo is 3.12x faster
```

See [PERFORMANCE_COMPARISON.md](../PERFORMANCE_COMPARISON.md) for detailed results and analysis.

## Adding New Benchmarks

When adding a new benchmark:

1. Create a standalone Python script in this directory
2. Use `time.perf_counter()` for timing measurements
3. Run multiple iterations and report averages
4. Include system information in output
5. Document the benchmark in this README
6. Add results to relevant documentation

## Dependencies

Different benchmarks may require different dependencies:

- `rugo` - Always required
- `opteryx` - For Opteryx comparisons
- `pyarrow` - For PyArrow comparisons
- Other dependencies as needed for specific benchmarks

Install all benchmark dependencies:
```bash
pip install rugo[test] opteryx
```
