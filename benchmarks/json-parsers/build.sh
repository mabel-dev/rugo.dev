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
wait
ls -la build/bench_*
{
    echo "cxx: $($CXX --version | head -1)"
    echo "cc: $($CC --version | head -1)"
    echo "flags: $COMMON"
    echo "sonic_flags: $SONIC_ARCH"
    for d in simdjson yyjson sonic unordered_dense; do echo "$d: $(git -C deps/$d describe --tags --always) $(git -C deps/$d rev-parse HEAD)"; done
} > build/build_info.txt
