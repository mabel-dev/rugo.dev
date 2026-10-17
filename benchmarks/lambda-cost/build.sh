#!/usr/bin/env bash
# Build one Lambda ZIP per library and architecture into ./build.
set -euo pipefail
mkdir -p build
for arch in x86_64 aarch64; do
  for lib in rugo pyarrow duckdb polars; do
    d=build/$lib-$arch
    rm -rf "$d" && mkdir -p "$d"
    pip install -q "$lib" --target "$d" \
      --platform manylinux_2_34_$arch --platform manylinux_2_28_$arch \
      --platform manylinux_2_17_$arch --platform manylinux2014_$arch \
      --python-version 3.12 --only-binary=:all: --implementation cp
    cp handlers/common.py "handlers/h_$lib.py" "$d/"
    (cd "$d" && zip -qr9 "../$lib-$arch.zip" .)
  done
done
