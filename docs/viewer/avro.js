// Avro object-container reader for the viewer. The header (magic, metadata map,
// sync marker) holds the schema and codec; the rest is a run of blocks
//   { long count | long byteSize | payload | 16-byte sync }
// A windowed scan walks block headers to count rows and check sync markers
// without holding the file in memory. Records of one block can be decoded for
// preview (null, deflate and snappy codecs).
import { ViewerError } from "./errors.js";
import { readVarint, unzigzag, ProtoError } from "./proto.js";
import { inflateRaw, snappyDecompress, crc32 } from "./codecs.js";
import { fmtBytes, fmtInt, fmtDays, fmtTimestampMs, displayValue } from "./viewer-core.js";

const FORMAT = "avro";
const MAGIC = [0x4f, 0x62, 0x6a, 0x01]; // "Obj\x01"
const WINDOW = 4 * 1024 * 1024;
const MAX_STORED_BLOCKS = 200_000;
const AUTO_SCAN_BYTES = 8 * 1024 * 1024; // a remote file this small is cheap to scan without asking
const READABLE_CODECS = ["null", "deflate", "snappy"];
const bad = (code, msg, detail) => new ViewerError(code, msg, detail, FORMAT);

class Eof extends Error {}

// ---- low-level reader --------------------------------------------------------------

class Reader {
  constructor(buf, pos = 0) { this.buf = buf; this.pos = pos; }
  long() {
    try {
      const [v, p] = readVarint(this.buf, this.pos);
      this.pos = p;
      return unzigzag(v);
    } catch (e) { if (e instanceof ProtoError) throw new Eof("eof"); throw e; }
  }
  int() { return Number(this.long()); }
  bytes(n) {
    if (typeof n !== "number" || n < 0 || this.pos + n > this.buf.length) throw new Eof("eof");
    const out = this.buf.subarray(this.pos, this.pos + n);
    this.pos += n;
    return out;
  }
  string() { return new TextDecoder("utf-8", { fatal: false }).decode(this.bytes(this.int())); }
  f32() { const b = this.bytes(4); return new DataView(b.buffer, b.byteOffset, 4).getFloat32(0, true); }
  f64() { const b = this.bytes(8); return new DataView(b.buffer, b.byteOffset, 8).getFloat64(0, true); }
}

function parseHeader(buf) {
  if (buf.length < 4 || !MAGIC.every((b, i) => buf[i] === b)) throw bad("UNKNOWN_FORMAT", "This file doesn't start with the Avro magic bytes (Obj\\x01).");
  const r = new Reader(buf, 4);
  const meta = new Map();
  for (;;) {
    let count = r.long();
    if (typeof count === "bigint") throw bad("CORRUPT", "This Avro file's metadata map has an implausible size.");
    if (count < 0) { count = -count; r.long(); }
    if (count === 0) break;
    for (let i = 0; i < count; i++) { const k = r.string(); const v = r.bytes(r.int()); meta.set(k, v); }
    if (meta.size > 100000) throw bad("CORRUPT", "This Avro file's metadata map is implausibly large.");
  }
  const sync = r.bytes(16).slice();
  return { meta, sync, firstBlock: r.pos };
}

async function readHeader(source) {
  let want = 64 * 1024;
  for (;;) {
    const n = Math.min(want, source.size);
    const buf = await source.read(0, n);
    try { return parseHeader(buf); } catch (e) {
      if (!(e instanceof Eof)) throw e;
      if (n >= source.size || want >= 64 * 1024 * 1024) throw bad("TRUNCATED", "This file starts like an Avro file, but its header is cut off before the schema ends.", "header");
      want *= 8;
    }
  }
}

// ---- schema --------------------------------------------------------------------------

const PRIMS = new Set(["null", "boolean", "int", "long", "float", "double", "bytes", "string"]);
const schemaErr = (msg) => bad("CORRUPT", `This Avro file's schema isn't valid: ${msg}.`, msg);

