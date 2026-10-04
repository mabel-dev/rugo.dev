// sonic-cpp driver.
//
//   --api dom        Document::Parse() per line (sonic has no NDJSON stream API) into a DOM,
//                    one Document per thread reused across lines; fields via
//                    AtPointer("a", "b"), which sonic documents as its fast path for
//                    literal keys. The Document's MemoryPoolAllocator is built on an 8 MiB
//                    per-thread buffer and Clear()ed before each line: Parse() does not
//                    reset the pool itself, so without this a reused Document grows a new
//                    chunk per line (and Clear() alone frees chunks back to malloc, which
//                    contends across threads). With the buffer, a line never calls malloc
//                    for the copy or the nodes.
//   --api ondemand   sonic_json::GetOnDemand(line, JsonPointer, &raw) per field: sonic's
//                    selective API. It skips to the target without building a DOM and
//                    returns the target's raw JSON text. Strings are taken between the
//                    quotes and decoded (via a small Parse) only if they contain a backslash.
//                    Each GetOnDemand call is a separate scan from the start of the line.
//
// Built with sonic's own x86 flags (-mavx2 -mpclmul -mbmi -mlzcnt) plus -march=native.
#include "common.hpp"
#include "sonic/sonic.h"

#include <charconv>

using bench::Chunk;
using bench::Row;
using bench::W;

namespace {

using Node = sonic_json::Document::NodeType;

inline void str_of(const Node* v, std::string_view& out, bool& has) {
    if (v && v->IsString()) { auto s = v->GetStringView(); out = std::string_view(s.data(), s.size()); has = true; }
}

void visit_dom(W w, sonic_json::Document& d, Row& r) {
    switch (w) {
        case W::parse: return;
        case W::filter_hi: case W::filter_lo:
            str_of(d.AtPointer("did"), r.did, r.has_did);
            str_of(d.AtPointer("commit", "collection"), r.coll, r.has_coll);
            return;
        case W::minmax: {
            const Node* v = d.AtPointer("time_us");
            if (v && v->IsUint64()) { r.ts = v->GetUint64(); r.has_ts = true; }
            return;
        }
        case W::freq_lo: str_of(d.AtPointer("commit", "collection"), r.coll, r.has_coll); return;
        case W::freq_hi: str_of(d.AtPointer("did"), r.did, r.has_did); return;
        case W::filter_agg: {
            str_of(d.AtPointer("kind"), r.kind, r.has_kind);
            const Node* commit = d.AtPointer("commit");
            if (commit) {
                str_of(commit->AtPointer("operation"), r.op, r.has_op);
                str_of(commit->AtPointer("collection"), r.coll, r.has_coll);
            }
            return;
        }
        case W::deep:
            str_of(d.AtPointer("commit", "record", "reply", "parent", "uri"), r.uri, r.has_uri);
            return;
        case W::langs: {
            const Node* arr = d.AtPointer("commit", "record", "langs");
            if (!arr || !arr->IsArray()) return;
            for (auto it = arr->Begin(); it != arr->End(); ++it)
                if (it->IsString()) { auto s = it->GetStringView(); r.langs.emplace_back(s.data(), s.size()); }
            return;
        }
    }
}

struct Driver {
    const bench::Config& cfg;
    bool od;
    std::vector<char> pool_mem = std::vector<char>(8u << 20);
    sonic_json::MemoryPoolAllocator<> pool{pool_mem.data(), pool_mem.size()};
    sonic_json::Document doc{&pool}, scratch;
    std::string dec[3];  // decoded strings when a raw value has escapes (one per field slot)
    sonic_json::JsonPointer p_did{"did"}, p_ts{"time_us"}, p_kind{"kind"},
        p_op{"commit", "operation"}, p_coll{"commit", "collection"},
        p_uri{"commit", "record", "reply", "parent", "uri"}, p_langs{"commit", "record", "langs"};
    Row row;

    explicit Driver(const bench::Config& c) : cfg(c), od(c.api == "ondemand") {
        if (c.api != "ondemand" && c.api != "dom") {
            std::fprintf(stderr, "sonic: --api ondemand|dom\n"); std::exit(2);
        }
        if (od && c.w == W::parse) { std::fprintf(stderr, "sonic: parse workload is DOM only\n"); std::exit(2); }
    }

