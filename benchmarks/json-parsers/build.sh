#!/usr/bin/env bash
# Fetch the pinned parser sources (versions.env) and build the C++ drivers into build/.
# Needs git and a C++20 compiler; CXX defaults to g++. Re-running rebuilds.
set -euo pipefail
cd "$(dirname "$0")"
source versions.env
CXX=${CXX:-g++}
CC=${CC:-gcc}
mkdir -p deps build

fetch() {  # repo tag dir
    if [ ! -d "deps/$3" ]; then
        git -c advice.detachedHead=false clone -q --depth 1 --branch "$2" "https://github.com/$1" "deps/$3"
    fi
}
fetch simdjson/simdjson        "$SIMDJSON_VERSION"        simdjson
fetch ibireme/yyjson           "$YYJSON_VERSION"          yyjson
fetch bytedance/sonic-cpp      "$SONIC_VERSION"           sonic
fetch martinus/unordered_dense "$UNORDERED_DENSE_VERSION" unordered_dense
# rugo: its C++ sources from opteryx-core at the release tag (sparse: sources only).
# OPTERYX_CORE_SRC=/path/to/opteryx-core builds from a local tree instead (e.g. to measure
# an unreleased change); build_info.txt records which.
if [ -z "${OPTERYX_CORE_SRC:-}" ] && [ ! -d deps/opteryx-core ]; then
    git -c advice.detachedHead=false clone -q --depth 1 --branch "$OPTERYX_CORE_REF" \
        --filter=blob:none --sparse https://github.com/mabel-dev/opteryx-core deps/opteryx-core
    git -C deps/opteryx-core sparse-checkout set rugo/src draken src/cpp src/c third_party
fi
OCORE=${OPTERYX_CORE_SRC:-deps/opteryx-core}

case "$(uname -m)" in
    x86_64) ARCH="-march=native"; SONIC_ARCH="-mavx2 -mpclmul -mbmi -mlzcnt" ;;
    *)      ARCH="-mcpu=native";  SONIC_ARCH="" ;;
esac
COMMON="-O3 -DNDEBUG $ARCH -std=c++20 -pthread -Icpp -Ideps/unordered_dense/include"
echo "CXX=$($CXX --version | head -1)"
echo "flags: $COMMON"

# simdjson: the amalgamated single-header build, as its README recommends; runtime dispatch
# picks the widest kernel the CPU supports. -pthread turns on SIMDJSON_THREADS_ENABLED; the
# driver chooses threaded / single-threaded streams at run time (--api ...-st).
$CXX $COMMON -Ideps/simdjson/singleheader \
    cpp/bench_simdjson.cpp deps/simdjson/singleheader/simdjson.cpp -o build/bench_simdjson &
# yyjson: compiled as C with the same optimisation flags, linked into the C++ driver.
$CC -O3 -DNDEBUG $ARCH -c deps/yyjson/src/yyjson.c -o build/yyjson.o
$CXX $COMMON -Ideps/yyjson/src cpp/bench_yyjson.cpp build/yyjson.o -o build/bench_yyjson &
# sonic-cpp: header-only, with the arch flags its own CMake sets (set_arch_flags.cmake).
$CXX $COMMON $SONIC_ARCH -Ideps/sonic/include \
    cpp/bench_sonic.cpp -o build/bench_sonic &
$CXX $COMMON cpp/bench_floor.cpp -o build/bench_floor &
# rugo: the JSONL reader's C++ core and its draken/simd dependencies, the same translation
# units the rugo_native extension compiles (opteryx-core build_common.py), minus the Python
# edge. Same flags as every other driver (the PyPI wheel is built -march=haswell).
RUGO_INC=""
for d in . src/cpp src/c draken draken/core draken/simd rugo/src rugo/src/jsonl/core \
         third_party/fastfloat third_party/fastfloat/fast_float third_party/cyan4973 \
         third_party/bshoshany third_party/moodycamel third_party/utf8h third_party/ulfjack/ryu \
         third_party/mabel third_party/mabel/carchar third_party/mabel/base16 third_party/mabel/base64 \
         third_party/mabel/base85 third_party/mabel/medius third_party/mabel/parvi third_party/mabel/perfect_hash; do
    RUGO_INC="$RUGO_INC -I$OCORE/$d"
done
RUGO_SRC=""
for f in rugo/src/jsonl/core/structural_scan.cpp rugo/src/jsonl/core/interpreter.cpp \
         rugo/src/jsonl/core/value_parser.cpp rugo/src/jsonl/core/field_span.cpp \
         rugo/src/jsonl/core/jsonl_reader.cpp rugo/src/jsonl/core/column_builder.cpp \
         rugo/src/declared_type.cpp draken/core/vector_alloc.cpp draken/simd/simd_env.cpp \
         draken/simd/cpu_features.cpp src/cpp/simd_search.cpp; do
    RUGO_SRC="$RUGO_SRC $OCORE/$f"
done
RUGO_VER=$(git -C "$OCORE" describe --tags --always --dirty 2>/dev/null || echo unknown)
$CXX $COMMON $RUGO_INC -DRUGO_BENCH_VERSION="\"$RUGO_VER\"" cpp/bench_rugo.cpp $RUGO_SRC -o build/bench_rugo &
wait
ls -la build/bench_*
{
    echo "cxx: $($CXX --version | head -1)"
    echo "cc: $($CC --version | head -1)"
    echo "flags: $COMMON"
    echo "sonic_flags: $SONIC_ARCH"
    for d in simdjson yyjson sonic unordered_dense; do echo "$d: $(git -C deps/$d describe --tags --always) $(git -C deps/$d rev-parse HEAD)"; done
    echo "rugo (opteryx-core): $OCORE $RUGO_VER $(git -C "$OCORE" rev-parse HEAD 2>/dev/null)"
} > build/build_info.txt
