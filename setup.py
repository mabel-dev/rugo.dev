#!/usr/bin/env python3
"""
Setup script for rugo - A Cython-based file decoders library
"""

import os
import platform

from Cython.Build import cythonize
from setuptools import Extension
from setuptools import setup
from setuptools.command.build_ext import build_ext as build_ext_orig

extra_compile_args = ["-O3", "-std=c++17"]
if platform.system() == "Darwin":
    # Use native architecture by default, or environment variable if set
    default_arch = platform.machine()  # Will be 'arm64' on Apple Silicon, 'x86_64' on Intel
    # CIBW_ARCHS_MACOS may be set to 'auto' by cibuildwheel; skip placeholder
    archs = os.environ.get("CIBW_ARCHS_MACOS", default_arch).split()
    for arch in archs:
        # Ignore non-concrete arch specifiers (common placeholders)
        if not arch or arch.lower() in ("auto", "native", "none"):
            continue
        extra_compile_args.extend(["-arch", arch])

def get_vendor_sources():
    """Get vendored compression library sources"""
    vendor_sources = []
    
    # Snappy sources (minimal set for decompression only) - these are C++
    snappy_sources = [
        "rugo/parquet/vendor/snappy/snappy.cc",
        "rugo/parquet/vendor/snappy/snappy-sinksource.cc", 
        "rugo/parquet/vendor/snappy/snappy-stubs-internal.cc"
    ]
    vendor_sources.extend(snappy_sources)
    
    # Zstd sources (decompression modules only) - compiled as C++
    zstd_sources = [
        # Common modules
        "rugo/parquet/vendor/zstd/common/entropy_common.cpp",
        "rugo/parquet/vendor/zstd/common/fse_decompress.cpp",
        "rugo/parquet/vendor/zstd/common/zstd_common.cpp",
        "rugo/parquet/vendor/zstd/common/xxhash.cpp",
        "rugo/parquet/vendor/zstd/common/error_private.cpp",
        "rugo/parquet/vendor/zstd/decompress/zstd_decompress.cpp",
        "rugo/parquet/vendor/zstd/decompress/zstd_decompress_block.cpp",
        "rugo/parquet/vendor/zstd/decompress/huf_decompress.cpp",
        "rugo/parquet/vendor/zstd/decompress/zstd_ddict.cpp"
    ]

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        # BMI2-enabled builds expect this ASM fast path to be present on x86-64.
        zstd_sources.append("rugo/parquet/vendor/zstd/decompress/huf_decompress_amd64.S")

    vendor_sources.extend(zstd_sources)
    
    return vendor_sources

def get_extensions():
    """Define the Cython extensions to build"""
    extensions = []
    
    # Parquet decoder extension with compression support
    parquet_ext = Extension(
        "rugo.parquet",
        sources=[
            "rugo/parquet/parquet_reader.pyx",
            "rugo/parquet/metadata.cpp",
            "rugo/parquet/bloom_filter.cpp",
            "rugo/parquet/decode.cpp",
            "rugo/parquet/compression.cpp",
        ] + get_vendor_sources(),  # ADD: vendored compression libraries
        include_dirs=[
            "rugo/parquet/vendor/snappy",      # Snappy headers
            "rugo/parquet/vendor/zstd",        # Zstd main header
            "rugo/parquet/vendor/zstd/common", # Zstd common headers
            "rugo/parquet/vendor/zstd/decompress" # Zstd decompress headers
        ],
        define_macros=[
            ("HAVE_SNAPPY", "1"),
            ("HAVE_ZSTD", "1"),
            ("ZSTD_STATIC_LINKING_ONLY", "1")  # Enable zstd static linking
        ],
        language="c++",
        extra_compile_args=extra_compile_args,
        extra_link_args=[],
    )
    extensions.append(parquet_ext)
    
    # JSON lines reader extension with SIMD optimizations
    jsonl_compile_args = extra_compile_args.copy()
    # Add SIMD flags based on architecture
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        # x86-64: Add SSE4.2 and AVX2 flags
        jsonl_compile_args.extend(["-msse4.2", "-mavx2"])
    elif machine in ("arm64", "aarch64"):
        # ARM: NEON is enabled by default on ARMv8, but we can be explicit
        # On some ARM systems, we may need to explicitly enable NEON
        if platform.system() != "Darwin":  # macOS automatically enables NEON
            jsonl_compile_args.append("-mfpu=neon")
    
    jsonl_ext = Extension(
        "rugo.jsonl",
        sources=[
            "rugo/jsonl/jsonl_reader.pyx",
            "rugo/jsonl/decode.cpp",
            "rugo/jsonl/simdjson_wrapper.cpp",
        ],
        include_dirs=[
            "rugo/jsonl",
            "rugo/jsonl/vendor/simdjson/include",
            "rugo/jsonl/vendor/simdjson",
        ],
        language="c++",
        extra_compile_args=jsonl_compile_args,
        extra_link_args=[],
    )
    extensions.append(jsonl_ext)
    
    # CSV/TSV reader extension with SIMD optimizations
    csv_compile_args = extra_compile_args.copy()
    # Add SIMD flags based on architecture (same as JSONL)
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        # x86-64: Add SSE4.2 and AVX2 flags
        csv_compile_args.extend(["-msse4.2", "-mavx2"])
    elif machine in ("arm64", "aarch64"):
        # ARM: NEON is enabled by default on ARMv8
        if platform.system() != "Darwin":
            csv_compile_args.append("-mfpu=neon")
    
    csv_ext = Extension(
        "rugo.csv",
        sources=[
            "rugo/csv/csv_reader.pyx",
            "rugo/csv/csv_parser.cpp",
        ],
        include_dirs=[
            "rugo/csv",
        ],
        language="c++",
        extra_compile_args=csv_compile_args,
        extra_link_args=[],
    )
    extensions.append(csv_ext)
    
    return extensions


class build_ext(build_ext_orig):
    """Ensure the compiler recognizes vendored assembly sources."""

    def build_extensions(self):
        if self.compiler:
            src_exts = self.compiler.src_extensions
            if ".S" not in src_exts:
                src_exts.append(".S")
        super().build_extensions()


def main():
    # Get extensions
    extensions = get_extensions()
    
    # Cythonize extensions
    ext_modules = cythonize(
        extensions,
        compiler_directives={
            "language_level": 3,
            "boundscheck": False,
            "wraparound": False,
            "initializedcheck": False,
            "cdivision": True,
        },
        annotate=True,  # Generate HTML annotation files for debugging
    )
    
    # Setup configuration
    setup(
        ext_modules=ext_modules,
        cmdclass={"build_ext": build_ext},
        zip_safe=False,
    )

if __name__ == "__main__":
    main()