    // Raw value -> string field. false = the document is malformed at this value.
    bool raw_str(sonic_json::StringView line, const sonic_json::JsonPointer& p, int slot,
                 std::string_view& out, bool& has) {
        sonic_json::StringView raw;
        auto res = sonic_json::GetOnDemand(line, p, raw);
        if (res.Error() != sonic_json::kErrorNone) {
            // a missing key / type mismatch on the path is NULL; anything else is malformed
            auto e = res.Error();
            return e == sonic_json::kParseErrorUnknownObjKey || e == sonic_json::kParseErrorMismatchType ||
                   e == sonic_json::kParseErrorArrIndexOutOfRange;
        }
        if (raw.size() < 2 || raw[0] != '"') return true;  // not a string: NULL
        std::string_view body(raw.data() + 1, raw.size() - 2);
        if (body.find('\\') == std::string_view::npos) { out = body; has = true; return true; }
        scratch.Parse(raw.data(), raw.size());
        if (scratch.HasParseError() || !scratch.IsString()) return false;
        auto s = scratch.GetStringView();
        dec[slot].assign(s.data(), s.size());
        out = dec[slot];
        has = true;
        return true;
    }

    bool visit_od(sonic_json::StringView line, Row& r) {
        switch (cfg.w) {
            case W::parse: return false;
            case W::filter_hi: case W::filter_lo:
                // collection first: the did is only needed on a match
                if (!raw_str(line, p_coll, 0, r.coll, r.has_coll)) return false;
                if (r.has_coll && r.coll == bench::filter_value(cfg.w))
                    return raw_str(line, p_did, 1, r.did, r.has_did);
                return true;
            case W::minmax: {
                sonic_json::StringView raw;
                auto res = sonic_json::GetOnDemand(line, p_ts, raw);
                if (res.Error() != sonic_json::kErrorNone)
                    return res.Error() == sonic_json::kParseErrorUnknownObjKey;
                auto [ptr, ec] = std::from_chars(raw.data(), raw.data() + raw.size(), r.ts);
                r.has_ts = (ec == std::errc() && ptr == raw.data() + raw.size());
                return true;
            }
            case W::freq_lo: return raw_str(line, p_coll, 0, r.coll, r.has_coll);
            case W::freq_hi: return raw_str(line, p_did, 0, r.did, r.has_did);
            case W::filter_agg:
                if (!raw_str(line, p_kind, 0, r.kind, r.has_kind)) return false;
                if (!(r.has_kind && r.kind == "commit")) return true;
                if (!raw_str(line, p_op, 1, r.op, r.has_op)) return false;
                if (!(r.has_op && r.op == "create")) return true;
                return raw_str(line, p_coll, 2, r.coll, r.has_coll);
            case W::deep: return raw_str(line, p_uri, 0, r.uri, r.has_uri);
            case W::langs: {
                sonic_json::StringView raw;
                auto res = sonic_json::GetOnDemand(line, p_langs, raw);
                if (res.Error() != sonic_json::kErrorNone)
                    return res.Error() == sonic_json::kParseErrorUnknownObjKey ||
                           res.Error() == sonic_json::kParseErrorMismatchType;
                if (raw.size() == 0 || raw[0] != '[') return true;
                scratch.Parse(raw.data(), raw.size());  // small: just the array
                if (scratch.HasParseError()) return false;
                for (auto it = scratch.Begin(); it != scratch.End(); ++it)
                    if (it->IsString()) { auto s = it->GetStringView(); r.langs.emplace_back(s.data(), s.size()); }
                return true;
            }
        }
        return true;
    }

    void run_chunk(const Chunk& c, bench::Acc& acc) {
        bench::for_each_line(c.data, c.len, c.cap, [&](const char* line, size_t len, size_t) {
            row.clear();
            if (od) {
                if (visit_od(sonic_json::StringView(line, len), row)) acc.commit(row); else ++acc.rejected;
                return;
            }
            pool.Clear();  // keeps the 8 MiB user buffer, drops any overflow chunks
            doc.Parse(line, len);
            if (doc.HasParseError()) { ++acc.rejected; return; }
            visit_dom(cfg.w, doc, row);
            acc.commit(row);
        });
    }
};

}  // namespace

int main(int argc, char** argv) {
#define BENCH_S_(x) #x
#define BENCH_S(x) BENCH_S_(x)
    return bench::bench_main<Driver>(argc, argv, "sonic-cpp",
        BENCH_S(SONIC_MAJOR_VERSION) "." BENCH_S(SONIC_MINOR_VERSION) "." BENCH_S(SONIC_PATCH_VERSION));
}