function parseSchema(json) {
  const names = new Map();
  const qualify = (name, ns) => (name.includes(".") || !ns ? name : `${ns}.${name}`);
  const build = (s, ns) => {
    if (typeof s === "string") {
      if (PRIMS.has(s)) return { t: s };
      const ref = names.get(qualify(s, ns)) ?? names.get(s);
      if (!ref) throw schemaErr(`unknown type "${s}"`);
      return ref;
    }
    if (Array.isArray(s)) return { t: "union", branches: s.map((x) => build(x, ns)) };
    if (!s || typeof s !== "object") throw schemaErr("a type must be a string, array or object");
    const type = s.type;
    if (typeof type === "object" || Array.isArray(type)) return build(type, ns);
    const named = (extra) => {
      if (typeof s.name !== "string" || !s.name) throw schemaErr(`a ${type} needs a name`);
      const full = qualify(s.name, s.namespace ?? ns);
      const node = { t: type, name: full.split(".").pop(), full, ...extra };
      names.set(full, node);
      return [node, full.includes(".") ? full.slice(0, full.lastIndexOf(".")) : ""];
    };
    switch (type) {
      case "record": case "error": {
        const [node, childNs] = named({ t: "record", fields: [] });
        if (!Array.isArray(s.fields)) throw schemaErr(`record ${node.full} has no fields array`);
        for (const f of s.fields) {
          if (!f || typeof f.name !== "string") throw schemaErr(`a field of ${node.full} has no name`);
          node.fields.push({ name: f.name, type: build(f.type, childNs), hasDefault: "default" in f });
        }
        return node;
      }
      case "enum": {
        if (!Array.isArray(s.symbols)) throw schemaErr("an enum needs a symbols array");
        return named({ symbols: s.symbols })[0];
      }
      case "fixed": {
        if (!Number.isInteger(s.size) || s.size < 0) throw schemaErr("a fixed needs an integer size");
        const [node] = named({ size: s.size });
        if (s.logicalType) { node.logical = s.logicalType; node.precision = s.precision; node.scale = s.scale ?? 0; }
        return node;
      }
      case "array": return { t: "array", items: build(s.items, ns) };
      case "map": return { t: "map", values: build(s.values, ns) };
      default:
        if (PRIMS.has(type)) {
          const n = { t: type };
          if (s.logicalType) { n.logical = s.logicalType; n.precision = s.precision; n.scale = s.scale ?? 0; }
          return n;
        }
        throw schemaErr(`unknown type "${String(type)}"`);
    }
  };
  return build(json, "");
}

function typeString(n) {
  switch (n.t) {
    case "record": return `record ${n.name}`;
    case "enum": return `enum ${n.name}(${n.symbols.slice(0, 6).join(", ")}${n.symbols.length > 6 ? ", …" : ""})`;
    case "fixed": return n.logical === "decimal" ? `decimal(${n.precision},${n.scale})` : `fixed(${n.size})`;
    case "array": return `array<${typeString(n.items)}>`;
    case "map": return `map<string, ${typeString(n.values)}>`;
    case "union": return n.branches.map(typeString).join(" | ");
    default:
      if (n.logical === "decimal") return `decimal(${n.precision},${n.scale})`;
      return n.logical ? `${n.t} (${n.logical})` : n.t;
  }
}

const hasNull = (t) => t.t === "union" && t.branches.some((b) => b.t === "null");
const isComplex = (n) => n.t === "record" || n.t === "array" || n.t === "map" || (n.t === "union" && n.branches.filter((b) => b.t !== "null").length > 1);

function treeNode(name, tn, nullable, path) {
  if (tn.t === "union") {
    const nonNull = tn.branches.filter((b) => b.t !== "null");
    if (nonNull.length === 1) return treeNode(name, nonNull[0], tn.branches.length > 1, path);
    return { name, path: name, kind: "union", type: typeString(tn), physical: "union", nullable: tn.branches.some((b) => b.t === "null"), children: nonNull.map((b) => treeNode(typeString(b), b, false, path)) };
  }
  const n = { name, path: name, kind: "leaf", type: typeString(tn), physical: tn.t, nullable, children: [] };
  if (tn.t === "record") {
    if (path.includes(tn)) { n.type = `→ ${tn.full}`; return n; } // recursive reference
    n.kind = "struct";
    n.children = tn.fields.map((f) => treeNode(f.name, f.type, hasNull(f.type), [...path, tn]));
  } else if (tn.t === "array") {
    n.kind = "list";
    if (isComplex(tn.items)) n.children = [treeNode("item", tn.items, false, path)];
  } else if (tn.t === "map") {
    n.kind = "map";
    if (isComplex(tn.values)) n.children = [treeNode("value", tn.values, false, path)];
  }
  return n;
}

