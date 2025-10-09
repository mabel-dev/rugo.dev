#!/usr/bin/env python3
"""
Setup script for rugo - A Cython-based file decoders library
"""

from Cython.Build import cythonize
from setuptools import Extension
from setuptools import setup


def get_extensions():
    """Define the Cython extensions to build"""
    extensions = []
    
    # Parquet decoder extension
    parquet_ext = Extension(
        "rugo.parquet",
        sources=[
            "rugo/parquet/metadata_reader.pyx",
            "rugo/parquet/metadata.cpp",
            "rugo/parquet/bloom_filter.cpp",
        ],
        include_dirs=[],
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
