// Not a parser: counts newlines over the same mmap'd chunks, the same way, on the same
// threads. It is the floor for any NDJSON reader on this machine (touch every byte once),
// so every other result can be read as a fraction of it.
#include "common.hpp"

using bench::Chunk;

namespace {
struct Driver {
    explicit Driver(const bench::Config&) {}
    void run_chunk(const Chunk& c, bench::Acc& acc) {
        // A plain byte loop: -O3 -march=native vectorises it to full-width compares.
        const unsigned char* p = reinterpret_cast<const unsigned char*>(c.data);
        uint64_t n = 0;
        for (size_t i = 0; i < c.len; ++i) n += (p[i] == '\n');
        acc.docs += n;
    }
};
}  // namespace

int main(int argc, char** argv) {
    return bench::bench_main<Driver>(argc, argv, "floor-newlines", "1");
}