// ---- record decoding -------------------------------------------------------------------

const pad = (n, w) => String(n).padStart(w, "0");
function clock(ms) {
  const t = Math.floor(ms);
  return `${pad(Math.floor(t / 3600000) % 24, 2)}:${pad(Math.floor(t / 60000) % 60, 2)}:${pad(Math.floor(t / 1000) % 60, 2)}.${pad(t % 1000, 3)}`;
}
function decimalText(bytes, scale) {
  if (!bytes.length) return "0";
  let v = 0n;
  for (const b of bytes) v = (v << 8n) | BigInt(b);
  if (bytes[0] & 0x80) v -= 1n << BigInt(8 * bytes.length);
  const neg = v < 0n;
  let digits = (neg ? -v : v).toString().padStart(scale + 1, "0");
  if (scale > 0) digits = `${digits.slice(0, -scale)}.${digits.slice(-scale)}`;
  return (neg ? "-" : "") + digits;
}
function decode(n, r) {
  switch (n.t) {
    case "null": return null;
    case "boolean": return r.bytes(1)[0] !== 0;
    case "int": case "long": {
      const v = r.long();
      switch (n.logical) {
        case "date": return fmtDays(v);
        case "timestamp-millis": return fmtTimestampMs(v);
        case "timestamp-micros": { const x = Number(v); const ms = Math.floor(x / 1000); return fmtTimestampMs(ms) + pad(((x % 1000) + 1000) % 1000, 3); }
        case "time-millis": return clock(Number(v));
        case "time-micros": { const x = Number(v); return clock(x / 1000) + pad(x % 1000, 3); }
        default: return v;
      }
    }
    case "float": return r.f32();
    case "double": return r.f64();
    case "bytes": { const b = r.bytes(r.int()).slice(); return n.logical === "decimal" ? decimalText(b, n.scale) : b; }
    case "string": return r.string();
    case "fixed": { const b = r.bytes(n.size).slice(); return n.logical === "decimal" ? decimalText(b, n.scale) : b; }
    case "enum": { const i = r.int(); return n.symbols[i] ?? `#${i}`; }
    case "record": { const o = {}; for (const f of n.fields) o[f.name] = decode(f.type, r); return o; }
    case "union": { const i = r.int(); const b = n.branches[i]; if (!b) throw new Eof("bad union branch"); return decode(b, r); }
    case "array": {
      const out = [];
      for (;;) { let c = r.long(); if (c === 0) break; if (c < 0) { c = -c; r.long(); } if (out.length + Number(c) > 5e6) throw new Eof("array too long"); for (let i = 0; i < c; i++) out.push(decode(n.items, r)); }
      return out;
    }
    case "map": {
      const out = {};
      for (;;) { let c = r.long(); if (c === 0) break; if (c < 0) { c = -c; r.long(); } for (let i = 0; i < c; i++) { const k = r.string(); out[k] = decode(n.values, r); } }
      return out;
    }
    default: throw new Eof(`unknown type ${n.t}`);
  }
}

// ---- blocks ----------------------------------------------------------------------------

// Reads one block header at `offset`: { count, bytes, headerLen } or null at/after EOF.
async function blockHeaderAt(source, offset) {
  const buf = await source.read(offset, Math.min(20, source.size - offset));
  const r = new Reader(buf);
  const count = r.long();
  const bytes = r.long();
  return { count: Number(count), bytes: Number(bytes), headerLen: r.pos };
}

