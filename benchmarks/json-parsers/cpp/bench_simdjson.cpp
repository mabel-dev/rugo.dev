// simdjson driver.
//
//   --api ondemand   ondemand::parser::iterate_many(..., stream_format::newline_delimited):
//                    the NDJSON fast path (v5+), which lets the stream jump to the next line
//                    instead of walking the unread rest of a document. Fields are read in
//                    document order with operator[] (find_field_unordered), as the
//                    simdjson docs recommend.
//   --api dom        dom::parser::parse_many: every document fully parsed and validated.
//
// Both use one parser per thread, reused across chunks, with the default 1 MB batch.
// simdjson's streams run stage 1 of the next batch on a helper thread by default
// (parser.threaded = true). At 32 workers that is 64 busy threads on 32 vCPUs, so the
// "-st" variants (ondemand-st, dom-st) set parser.threaded = false; both are measured.
//
// Malformed input: a stream stops at its first error. We then re-parse that region one line
// at a time (a single-document parse per line, same API), count the bad lines as rejected,
// and restart the stream after it, so every valid document in the file is still read.
#include "common.hpp"
#include "simdjson.h"

using namespace simdjson;
using bench::Chunk;
using bench::Row;
using bench::W;

namespace {

// --- field helpers: missing (NO_SUCH_FIELD) or wrong type (INCORRECT_TYPE) is NULL, not an
//     error; anything else means the document is broken.
inline bool soft(error_code e) { return e == NO_SUCH_FIELD || e == INCORRECT_TYPE; }

template <class V>
inline error_code str_of(V&& v, std::string_view& out, bool& has) {
    error_code e = std::forward<V>(v).get_string().get(out);
    if (!e) { has = true; return SUCCESS; }
    return soft(e) ? SUCCESS : e;
}

template <class V>
inline error_code u64_of(V&& v, uint64_t& out, bool& has) {
    error_code e = std::forward<V>(v).get_uint64().get(out);
    if (!e) { has = true; return SUCCESS; }
    return soft(e) ? SUCCESS : e;
}

#define TRY(x) do { error_code _e = (x); if (_e) return _e; } while (0)

// ---------------------------------------------------------------- On-Demand ---
// Field order in the Bluesky documents is did, time_us, kind, commit{rev, operation,
// collection, rkey, record{...}, cid}; reads below follow that order.
template <class Doc>
error_code visit_od(W w, Doc& doc, Row& r) {
    switch (w) {
        case W::parse: return UNSUPPORTED_ARCHITECTURE;  // not offered: On-Demand parses lazily
        case W::filter_hi: case W::filter_lo:
            TRY(str_of(doc["did"], r.did, r.has_did));
            TRY(str_of(doc["commit"]["collection"], r.coll, r.has_coll));
            return SUCCESS;
        case W::minmax:
            return u64_of(doc["time_us"], r.ts, r.has_ts);
        case W::freq_lo:
            return str_of(doc["commit"]["collection"], r.coll, r.has_coll);
        case W::freq_hi:
            return str_of(doc["did"], r.did, r.has_did);
        case W::filter_agg: {
            TRY(str_of(doc["kind"], r.kind, r.has_kind));
            auto commit = doc["commit"];
            TRY(str_of(commit["operation"], r.op, r.has_op));
            TRY(str_of(commit["collection"], r.coll, r.has_coll));
            return SUCCESS;
        }
        case W::deep:
            return str_of(doc["commit"]["record"]["reply"]["parent"]["uri"], r.uri, r.has_uri);
        case W::langs: {
            ondemand::array arr;
            error_code e = doc["commit"]["record"]["langs"].get_array().get(arr);
            if (e) return soft(e) ? SUCCESS : e;
            for (auto el : arr) {
                std::string_view s;
                error_code ee = el.get_string().get(s);
                if (!ee) r.langs.push_back(s);
                else if (!soft(ee)) return ee;
            }
            return SUCCESS;
        }
    }
    return SUCCESS;
}

// ---------------------------------------------------------------------- DOM ---
error_code visit_dom(W w, dom::element doc, Row& r) {
    switch (w) {
        case W::parse: return SUCCESS;
        case W::filter_hi: case W::filter_lo:
            TRY(str_of(doc["did"], r.did, r.has_did));
            return str_of(doc["commit"]["collection"], r.coll, r.has_coll);
        case W::minmax: return u64_of(doc["time_us"], r.ts, r.has_ts);
        case W::freq_lo: return str_of(doc["commit"]["collection"], r.coll, r.has_coll);
        case W::freq_hi: return str_of(doc["did"], r.did, r.has_did);
        case W::filter_agg: {
            TRY(str_of(doc["kind"], r.kind, r.has_kind));
            auto commit = doc["commit"];
            TRY(str_of(commit["operation"], r.op, r.has_op));
            return str_of(commit["collection"], r.coll, r.has_coll);
        }
        case W::deep:
            return str_of(doc["commit"]["record"]["reply"]["parent"]["uri"], r.uri, r.has_uri);
        case W::langs: {
            dom::array arr;
            error_code e = doc["commit"]["record"]["langs"].get_array().get(arr);
            if (e) return soft(e) ? SUCCESS : e;
            for (dom::element el : arr) {
                std::string_view s;
                if (!el.get_string().get(s)) r.langs.push_back(s);
            }
            return SUCCESS;
        }
    }
    return SUCCESS;
}

struct Driver {
    const bench::Config& cfg;
    bool od;
    ondemand::parser oparser, oline;
    dom::parser dparser, dline;
    Row row;

