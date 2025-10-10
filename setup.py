#!/usr/bin/env python3
"""
Setup script for rugo - A Cython-based file decoders library
"""

from Cython.Build import cythonize
from setuptools import Extension
from setuptools import setup


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
            "rugo/parquet/compression.cpp",  # NEW: compression support
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
        extra_compile_args=["-O3", "-std=c++17"],
        extra_link_args=[],
    )
    extensions.append(parquet_ext)
    
    return extensions


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
        zip_safe=False,
    )

if __name__ == "__main__":
    main()