async function blockPayload(source, header, offset, hdr) {
  const raw = await source.read(offset + hdr.headerLen, hdr.bytes);
  const codec = header.codec;
  if (codec === "null") return raw;
  if (codec === "deflate") return inflateRaw(raw, FORMAT);
  if (codec === "snappy") {
    if (raw.length < 4) throw bad("CORRUPT", "A snappy block is too short to hold its checksum.");
    const out = snappyDecompress(raw.subarray(0, raw.length - 4), FORMAT);
    const want = ((raw[raw.length - 4] << 24) | (raw[raw.length - 3] << 16) | (raw[raw.length - 2] << 8) | raw[raw.length - 1]) >>> 0;
    if (crc32(out) !== want) throw bad("CORRUPT", "A snappy block's checksum doesn't match: the block is corrupt.");
    return out;
  }
  throw bad("UNSUPPORTED_CODEC", `This Avro file's blocks use the ${codec} codec, which the viewer can't decompress. Null, deflate and snappy files can be previewed.`, codec);
}

// Walks every block header with windowed reads. Memory stays flat: only block
// offsets (capped) are kept.
async function scanBlocks(source, header, { onProgress, signal } = {}) {
  const size = source.size;
  const blocks = [];
  let rows = 0;
  let count = 0;
  let problem = null;
  let pos = header.firstBlock;
  let win = null;
  let winAt = 0;
  let minBytes = Infinity;
  let maxBytes = 0;
  let last = 0;
  const view = async (at, n) => {
    const want = Math.min(n, size - at);
    if (!win || at < winAt || at + want > winAt + win.length) {
      win = await source.read(at, Math.min(WINDOW, size - at));
      winAt = at;
    }
    return win.subarray(at - winAt, at - winAt + want);
  };
  while (pos < size) {
    if (signal?.aborted) throw new DOMException("aborted", "AbortError");
    let hdr;
    try {
      const r = new Reader(await view(pos, 20));
      const c = r.long();
      const b = r.long();
      hdr = { count: c, bytes: b, headerLen: r.pos };
    } catch (e) {
      if (e instanceof Eof) { problem = { kind: "truncated", block: count, offset: pos, detail: `Block ${count} at byte ${fmtInt(pos)} has a header that is cut off.` }; break; }
      throw e;
    }
    if (typeof hdr.count === "bigint" || typeof hdr.bytes === "bigint" || hdr.count < 0 || hdr.bytes < 0) {
      problem = { kind: "invalid", block: count, offset: pos, detail: `Block ${count} at byte ${fmtInt(pos)} has an invalid record count or size.` };
      break;
    }
    const end = pos + hdr.headerLen + hdr.bytes;
    if (end + 16 > size) {
      problem = { kind: "truncated", block: count, offset: pos, detail: `Block ${count} at byte ${fmtInt(pos)} claims ${fmtBytes(hdr.bytes)} but the file ends before it does.` };
      break;
    }
    const sync = await view(end, 16);
    let same = sync.length === 16;
    for (let i = 0; same && i < 16; i++) if (sync[i] !== header.sync[i]) same = false;
    if (!same) {
      problem = { kind: "sync", block: count, offset: pos, detail: `Block ${count} at byte ${fmtInt(pos)} doesn't end with the file's sync marker.` };
      break;
    }
    if (blocks.length < MAX_STORED_BLOCKS) blocks.push({ offset: pos, count: hdr.count, bytes: hdr.bytes });
    rows += hdr.count;
    count++;
    minBytes = Math.min(minBytes, hdr.bytes);
    maxBytes = Math.max(maxBytes, hdr.bytes);
    pos = end + 16;
    const now = Date.now();
    if (onProgress && now - last > 100) { last = now; onProgress(pos / size); await new Promise((r) => setTimeout(r, 0)); }
  }
  return { blocks, rows, count, problem, truncatedIndex: count > blocks.length, minBytes: count ? minBytes : 0, maxBytes, end: pos };
}

// ---- model -------------------------------------------------------------------------------

const printable = (u8) => { try { const t = new TextDecoder("utf-8", { fatal: true }).decode(u8); return /^[\x20-\x7e -￿]*$/.test(t) ? t : null; } catch (_) { return null; } };

