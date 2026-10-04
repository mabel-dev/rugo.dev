// Shared harness for the C/C++ parser drivers (simdjson, yyjson, sonic-cpp).
//
// Everything that is NOT the parser lives here, so every parser gets identical I/O,
// identical scheduling and identical result accounting:
//
//   * I/O       Each file is mmap'd read-only into a reserved region with >= 4 KiB of
//               zero-filled readable memory after it, so any parser that wants padding
//               (simdjson needs 64 bytes) can read past the end without a copy. On Linux
//               each chunk is pre-faulted with MADV_POPULATE_READ (batched page-table
//               population) before it is parsed. Mapping happens inside the timed region.
//   * Schedule  Files are cut into ~32 MiB chunks at newline boundaries and handed to
//               worker threads from one shared queue, so 100 files on 32 threads never
//               leaves threads idle for a final partial "round" of files.
//   * Results   A parser fills a `Row` with the fields a workload needs; `Acc::commit`
//               does the counting, hashing and copying the same way for every parser.
//               Hash maps are ankerl::unordered_dense for all parsers.
//   * Runs      --repeat R runs the whole thing R times in one process, re-mapping the files
//               each time. Run 0 is the warm-up; the report drops it.
//
// A driver implements:  struct Driver { explicit Driver(const Config&);
//                                       void run_chunk(const Chunk&, Acc&); };
// and calls bench_main<Driver>(argc, argv, "<parser>", "<version>", "<api>").
#pragma once

#include <ankerl/unordered_dense.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <memory>
#include <string>
#include <string_view>
#include <sys/mman.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace bench {

// ------------------------------------------------------------------ workloads ---
enum class W { parse, filter_hi, filter_lo, minmax, freq_lo, freq_hi, filter_agg, deep, langs };

inline const char* wname(W w) {
    switch (w) {
        case W::parse: return "parse";
        case W::filter_hi: return "filter_hi";
        case W::filter_lo: return "filter_lo";
        case W::minmax: return "minmax";
        case W::freq_lo: return "freq_lo";
        case W::freq_hi: return "freq_hi";
        case W::filter_agg: return "filter_agg";
        case W::deep: return "deep";
        case W::langs: return "langs";
    }
    return "?";
}

inline bool parse_w(const char* s, W& w) {
    for (W c : {W::parse, W::filter_hi, W::filter_lo, W::minmax, W::freq_lo, W::freq_hi,
                W::filter_agg, W::deep, W::langs})
        if (std::strcmp(s, wname(c)) == 0) { w = c; return true; }
    return false;
}

// The filter values. filter_hi matches ~45% of Bluesky rows, filter_lo ~1.4%.
inline std::string_view filter_value(W w) {
    return w == W::filter_hi ? std::string_view("app.bsky.feed.like")
                             : std::string_view("app.bsky.graph.block");
}

// ------------------------------------------------------------------------ row ---
// What one document contributed. A field is "present" only if it exists AND has the
// expected JSON type (string / unsigned integer); anything else is NULL, as SQL's ->> and
// a typed column read would make it. String views only need to live until Acc::commit.
struct Row {
    std::string_view did, kind, op, coll, uri;
    bool has_did = false, has_kind = false, has_op = false, has_coll = false, has_uri = false;
    uint64_t ts = 0;
    bool has_ts = false;
    std::vector<std::string_view> langs;  // string elements of commit.record.langs
    void clear() {
        has_did = has_kind = has_op = has_coll = has_uri = has_ts = false;
        langs.clear();
    }
};

// ---------------------------------------------------------------------- arena ---
// Stable storage for copied strings (hash-map keys, filter output).
class Arena {
    std::vector<std::unique_ptr<char[]>> blocks_;
    char* cur_ = nullptr;
    size_t left_ = 0;
public:
    std::string_view copy(std::string_view s) {
        if (s.size() > left_) {
            size_t n = std::max<size_t>(s.size(), 1 << 20);
            blocks_.emplace_back(new char[n]);
            cur_ = blocks_.back().get();
            left_ = n;
        }
        std::memcpy(cur_, s.data(), s.size());
        std::string_view out(cur_, s.size());
        cur_ += s.size();
        left_ -= s.size();
        return out;
    }
};