    explicit Driver(const bench::Config& c) : cfg(c), od(c.api.rfind("ondemand", 0) == 0) {
        if (c.api != "ondemand" && c.api != "dom" && c.api != "ondemand-st" && c.api != "dom-st") {
            std::fprintf(stderr, "simdjson: --api ondemand|ondemand-st|dom|dom-st\n"); std::exit(2);
        }
        const bool threaded = c.api.size() < 3 || c.api.compare(c.api.size() - 3, 3, "-st") != 0;
        oparser.threaded = threaded;
        dparser.threaded = threaded;
        if (od && c.w == W::parse) {
            std::fprintf(stderr, "simdjson: parse workload is DOM only\n"); std::exit(2);
        }
    }

    // One document per line, for the region after a stream error.
    void recover_lines(const char* p, size_t n, size_t cap, bench::Acc& acc) {
        bench::for_each_line(p, n, cap, [&](const char* line, size_t len, size_t lcap) {
            row.clear();
            error_code e;
            if (od) {
                ondemand::document doc;
                e = oline.iterate(padded_string_view(line, len, lcap)).get(doc);
                if (!e) e = visit_od(cfg.w, doc, row);
            } else {
                dom::element doc;
                e = dline.parse(line, len, false).get(doc);
                if (!e) e = visit_dom(cfg.w, doc, row);
            }
            if (e) ++acc.rejected; else acc.commit(row);
        });
    }

    // Region of one batch, rounded to a line end, starting at p.
    static size_t window(const char* p, size_t left, size_t batch) {
        if (left <= batch) return left;
        const void* nl = std::memchr(p + batch, '\n', left - batch);
        return nl ? size_t(static_cast<const char*>(nl) - p) + 1 : left;
    }

    void run_chunk(const Chunk& c, bench::Acc& acc) {
        size_t pos = 0;
        while (pos < c.len) {
            const char* p = c.data + pos;
            const size_t left = c.len - pos;
            size_t resume = left;     // where the stream ended, relative to p
            bool failed = false;
            size_t last_ok = SIZE_MAX;  // current_index() of the last good document
            if (od) {
                ondemand::document_stream stream;
                if (oparser.iterate_many(p, left, cfg.batch, stream_format::newline_delimited).get(stream)) {
                    failed = true;
                } else {
                    for (auto it = stream.begin(); it != stream.end(); ++it) {
                        ondemand::document_reference doc;
                        row.clear();
                        error_code e = (*it).get(doc);
                        if (!e) e = visit_od(cfg.w, doc, row);
                        if (e) { failed = true; break; }
                        last_ok = it.current_index();
                        acc.commit(row);
                    }
                }
            } else {
                dom::document_stream stream;
                if (dparser.parse_many(reinterpret_cast<const uint8_t*>(p), left, cfg.batch).get(stream)) {
                    failed = true;
                } else {
                    for (auto it = stream.begin(); it != stream.end(); ++it) {
                        dom::element doc;
                        row.clear();
                        error_code e = (*it).get(doc);
                        if (!e) e = visit_dom(cfg.w, doc, row);
                        if (e) { failed = true; break; }
                        last_ok = it.current_index();
                        acc.commit(row);
                    }
                }
            }
            if (!failed) { pos += resume; continue; }
            // Stream stopped on an error. Restart after the last good document's line,
            // re-read the next batch line by line, then hand the rest back to a new stream.
            size_t start = 0;
            if (last_ok != SIZE_MAX) {
                const void* nl = std::memchr(p + last_ok, '\n', left - last_ok);
                start = nl ? size_t(static_cast<const char*>(nl) - p) + 1 : left;
            }
            size_t w = window(p + start, left - start, cfg.batch);
            recover_lines(p + start, w, c.cap - pos - start, acc);
            pos += start + w;
        }
    }
};

}  // namespace

int main(int argc, char** argv) {
#ifndef SIMDJSON_THREADS_ENABLED
#error "build with -pthread: the threaded stream variants need SIMDJSON_THREADS_ENABLED"
#endif
    std::fprintf(stderr, "simdjson %s, implementation %s\n", SIMDJSON_VERSION,
                 get_active_implementation()->name().c_str());
    return bench::bench_main<Driver>(argc, argv, "simdjson", SIMDJSON_VERSION);
}