export async function openAvro(source) {
  const header = await readHeader(source);
  const schemaBytes = header.meta.get("avro.schema");
  if (!schemaBytes) throw bad("CORRUPT", "This Avro file's header has no avro.schema entry.", "avro.schema missing");
  let schemaJson;
  try { schemaJson = JSON.parse(new TextDecoder().decode(schemaBytes)); } catch (e) { throw bad("CORRUPT", "This Avro file's schema isn't valid JSON.", String(e.message)); }
  const root = parseSchema(schemaJson);
  header.codec = header.meta.has("avro.codec") ? new TextDecoder().decode(header.meta.get("avro.codec")) : "null";
  const size = source.size;
  const readable = READABLE_CODECS.includes(header.codec);
  const columns = root.t === "record" ? root.fields.map((f) => f.name) : ["value"];

  const listeners = new Set();
  const emit = (kind) => listeners.forEach((fn) => fn(kind));
  const scan = { state: "idle", progress: 0, result: null, error: null, controller: null, auto: !!source.local || size <= AUTO_SCAN_BYTES };
  scan.start = async () => {
    if (scan.state === "running" || scan.state === "done") return;
    scan.state = "running";
    scan.progress = 0;
    scan.controller = new AbortController();
    emit("progress");
    try {
      scan.result = await scanBlocks(source, header, {
        signal: scan.controller.signal,
        onProgress: (p) => { scan.progress = p; emit("progress"); },
      });
      scan.state = "done";
      scan.progress = 1;
    } catch (e) {
      scan.state = e && e.name === "AbortError" ? "idle" : "error";
      scan.error = e;
    }
    emit("done");
  };
  scan.cancel = () => scan.controller?.abort();

  const userMeta = [...header.meta.entries()].filter(([k]) => !k.startsWith("avro."));
  const pct = () => `${Math.round(scan.progress * 100)}%`;

  const model = {
    format: "avro",
    label: "Avro",
    size,
    scan,
    tabs: ["info", "schema", "preview", "validate"],
    onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    summary() {
      if (scan.state === "done") return `${fmtInt(scan.result.rows)} records · ${fmtInt(scan.result.count)} block${scan.result.count === 1 ? "" : "s"}`;
      if (scan.state === "running") return `counting records… ${pct()}`;
      return "records not counted yet";
    },
    info() {
      const rows = [["File size", fmtBytes(size)]];
      if (scan.state === "done") {
        rows.push(["Records", fmtInt(scan.result.rows)], ["Blocks", fmtInt(scan.result.count)]);
        if (scan.result.problem) rows.push(["Scan stopped", scan.result.problem.detail]);
        if (scan.result.count) rows.push(["Block size", `${fmtBytes(scan.result.minBytes)} – ${fmtBytes(scan.result.maxBytes)}`]);
      } else {
        rows.push(["Records", scan.state === "running" ? `counting… ${pct()}` : "not counted yet"]);
      }
      rows.push(["Fields", fmtInt(columns.length)]);
      rows.push(["Compression", header.codec === "null" ? "null (uncompressed)" : header.codec]);
      if (root.t === "record") rows.push(["Record", root.full]);
      if (userMeta.length) rows.push(["Metadata", userMeta.map(([k, v]) => { const t = printable(v); return t != null && t.length <= 60 ? `${k}=${t}` : k; }).join(", ")]);
      return rows;
    },
    units() {
      if (scan.state !== "done") return null;
      const stored = scan.result.blocks;
      return {
        title: "Blocks",
        head: ["#", "Records", "Bytes", "Offset"],
        rows: stored.map((b, i) => [i, fmtInt(b.count), fmtBytes(b.bytes), fmtInt(b.offset)]),
        total: scan.result.count,
      };
    },
    schema: () => (root.t === "record" ? root.fields.map((f) => treeNode(f.name, f.type, hasNull(f.type), [root])) : [treeNode("value", root, false, [])]),
    validate() {
      const checks = [
        { id: "magic", label: "Avro magic bytes", status: "pass", detail: "The file starts with Obj\\x01." },
        { id: "header", label: "Header and metadata decode", status: "pass", detail: `${fmtInt(header.meta.size)} metadata entries and a sync marker.` },
        { id: "schema", label: "Schema is valid Avro", status: "pass", detail: root.t === "record" ? `Record ${root.full} with ${fmtInt(columns.length)} fields.` : `A ${root.t} schema.` },
        readable
          ? { id: "codec", label: "Compression readable", status: "pass", detail: `Codec: ${header.codec}.` }
          : { id: "codec", label: "Compression readable", status: "warn", detail: `${header.codec} is valid Avro, but the viewer can't decompress it to preview rows.` },
      ];
      if (scan.state === "done") {
        const r = scan.result;
        const p = r.problem;
        checks.push(
          p && p.kind === "sync" ? { id: "sync", label: "Every block ends with the sync marker", status: "fail", detail: p.detail }
          : p && p.kind === "invalid" ? { id: "sync", label: "Every block ends with the sync marker", status: "fail", detail: p.detail }
          : { id: "sync", label: "Every block ends with the sync marker", status: "pass", detail: `${fmtInt(r.count)} blocks, ${fmtInt(r.rows)} records.` },
          p && p.kind === "truncated" ? { id: "end", label: "File ends on a block boundary", status: "fail", detail: p.detail }
          : { id: "end", label: "File ends on a block boundary", status: "pass", detail: "No partial block at the end." },
        );
      } else if (scan.state === "error") {
        checks.push({ id: "sync", label: "Block checks", status: "fail", detail: `The scan stopped: ${scan.error?.message ?? scan.error}` });
      } else {
        checks.push({ id: "sync", label: "Block checks", status: "pending", detail: scan.state === "running" ? `Reading block headers… ${pct()}` : `Not run yet. Checking every block reads the whole file (${fmtBytes(size)}).` });
      }
      const failed = checks.filter((c) => c.status === "fail").length;
      const warned = checks.filter((c) => c.status === "warn").length;
      const pending = checks.some((c) => c.status === "pending");
      return { checks, failed, warned, verdict: failed ? "fail" : pending ? "partial" : warned ? "pass-with-warnings" : "pass" };
    },
    preview: readable
      ? {
        kind: "rows",
        unitLabel: "Block",
        count: () => (scan.state === "done" ? Math.max(1, Math.min(scan.result.count, scan.result.blocks.length)) : 1),
        label: (i) => (scan.state === "done" && scan.result.blocks[i] ? `Block ${i} · ${fmtInt(scan.result.blocks[i].count)} records` : `Block ${i}`),
        async read(i, limit) {
          const offset = scan.state === "done" ? scan.result.blocks[i]?.offset : i === 0 ? header.firstBlock : undefined;
          if (offset === undefined || offset >= size) return { columns, rows: [], totalRows: 0 };
          let hdr;
          try { hdr = await blockHeaderAt(source, offset); } catch (e) { throw bad("CORRUPT", "This block's header is cut off.", e.message); }
          if (hdr.bytes > 256 * 1024 * 1024) throw bad("CORRUPT", "This block is implausibly large to preview.");
          const payload = await blockPayload(source, header, offset, hdr);
          const r = new Reader(payload);
          const rows = [];
          try {
            for (let k = 0; k < Math.min(hdr.count, limit); k++) {
              const v = decode(root, r);
              rows.push(root.t === "record" ? columns.map((c) => displayValue(v[c])) : [displayValue(v)]);
            }
          } catch (e) {
            if (e instanceof Eof) throw bad("CORRUPT", "Records in this block can't be decoded with the file's schema, so the block is probably corrupt.", e.message);
            throw e;
          }
          return { columns, rows, totalRows: hdr.count };
        },
      }
      : { kind: "error", code: "UNSUPPORTED_CODEC", title: "Unsupported compression", text: `This file's blocks use the ${header.codec} codec, which the viewer can't decompress, so rows can't be previewed. Info, Schema and Validate still work.` },
  };
  if (scan.auto) queueMicrotask(() => scan.start());
  return model;
}

export const _internals = { parseHeader, parseSchema, typeString, decode, Reader, scanBlocks };
