# Testing Against Opteryx Main Branch (Cython Decoder)

## Current Status

### Beta Version Availability

As of October 2025, there are **no beta versions** of Opteryx 0.26.0 released on PyPI. The latest stable release is **0.25.1**, which uses the Python-based decoder with csimdjson.

The main branch on GitHub contains version **0.26.0-beta.1666** with the Cython-based fast decoder, but this is not yet available as a pip-installable package.

### Installation Options

#### Option 1: Install from GitHub (Main Branch)
```bash
pip install git+https://github.com/mabel-dev/opteryx.git
```

**Status**: Network issues prevented successful installation during testing. The installation requires:
- Compiling Cython extensions
- Downloading/building dependencies
- May require additional C++ build tools

#### Option 2: Wait for Official Beta Release
The Opteryx team may release 0.26.0-beta to PyPI in the future, at which point it can be tested with:
```bash
pip install opteryx==0.26.0b1  # or similar version
```

### Why Testing Against Main Branch is Important

The main branch includes a significantly different architecture:

1. **Cython-based decoder** vs Python-based decoder
2. **Custom SIMD implementations** (AVX/NEON) for text scanning
3. **Single-pass multi-column extraction** for better performance
4. **Fast float/integer parsing** using optimized algorithms
5. **Memory pre-allocation** based on line counting
6. **Projection pushdown support** (similar to rugo)

These changes are expected to make Opteryx's JSONL reader significantly faster than the 0.25.1 release tested in the current benchmarks.

## Recommendation

### For Now
1. Document that benchmarks compare against **Opteryx 0.25.1** (release)
2. Acknowledge that **main branch (0.26.0+)** has a faster Cython decoder
3. Commit to **re-running benchmarks** when 0.26.0 is officially released

### For Future Work
1. Monitor Opteryx releases for 0.26.0 beta/stable
2. Re-run comprehensive benchmarks when available
3. Update comparison documentation with new results
4. Consider implementing improvements identified in the decoder analysis

## Alternative: Docker-Based Testing

If GitHub installation continues to fail, an alternative approach would be:

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y git build-essential
RUN pip install cython numpy
RUN git clone https://github.com/mabel-dev/opteryx.git
WORKDIR /opteryx
RUN pip install -e .
# Then run benchmarks
```

However, this is beyond the scope of the current PR and should be done as a separate follow-up task.

## Improvements to Implement (From Analysis)

Rather than waiting for the beta release, rugo can proactively implement improvements identified from analyzing the Opteryx decoder:

### High Priority
1. **Integrate fast_float library** - Easy win, significant impact on float parsing
2. **Implement single-pass multi-column extraction** - More complex but high value
3. **Add custom fast integer parser** - Moderate effort, good impact

These improvements will strengthen rugo's position regardless of Opteryx's performance.

See `OPTERYX_DECODER_ANALYSIS.md` for detailed analysis and implementation recommendations.
