// yyjson driver.
//
//   --api dom   yyjson_read_opts() per line (yyjson has no NDJSON stream API), strict
//               RFC 8259 (no flags), into an immutable DOM; fields via yyjson_obj_get.
//
// Each thread reuses one pool allocator sized with yyjson_read_max_memory_usage(), the
// approach yyjson's docs recommend for repeated reads, so no document touches malloc.
// The input is read-only mmap, so YYJSON_READ_INSITU is not used: yyjson copies each line
// into its pool (that copy is the same work INSITU would need us to do first).
#include "common.hpp"
#include "yyjson.h"

using bench::Chunk;
using bench::Row;
using bench::W;

namespace {

inline yyjson_val* path(yyjson_val* v, std::initializer_list<const char*> keys) {
    for (const char* k : keys) {
        if (!v) return nullptr;
        v = yyjson_obj_get(v, k);  // NULL for a non-object or a missing key
    }
    return v;
}

inline void str_of(yyjson_val* v, std::string_view& out, bool& has) {
    if (v && yyjson_is_str(v)) { out = std::string_view(yyjson_get_str(v), yyjson_get_len(v)); has = true; }
}

void visit(W w, yyjson_val* doc, Row& r) {
    switch (w) {
        case W::parse: return;
        case W::filter_hi: case W::filter_lo:
            str_of(path(doc, {"did"}), r.did, r.has_did);
            str_of(path(doc, {"commit", "collection"}), r.coll, r.has_coll);
            return;
        case W::minmax: {
            yyjson_val* v = path(doc, {"time_us"});
            if (v && yyjson_is_uint(v)) { r.ts = yyjson_get_uint(v); r.has_ts = true; }
            return;
        }
        case W::freq_lo: str_of(path(doc, {"commit", "collection"}), r.coll, r.has_coll); return;
        case W::freq_hi: str_of(path(doc, {"did"}), r.did, r.has_did); return;
        case W::filter_agg: {
            str_of(path(doc, {"kind"}), r.kind, r.has_kind);
            yyjson_val* commit = path(doc, {"commit"});
            str_of(path(commit, {"operation"}), r.op, r.has_op);
            str_of(path(commit, {"collection"}), r.coll, r.has_coll);
            return;
        }
        case W::deep:
            str_of(path(doc, {"commit", "record", "reply", "parent", "uri"}), r.uri, r.has_uri);
            return;
        case W::langs: {
            yyjson_val* arr = path(doc, {"commit", "record", "langs"});
            if (!arr || !yyjson_is_arr(arr)) return;
            size_t i, n;
            yyjson_val* el;
            yyjson_arr_foreach(arr, i, n, el) {
                if (yyjson_is_str(el)) r.langs.emplace_back(yyjson_get_str(el), yyjson_get_len(el));
            }
            return;
        }
    }
}

struct Driver {
    const bench::Config& cfg;
    static constexpr size_t kMaxPooled = 1 << 20;  // lines up to 1 MiB use the pool
    std::vector<char> pool_mem;
    yyjson_alc pool;
    Row row;

    explicit Driver(const bench::Config& c) : cfg(c) {
        if (c.api != "dom") { std::fprintf(stderr, "yyjson: --api dom\n"); std::exit(2); }
        pool_mem.resize(yyjson_read_max_memory_usage(kMaxPooled, YYJSON_READ_NOFLAG));
        yyjson_alc_pool_init(&pool, pool_mem.data(), pool_mem.size());
    }

    void run_chunk(const Chunk& c, bench::Acc& acc) {
        bench::for_each_line(c.data, c.len, c.cap, [&](const char* line, size_t len, size_t) {
            const yyjson_alc* alc = len <= kMaxPooled ? &pool : nullptr;
            yyjson_doc* doc = yyjson_read_opts(const_cast<char*>(line), len, YYJSON_READ_NOFLAG, alc, nullptr);
            if (!doc) { ++acc.rejected; return; }
            row.clear();
            visit(cfg.w, yyjson_doc_get_root(doc), row);
            acc.commit(row);
            yyjson_doc_free(doc);
        });
    }
};

}  // namespace

int main(int argc, char** argv) {
    return bench::bench_main<Driver>(argc, argv, "yyjson", YYJSON_VERSION_STRING);
}
