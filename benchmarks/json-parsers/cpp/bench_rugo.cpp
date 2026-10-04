// rugo driver: rugo's JSONL reader called from C++, the same calls read_jsonl() makes
// beneath its Python edge (rugo/src/jsonl/_jsonl_reader.pxi), minus Python:
//
//   ParseContext (projection + pushed-down predicates)
//   -> check_predicate_literals -> discover_column_names
//   -> interpret_jsonl_threaded(..., max_threads, use_prefilter = true)   [read_jsonl's default]
//   -> parse_all_columns(..., max_threads)                                -> typed columns
//
// Then the harness walks the columns into the shared accumulators, so counting is done by
// the same hash-map code as for every other parser.
//
//   --api chunked  How Opteryx drives rugo (src/cpp/engine/native_jsonl_scan_source.hpp):
//                  the input is cut into newline-aligned chunks (Opteryx: 128 MiB; here
//                  --chunk-mb, default 128) and each chunk is decoded on ONE thread
//                  (max_threads = 1), with parallelism across chunks: the same chunk queue
//                  the other C++ drivers use.
//   --api whole    One read per file with rugo's own threading (max_threads = --threads),
//                  as read_jsonl(path) does. NOTE: at opteryx-0.9.155 a buffer over 4 GiB
//                  overflows rugo's 32-bit offsets: wrong answers or an exception. Kept so
//                  the correctness check shows it.
//
// rugo projects one level of nesting (`key->>'sub'`), so `deep` and `langs` are not
// supported. Built from opteryx-core source (OPTERYX_CORE_REF in versions.env) with the same
// flags as the other drivers.
#include "common.hpp"

#include "column_builder.hpp"
#include "field_span.hpp"
#include "interpreter.hpp"
#include "parse_context.hpp"
#include "predicate_literal.hpp"
#include "alloc.h"

using bench::Row;
using bench::W;
using namespace rugo::_jsonl;

namespace {

Predicate str_eq(const char* column, std::string_view value) {
    Predicate p;
    p.column = column;
    p.op = 0;  // EQ
    p.kind = rugo::LITERAL_STRING;
    p.value = std::string(value);
    return p;
}

inline bool valid(const ParsedColumn& c, size_t i) {
    return !c.validity || ((c.validity[i >> 3] >> (i & 7)) & 1u);
}

inline std::string_view str_at(const ParsedColumn& c, size_t i) {
    const DrakenStringSlot& s = c.slots[c.codes ? c.codes[i] : i];
    const uint32_t len = s.inl.length;
    if (len <= STR_INLINE_MAX) return {reinterpret_cast<const char*>(s.inl.data), len};
    return {reinterpret_cast<const char*>(c.arena + s.ext.arena_offset), len};
}

void free_column(ParsedColumn& c) {
    for (void* p : {static_cast<void*>(c.validity), c.data, static_cast<void*>(c.slots),
                    static_cast<void*>(c.arena), static_cast<void*>(c.codes),
                    static_cast<void*>(c.array_parent_offsets),
                    static_cast<void*>(c.array_child_validity),
                    static_cast<void*>(c.array_child_slots)})
        if (p) draken_free(p);
    c = ParsedColumn{};
}

struct Reader {
    const bench::Config& cfg;
    ParseContext ctx;
    std::vector<ParsedColumn> cols;
    size_t nrows = 0;
    long long ndocs = 0;
    uint64_t nbad = 0;

    explicit Reader(const bench::Config& c) : cfg(c) {
        ctx.fail_on_error = false;  // skip malformed lines, as every driver does
        const char* coll = "commit->>'collection'";
        switch (c.w) {
            case W::parse: break;  // every column
            case W::filter_hi: case W::filter_lo:
                ctx.projected_columns = {"did"};
                ctx.predicates.push_back(str_eq(coll, bench::filter_value(c.w)));
                break;
            case W::minmax: ctx.projected_columns = {"time_us"}; break;
            case W::freq_lo: ctx.projected_columns = {coll}; break;
            case W::freq_hi: ctx.projected_columns = {"did"}; break;
            case W::filter_agg:
                ctx.projected_columns = {coll};
                ctx.predicates.push_back(str_eq("kind", "commit"));
                ctx.predicates.push_back(str_eq("commit->>'operation'", "create"));
                break;
            case W::deep: case W::langs:
                std::fprintf(stderr, "rugo: %s needs more than one level of nesting\n", bench::wname(c.w));
                std::exit(2);
        }
    }