using Map = ankerl::unordered_dense::map<std::string_view, uint64_t>;
// freq_hi (millions of groups) aggregates by ROW ROUTING, the way a parallel query engine
// does: while parsing, each thread copies the key and appends (key, hash) to one of kParts
// buffers chosen by the hash; after parsing, each partition is aggregated by one thread into
// one map. No per-thread maps, no merge. (--agg merge selects the simpler alternative:
// per-thread partitioned maps merged per partition afterwards; slower at high cardinality.)
constexpr int kParts = 256;
struct HKey {
    std::string_view s;
    uint64_t h;
    bool operator==(const HKey& o) const { return h == o.h && s == o.s; }
};
struct HKeyHash {
    using is_avalanching = void;
    uint64_t operator()(const HKey& k) const noexcept { return k.h; }
};
using HMap = ankerl::unordered_dense::map<HKey, uint64_t, HKeyHash>;
inline int part_of(uint64_t h) { return int(h >> 56); }
constexpr std::string_view kNullKey("\0<null>", 7);  // NULL group (cannot collide with JSON text)

// Result digest (computed after the clock stops): zlib-compatible CRC-32 of each string,
// summed mod 2^64, so the Python drivers can compute the same with zlib.crc32.
inline uint64_t crc32(std::string_view s) {
    static const auto table = [] {
        std::array<uint32_t, 256> t{};
        for (uint32_t i = 0; i < 256; ++i) {
            uint32_t c = i;
            for (int k = 0; k < 8; ++k) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            t[i] = c;
        }
        return t;
    }();
    uint32_t c = 0xFFFFFFFFu;
    for (unsigned char ch : s) c = table[(c ^ ch) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

// --------------------------------------------------------------- accumulator ---
struct Acc {
    W w;
    uint64_t docs = 0, rejected = 0;
    // filter: the matching rows' `did`, materialised as a column (bytes + offsets)
    Arena arena;
    std::vector<std::string_view> out;
    uint64_t out_nulls = 0;
    // minmax
    uint64_t mn = UINT64_MAX, mx = 0, n_ts = 0;
    // freq_lo / filter_agg / langs
    Map counts;
    // freq_hi
    bool route_mode = true;
    std::vector<std::vector<HKey>> route;  // route mode: per-partition (key, hash) buffers
    std::vector<HMap> parts;               // final per-partition maps (merge mode: per thread)
    // deep
    uint64_t n_uri = 0;

    explicit Acc(W w_, bool route_ = true) : w(w_), route_mode(route_) {
        if (w == W::freq_hi) { parts.resize(kParts); if (route_mode) route.resize(kParts); }
    }

    void bump(Map& m, std::string_view k) {
        auto it = m.find(k);
        if (it != m.end()) { ++it->second; return; }
        m.emplace(k == kNullKey ? kNullKey : arena.copy(k), 1);
    }

    void commit(const Row& r) {
        ++docs;
        switch (w) {
            case W::parse: break;
            case W::filter_hi:
            case W::filter_lo:
                if (r.has_coll && r.coll == filter_value(w)) {
                    if (r.has_did) out.push_back(arena.copy(r.did)); else ++out_nulls;
                }
                break;
            case W::minmax:
                if (r.has_ts) { mn = std::min(mn, r.ts); mx = std::max(mx, r.ts); ++n_ts; }
                break;
            case W::freq_lo:
                bump(counts, r.has_coll ? r.coll : kNullKey);
                break;
            case W::freq_hi: {
                std::string_view k = r.has_did ? r.did : kNullKey;
                uint64_t h = ankerl::unordered_dense::hash<std::string_view>{}(k);
                if (route_mode) {
                    route[part_of(h)].push_back({k == kNullKey ? kNullKey : arena.copy(k), h});
                } else {
                    HMap& m = parts[part_of(h)];
                    auto it = m.find(HKey{k, h});
                    if (it != m.end()) ++it->second;
                    else m.emplace(HKey{k == kNullKey ? kNullKey : arena.copy(k), h}, 1);
                }
                break;
            }
            case W::filter_agg:
                if (r.has_kind && r.kind == "commit" && r.has_op && r.op == "create")
                    bump(counts, r.has_coll ? r.coll : kNullKey);
                break;
            case W::deep:
                if (r.has_uri) ++n_uri;
                break;
            case W::langs:
                for (auto l : r.langs) bump(counts, l);
                break;
        }
    }
};

// ----------------------------------------------------------------------- I/O ---
struct Mapped {
    const char* data = nullptr;
    size_t size = 0, region = 0;
    void* base = nullptr;
};

constexpr size_t kTailPad = 1 << 13;  // readable zero bytes after every file (>= 4 KiB)

inline Mapped map_file(const std::string& path) {
    Mapped m;
    int fd = ::open(path.c_str(), O_RDONLY);
    if (fd < 0) { std::perror(path.c_str()); std::exit(1); }
    struct stat st;
    fstat(fd, &st);
    m.size = size_t(st.st_size);
    long pg = sysconf(_SC_PAGESIZE);
    m.region = ((m.size + kTailPad + pg - 1) / pg) * pg;
    m.base = mmap(nullptr, m.region, PROT_READ, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (m.base == MAP_FAILED) { std::perror("mmap reserve"); std::exit(1); }
    if (m.size && mmap(m.base, m.size, PROT_READ, MAP_PRIVATE | MAP_FIXED, fd, 0) == MAP_FAILED) {
        std::perror("mmap file"); std::exit(1);
    }
    ::close(fd);
    m.data = static_cast<const char*>(m.base);
    return m;
}

// A run of whole lines. data[0..len) is the work; data[0..cap) is readable (cap >= len + 4 KiB),
// so a parser may treat everything past len as padding.
struct Chunk {
    const char* data;
    size_t len, cap;
};

inline std::vector<Chunk> make_chunks(const std::vector<Mapped>& files, size_t target) {
    std::vector<Chunk> out;
    for (auto& f : files) {
        size_t pos = 0;
        const size_t readable = f.region;
        while (pos < f.size) {
            size_t end = std::min(f.size, pos + target);
            if (end < f.size) {
                const void* nl = std::memchr(f.data + end, '\n', f.size - end);
                end = nl ? size_t(static_cast<const char*>(nl) - f.data) + 1 : f.size;
            }
            out.push_back({f.data + pos, end - pos, readable - pos});
            pos = end;
        }
    }
    return out;
}

inline void populate(const Chunk& c, bool on) {
#if defined(MADV_POPULATE_READ)
    if (!on) return;
    long pg = sysconf(_SC_PAGESIZE);
    uintptr_t a = reinterpret_cast<uintptr_t>(c.data) & ~uintptr_t(pg - 1);
    uintptr_t b = reinterpret_cast<uintptr_t>(c.data + c.len);
    madvise(reinterpret_cast<void*>(a), b - a, MADV_POPULATE_READ);
#else
    (void)c; (void)on;
#endif
}

// Call fn(line, len, cap) for each non-empty line in [p, p+n); cap = readable bytes from line.
template <class F>
inline void for_each_line(const char* p, size_t n, size_t cap, F&& fn) {
    const char* end = p + n;
    while (p < end) {
        const char* nl = static_cast<const char*>(std::memchr(p, '\n', size_t(end - p)));
        const char* le = nl ? nl : end;
        size_t len = size_t(le - p);
        if (len && p[len - 1] == '\r') --len;
        if (len) fn(p, len, cap);
        size_t step = size_t(le - p) + (nl ? 1 : 0);
        p += step;
        cap -= step;
    }
}

// --------------------------------------------------------------------- config ---
struct Config {
    W w = W::parse;
    std::string api;        // driver-specific API selector (e.g. "ondemand" / "dom")
    int threads = 1;
    int repeat = 1;
    size_t chunk = 32u << 20;
    size_t batch = 1u << 20;  // simdjson stream window
    bool route = true;        // freq_hi aggregation: row routing (default) or merge
    bool populate = true;
    std::vector<std::string> files;
};

inline void usage(const char* argv0) {
    std::fprintf(stderr,
        "usage: %s --workload W --api A [--threads N] [--repeat R] [--chunk-mb M]\n"
        "          [--batch-kb K] [--no-populate] [--agg route|merge] file...\n"
        "  W: parse filter_hi filter_lo minmax freq_lo freq_hi filter_agg deep langs\n", argv0);
    std::exit(2);
}

inline Config parse_args(int argc, char** argv) {
    Config c;
    bool have_w = false;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        auto next = [&]() -> const char* { if (i + 1 >= argc) usage(argv[0]); return argv[++i]; };
        if (a == "--workload") { if (!parse_w(next(), c.w)) usage(argv[0]); have_w = true; }
        else if (a == "--api") c.api = next();
        else if (a == "--threads") c.threads = std::atoi(next());
        else if (a == "--repeat") c.repeat = std::atoi(next());
        else if (a == "--chunk-mb") c.chunk = size_t(std::atoll(next())) << 20;
        else if (a == "--batch-kb") c.batch = size_t(std::atoll(next())) << 10;
        else if (a == "--no-populate") c.populate = false;
        else if (a == "--agg") { std::string v = next(); if (v != "route" && v != "merge") usage(argv[0]); c.route = (v == "route"); }
        else if (a.rfind("--", 0) == 0) usage(argv[0]);
        else c.files.push_back(a);
    }
    if (!have_w || c.files.empty() || c.threads < 1) usage(argv[0]);
    return c;
}

// --------------------------------------------------------------------- output ---
inline void json_str(std::string& o, std::string_view s) {
    if (s == kNullKey) { o += "null"; return; }
    o += '"';
    for (unsigned char ch : s) {
        if (ch == '"' || ch == '\\') { o += '\\'; o += char(ch); }
        else if (ch < 0x20) { char b[8]; std::snprintf(b, sizeof b, "\\u%04x", ch); o += b; }
        else o += char(ch);
    }
    o += '"';
}

inline std::string groups_json(const Map& m) {
    std::vector<std::pair<std::string_view, uint64_t>> v(m.begin(), m.end());
    std::sort(v.begin(), v.end());
    std::string o = "[";
    for (size_t i = 0; i < v.size(); ++i) {
        if (i) o += ',';
        o += '[';
        json_str(o, v[i].first);
        o += ',' + std::to_string(v[i].second) + ']';
    }
    return o + "]";
}

// --------------------------------------------------------------------- driver ---
template <class Driver>
int bench_main(int argc, char** argv, const char* parser, const char* version) {
    Config cfg = parse_args(argc, argv);
    for (int rep = 0; rep < cfg.repeat; ++rep) {
        auto t0 = std::chrono::steady_clock::now();

        std::vector<Mapped> files;
        files.reserve(cfg.files.size());
        for (auto& f : cfg.files) files.push_back(map_file(f));
        std::vector<Chunk> chunks = make_chunks(files, cfg.chunk);

        std::vector<std::unique_ptr<Acc>> accs;
        for (int t = 0; t < cfg.threads; ++t) accs.emplace_back(new Acc(cfg.w, cfg.route));
        std::atomic<size_t> next{0};
        std::vector<std::thread> pool;
        for (int t = 0; t < cfg.threads; ++t) {
            pool.emplace_back([&, t]() {
                Driver d(cfg);
                Acc& acc = *accs[t];
                for (size_t i; (i = next.fetch_add(1)) < chunks.size();) {
                    populate(chunks[i], cfg.populate);
                    d.run_chunk(chunks[i], acc);
                }
            });
        }
        for (auto& th : pool) th.join();

        // ---- merge (timed): the result must exist in one place, as a query engine's would
        Acc& a0 = *accs[0];
        for (int t = 1; t < cfg.threads; ++t) {
            Acc& a = *accs[t];
            a0.docs += a.docs; a0.rejected += a.rejected;
            switch (cfg.w) {
                case W::filter_hi: case W::filter_lo:
                    a0.out.insert(a0.out.end(), a.out.begin(), a.out.end());  // views stay valid
                    a0.out_nulls += a.out_nulls;
                    break;
                case W::minmax:
                    a0.mn = std::min(a0.mn, a.mn); a0.mx = std::max(a0.mx, a.mx); a0.n_ts += a.n_ts;
                    break;
                case W::freq_lo: case W::filter_agg: case W::langs:
                    for (auto& [k, v] : a.counts) a0.counts[k] += v;  // keys live in a's arena
                    break;
                case W::deep: a0.n_uri += a.n_uri; break;
                default: break;
            }
        }
        if (cfg.w == W::freq_hi) {
            // one thread per partition at a time: route mode builds each partition's map from
            // every thread's buffer; merge mode folds threads 1..N-1 into thread 0's maps
            std::atomic<int> np{0};
            std::vector<std::thread> mp;
            for (int t = 0; t < cfg.threads; ++t) {
                mp.emplace_back([&]() {
                    for (int p; (p = np.fetch_add(1)) < kParts;) {
                        HMap& m = a0.parts[p];
                        if (cfg.route) {
                            size_t n = 0;
                            for (auto& a : accs) n += a->route[p].size();
                            m.reserve(n / 4);
                            for (auto& a : accs)
                                for (const HKey& k : a->route[p]) ++m[k];
                        } else {
                            for (int s = 1; s < cfg.threads; ++s)
                                for (auto& [k, v] : accs[s]->parts[p]) m[k] += v;
                        }
                    }
                });
            }
            for (auto& th : mp) th.join();
        }
        double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();

        // ---- untimed: digest + report
        size_t bytes = 0;
        for (auto& f : files) bytes += f.size;
        std::string res;
        switch (cfg.w) {
            case W::parse: res = "{}"; break;
            case W::filter_hi: case W::filter_lo: {
                uint64_t h = 0;
                for (auto s : a0.out) h += crc32(s);
                res = "{\"rows\":" + std::to_string(a0.out.size() + a0.out_nulls) +
                      ",\"nulls\":" + std::to_string(a0.out_nulls) + ",\"hash\":" + std::to_string(h) + "}";
                break;
            }
            case W::minmax:
                res = "{\"min\":" + std::to_string(a0.mn) + ",\"max\":" + std::to_string(a0.mx) + "}";
                break;
            case W::freq_lo: case W::filter_agg: case W::langs:
                res = "{\"groups\":" + groups_json(a0.counts) + "}";
                break;
            case W::freq_hi: {
                uint64_t g = 0, total = 0, h = 0;
                for (auto& m : a0.parts)
                    for (auto& [k, v] : m) { ++g; total += v; h += (k.s == kNullKey ? 0 : crc32(k.s)) * v; }
                res = "{\"groups\":" + std::to_string(g) + ",\"total\":" + std::to_string(total) +
                      ",\"hash\":" + std::to_string(h) + "}";
                break;
            }
            case W::deep: res = "{\"count\":" + std::to_string(a0.n_uri) + "}"; break;
        }
        std::printf("{\"parser\":\"%s\",\"version\":\"%s\",\"api\":\"%s\",\"workload\":\"%s\","
                    "\"threads\":%d,\"agg\":\"%s\",\"run\":%d,\"files\":%zu,\"bytes\":%zu,\"seconds\":%.6f,"
                    "\"docs\":%llu,\"rejected\":%llu,\"result\":%s}\n",
                    parser, version, cfg.api.c_str(), wname(cfg.w), cfg.threads,
                    cfg.w == W::freq_hi ? (cfg.route ? "route" : "merge") : "", rep, files.size(),
                    bytes, secs, (unsigned long long)a0.docs, (unsigned long long)a0.rejected,
                    res.c_str());
        std::fflush(stdout);
        accs.clear();
        for (auto& f : files) munmap(f.base, f.region);
    }
    return 0;
}

}  // namespace bench