    void load(const char* data, size_t size, size_t threads) {
        const uint8_t* buf = reinterpret_cast<const uint8_t*>(data);
        if (!ctx.predicates.empty()) check_predicate_literals(buf, size, ctx);
        std::vector<std::string> names = discover_column_names(buf, size, ctx);
        InterpreterResult ir = interpret_jsonl_threaded(buf, size, ctx, names, threads, true);
        nbad = ir.all_records.malformed_count;
        nrows = ir.all_records.num_records() ? ir.num_records_passed : 0;
        ndocs = ctx.predicates.empty() ? static_cast<long long>(nrows) : -1;
        cols.clear();
        if (nrows) {
            const bool may_esc = std::memchr(buf, '\\', size) != nullptr;  // as read_jsonl does
            cols = parse_all_columns(buf, ir.all_records, names, threads, may_esc, ctx);
        }
    }
    size_t rows() const { return nrows; }
    long long docs() const { return ndocs; }
    uint64_t rejected() const { return nbad; }

    void emit(size_t b, size_t e, bench::Acc& acc) const {
        Row r;
        switch (cfg.w) {
            case W::parse:
                for (size_t i = b; i < e; ++i) { r.clear(); acc.commit(r); }
                return;
            case W::filter_hi: case W::filter_lo: {
                const ParsedColumn& did = cols[0];
                for (size_t i = b; i < e; ++i) {
                    r.clear();
                    r.coll = bench::filter_value(cfg.w); r.has_coll = true;  // the predicate held
                    if (valid(did, i) && did.is_string) { r.did = str_at(did, i); r.has_did = true; }
                    acc.commit(r);
                }
                return;
            }
            case W::minmax: {
                const ParsedColumn& c = cols[0];
                if (c.type != DRAKEN_INT64) { std::fprintf(stderr, "rugo: time_us not INT64\n"); std::exit(1); }
                const int64_t* v = static_cast<const int64_t*>(c.data);
                for (size_t i = b; i < e; ++i) {
                    r.clear();
                    if (valid(c, i) && v[i] >= 0) { r.ts = uint64_t(v[i]); r.has_ts = true; }
                    acc.commit(r);
                }
                return;
            }
            case W::freq_lo: case W::filter_agg: {
                const ParsedColumn& c = cols[0];
                for (size_t i = b; i < e; ++i) {
                    r.clear();
                    if (cfg.w == W::filter_agg) { r.kind = "commit"; r.has_kind = true; r.op = "create"; r.has_op = true; }
                    if (valid(c, i) && c.is_string) { r.coll = str_at(c, i); r.has_coll = true; }
                    acc.commit(r);
                }
                return;
            }
            case W::freq_hi: {
                const ParsedColumn& c = cols[0];
                for (size_t i = b; i < e; ++i) {
                    r.clear();
                    if (valid(c, i) && c.is_string) { r.did = str_at(c, i); r.has_did = true; }
                    acc.commit(r);
                }
                return;
            }
            default: return;
        }
    }

    void release() {
        for (auto& c : cols) free_column(c);
        cols.clear();
    }
};

// --api whole: rugo reads each whole file with its own threads; the harness then walks the
// columns with its threads.
struct WholeDriver : Reader {
    static constexpr bool kWholeFile = true;
    explicit WholeDriver(const bench::Config& c) : Reader(c) {}
    void load(const char* data, size_t size) { Reader::load(data, size, size_t(cfg.threads)); }
};

// --api chunked: one chunk per call, decoded on this worker thread alone.
struct ChunkDriver : Reader {
    explicit ChunkDriver(const bench::Config& c) : Reader(c) {}
    void run_chunk(const bench::Chunk& c, bench::Acc& acc) {
        Reader::load(c.data, c.len, 1);
        acc.rejected += nbad;
        if (ndocs < 0) acc.docs_unknown = true;
        emit(0, nrows, acc);
        release();
    }
};

}  // namespace

#ifndef RUGO_BENCH_VERSION
#define RUGO_BENCH_VERSION "unknown"
#endif

int main(int argc, char** argv) {
    const char* api = "";
    for (int i = 1; i + 1 < argc; ++i) if (std::strcmp(argv[i], "--api") == 0) api = argv[i + 1];
    if (std::strcmp(api, "whole") == 0) return bench::bench_main<WholeDriver>(argc, argv, "rugo", RUGO_BENCH_VERSION);
    if (std::strcmp(api, "chunked") == 0) return bench::bench_main<ChunkDriver>(argc, argv, "rugo", RUGO_BENCH_VERSION);
    std::fprintf(stderr, "rugo: --api chunked|whole\n");
    return 2;
}
