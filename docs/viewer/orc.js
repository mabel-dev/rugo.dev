// ORC reader for the viewer: parses the file tail (postscript + footer), which
// holds the schema, stripe layout and per-column statistics. Only the tail is
// read. Mirrors the checks rugo's native ORC reader makes on open.
import { ViewerError } from "./errors.js";
import { fields, pushVarints, unzigzag, f64, utf8, ProtoError } from "./proto.js";
import { inflateRaw, snappyDecompress, lz4BlockDecompress } from "./codecs.js";
import { fmtBytes, fmtInt, fmtDays, fmtTimestampMs } from "./viewer-core.js";

const FORMAT = "orc";
const COMPRESSION = ["NONE", "ZLIB", "SNAPPY", "LZO", "LZ4", "ZSTD"];
const KINDS = ["BOOLEAN", "BYTE", "SHORT", "INT", "LONG", "FLOAT", "DOUBLE", "STRING", "BINARY", "TIMESTAMP", "LIST", "MAP", "STRUCT", "UNION", "DECIMAL", "DATE", "VARCHAR", "CHAR", "TIMESTAMP_INSTANT"];
const SQL_NAMES = { BYTE: "tinyint", SHORT: "smallint", INT: "int", LONG: "bigint" };
const WRITERS = ["ORC Java", "ORC C++", "Presto", "Scritchley Go", "Trino"];
const TAIL_GUESS = 16 * 1024;
const MAX_FOOTER = 256 * 1024 * 1024;

const bad = (code, msg, detail) => new ViewerError(code, msg, detail, FORMAT);

// ---- decoding the tail -----------------------------------------------------------

function parsePostscript(u8) {
  const ps = { footerLength: 0, compression: 0, blockSize: 262144, version: [], metadataLength: 0, writerVersion: 0, magic: "" };
  for (const [f, w, v] of fields(u8)) {
    if (f === 1) ps.footerLength = Number(v);
    else if (f === 2) ps.compression = Number(v);
    else if (f === 3) ps.blockSize = Number(v);
    else if (f === 4) pushVarints(ps.version, w, v);
    else if (f === 5) ps.metadataLength = Number(v);
    else if (f === 6) ps.writerVersion = Number(v);
    else if (f === 8000) ps.magic = utf8(v);
  }
  return ps;
}

async function decompress(kind, blockSize, bytes) {
  if (kind === 0) return bytes;
  const name = COMPRESSION[kind];
  if (name === undefined) throw bad("CORRUPT", `This ORC file names an unknown compression (${kind}).`);
  if (name === "ZSTD" || name === "LZO") {
    throw bad("UNSUPPORTED_CODEC", `This ORC file's footer is compressed with ${name}, which the viewer can't decompress yet. ORC files using NONE, ZLIB, SNAPPY or LZ4 open fine.`, name);
  }
  const chunks = [];
  let pos = 0;
  let total = 0;
  while (pos < bytes.length) {
    if (pos + 3 > bytes.length) throw bad("CORRUPT", "An ORC compression chunk header is cut off.");
    const h = bytes[pos] | (bytes[pos + 1] << 8) | (bytes[pos + 2] << 16);
    const len = h >>> 1;
    pos += 3;
    if (pos + len > bytes.length) throw bad("CORRUPT", "An ORC compression chunk runs past the end of its data.");
    const chunk = bytes.subarray(pos, pos + len);
    pos += len;
    const out = h & 1 ? chunk
      : name === "ZLIB" ? await inflateRaw(chunk, FORMAT)
      : name === "SNAPPY" ? snappyDecompress(chunk, FORMAT, blockSize)
      : lz4BlockDecompress(chunk, blockSize, FORMAT);
    chunks.push(out);
    total += out.length;
  }
  if (chunks.length === 1) return chunks[0];
  const all = new Uint8Array(total);
  let o = 0;
  for (const c of chunks) { all.set(c, o); o += c.length; }
  return all;
}

function parseStats(buf) {
  const s = { values: 0, hasNull: null, bytesOnDisk: null };
  for (const [f, , v] of fields(buf)) {
    if (f === 1) s.values = Number(v);
    else if (f === 2) { s.kind = "int"; for (const [g, , x] of fields(v)) { if (g === 1) s.min = unzigzag(x); else if (g === 2) s.max = unzigzag(x); else if (g === 3) s.sum = unzigzag(x); } }
    else if (f === 3) { s.kind = "double"; for (const [g, , x] of fields(v)) { if (g === 1) s.min = f64(x); else if (g === 2) s.max = f64(x); else if (g === 3) s.sum = f64(x); } }
    else if (f === 4) { s.kind = "string"; for (const [g, , x] of fields(v)) { if (g === 1) s.min = utf8(x); else if (g === 2) s.max = utf8(x); } }
    else if (f === 5) { s.kind = "bucket"; const c = []; for (const [g, w, x] of fields(v)) if (g === 1) pushVarints(c, w, x); s.trueCount = c[0]; }
    else if (f === 6) { s.kind = "decimal"; for (const [g, , x] of fields(v)) { if (g === 1) s.min = utf8(x); else if (g === 2) s.max = utf8(x); } }
    else if (f === 7) { s.kind = "date"; for (const [g, , x] of fields(v)) { if (g === 1) s.min = unzigzag(x); else if (g === 2) s.max = unzigzag(x); } }
    else if (f === 8) s.kind = "binary";
    else if (f === 9) { s.kind = "timestamp"; for (const [g, , x] of fields(v)) { if (g === 1 && s.min === undefined) s.min = unzigzag(x); else if (g === 2 && s.max === undefined) s.max = unzigzag(x); else if (g === 3) s.min = unzigzag(x); else if (g === 4) s.max = unzigzag(x); } }
    else if (f === 10) s.hasNull = Number(v) !== 0;
    else if (f === 11) s.bytesOnDisk = Number(v);
  }
  return s;
}

function parseFooter(u8) {
  const ft = { headerLength: 0, contentLength: 0, stripes: [], types: [], numberOfRows: 0, statistics: [], rowIndexStride: 0, writer: null, softwareVersion: "", encrypted: false, metadata: [] };
  for (const [f, , v] of fields(u8)) {
    if (f === 1) ft.headerLength = Number(v);
    else if (f === 2) ft.contentLength = Number(v);
    else if (f === 3) {
      const s = { offset: 0, indexLength: 0, dataLength: 0, footerLength: 0, rows: 0 };
      for (const [g, , x] of fields(v)) { if (g === 1) s.offset = Number(x); else if (g === 2) s.indexLength = Number(x); else if (g === 3) s.dataLength = Number(x); else if (g === 4) s.footerLength = Number(x); else if (g === 5) s.rows = Number(x); }
      ft.stripes.push(s);
    } else if (f === 4) {
      const t = { kind: 0, subtypes: [], names: [], maxLength: 0, precision: 0, scale: 0, attributes: [] };
      for (const [g, w, x] of fields(v)) {
        if (g === 1) t.kind = Number(x);
        else if (g === 2) pushVarints(t.subtypes, w, x);
        else if (g === 3) t.names.push(utf8(x));
        else if (g === 4) t.maxLength = Number(x);
        else if (g === 5) t.precision = Number(x);
        else if (g === 6) t.scale = Number(x);
        else if (g === 7) { let k = ""; let val = ""; for (const [h, , y] of fields(x)) { if (h === 1) k = utf8(y); else if (h === 2) val = utf8(y); } t.attributes.push([k, val]); }
      }
      ft.types.push(t);
    } else if (f === 5) {
      let k = "";
      for (const [g, , x] of fields(v)) if (g === 1) k = utf8(x);
      ft.metadata.push(k);
    } else if (f === 6) ft.numberOfRows = Number(v);
    else if (f === 7) ft.statistics.push(parseStats(v));
    else if (f === 8) ft.rowIndexStride = Number(v);
    else if (f === 9) ft.writer = Number(v);
    else if (f === 10) ft.encrypted = true;
    else if (f === 12) ft.softwareVersion = utf8(v);
  }
  return ft;
}

// Reads and decodes the tail. Returns { ps, footer, tailLength }.
async function readTail(source) {
  const size = source.size;
  if (size < 4) throw bad("TRUNCATED", "This file is too short to be an ORC file.");
  const win = Math.min(size, TAIL_GUESS);
  let tail = source.prefetched && source.prefetched.length >= win ? source.prefetched : await source.read(size - win, win);
  const psLen = tail[tail.length - 1];
  const truncated = () => bad("TRUNCATED", "This file starts like an ORC file, but the postscript at its end is missing or damaged. It looks truncated or corrupted.", "postscript");
  if (psLen === 0 || psLen + 1 > tail.length) throw truncated();
  let ps;
  try { ps = parsePostscript(tail.subarray(tail.length - 1 - psLen, tail.length - 1)); } catch (e) { if (e instanceof ProtoError) throw truncated(); throw e; }
  if (ps.magic !== "ORC") throw truncated();
  const need = 1 + psLen + ps.footerLength;
  if (need > size) throw bad("CORRUPT", "This ORC file is corrupt: its footer would start before the beginning of the file.", `footerLength ${ps.footerLength}`);
  if (ps.footerLength > MAX_FOOTER) throw bad("CORRUPT", "This ORC file's footer is implausibly large.", `footerLength ${ps.footerLength}`);
  if (need > tail.length) {
    const more = await source.read(size - need, need - tail.length);
    const all = new Uint8Array(need);
    all.set(more, 0);
    all.set(tail, need - tail.length);
    tail = all;
  }
  const footerAt = tail.length - need;
  const raw = tail.subarray(footerAt, footerAt + ps.footerLength);
  const footerBytes = await decompress(ps.compression, ps.blockSize, raw);
  let footer;
  try { footer = parseFooter(footerBytes); } catch (e) {
    if (e instanceof ProtoError) throw bad("CORRUPT", "This ORC file's footer couldn't be decoded, so the file is probably corrupt.", e.message);
    throw e;
  }
  return { ps, footer, tailLength: need };
}

// ---- schema ----------------------------------------------------------------------

function typeLabel(t) {
  const k = KINDS[t.kind] ?? `kind ${t.kind}`;
  if (k === "DECIMAL") return `decimal(${t.precision},${t.scale})`;
  if (k === "VARCHAR" || k === "CHAR") return `${k.toLowerCase()}(${t.maxLength})`;
  return SQL_NAMES[k] ?? k.toLowerCase();
}

// Preorder list of every type node with a dotted path.
function flatten(types) {
  const out = [];
  const seen = new Set();
  const walk = (id, path, depth) => {
    const t = types[id];
    if (!t || seen.has(id) || depth > 64) return;
    seen.add(id);
    out.push({ id, path, depth, t });
    const k = KINDS[t.kind];
    t.subtypes.forEach((sub, i) => {
      const name = k === "STRUCT" ? t.names[i] ?? `f${i}` : k === "LIST" ? "element" : k === "MAP" ? (i === 0 ? "key" : "value") : `u${i}`;
      walk(sub, path ? `${path}.${name}` : name, depth + 1);
    });
  };
  walk(0, "", 0);
  return out;
}

function buildTree(types) {
  const seen = new Set();
  const node = (id, name) => {
    const t = types[id];
    const k = KINDS[t.kind];
    const n = { name, path: name, kind: "leaf", type: typeLabel(t), physical: k, nullable: true, children: [] };
    if (seen.has(id)) return n;
    seen.add(id);
    const kids = t.subtypes.filter((s) => types[s]);
    if (k === "STRUCT") { n.kind = "struct"; n.type = "struct"; n.children = kids.map((s, i) => node(s, t.names[i] ?? `f${i}`)); }
    else if (k === "LIST") {
      n.kind = "list";
      const el = types[kids[0]];
      const simple = el && !["LIST", "MAP", "STRUCT", "UNION"].includes(KINDS[el.kind]);
      n.type = `array<${el ? typeLabel(el) : "?"}>`;
      if (!simple && kids.length) n.children = [node(kids[0], "element")];
    } else if (k === "MAP") {
      n.kind = "map";
      const [kt, vt] = [types[kids[0]], types[kids[1]]];
      n.type = `map<${kt ? typeLabel(kt) : "?"}, ${vt ? typeLabel(vt) : "?"}>`;
      n.children = kids.map((s, i) => node(s, i === 0 ? "key" : "value"));
    } else if (k === "UNION") { n.kind = "union"; n.type = "union"; n.children = kids.map((s, i) => node(s, `u${i}`)); }
    seen.delete(id);
    return n;
  };
  const root = types[0];
  return root.subtypes.map((s, i) => node(s, root.names[i] ?? `f${i}`));
}

// ---- describe --------------------------------------------------------------------

function statText(s, kind) {
  if (!s) return [undefined, undefined];
  const cut = (x) => (typeof x === "string" && x.length > 48 ? x.slice(0, 48) + "…" : x);
  switch (s.kind) {
    case "int": return [s.min, s.max].map((x) => (x === undefined ? undefined : String(x)));
    case "double": return [s.min, s.max].map((x) => (x === undefined ? undefined : String(x)));
    case "string": return [cut(s.min), cut(s.max)];
    case "decimal": return [s.min, s.max];
    case "date": return [s.min, s.max].map((x) => (x === undefined ? undefined : fmtDays(x)));
    case "timestamp": return [s.min, s.max].map((x) => (x === undefined ? undefined : fmtTimestampMs(x)));
    default: return [undefined, undefined];
  }
}

function describeTable(footer) {
  const flat = flatten(footer.types).filter((f) => f.id !== 0);
  const rows = footer.numberOfRows;
  const topIds = new Set(footer.types[0].subtypes);
  const head = [
    { t: "Column" }, { t: "Type" }, { t: "Values", num: true }, { t: "Nulls", num: true }, { t: "Null %", num: true },
    { t: "Min" }, { t: "Max" }, { t: "Stats" }, { t: "Size", num: true },
  ];
  const body = flat.map(({ id, path, t }) => {
    const s = footer.statistics[id];
    const [min, max] = statText(s);
    const top = topIds.has(id);
    const nulls = top && s ? Math.max(0, rows - s.values) : null;
    const pct = nulls != null && rows ? (nulls / rows) * 100 : null;
    const boolText = s?.kind === "bucket" && s.trueCount !== undefined ? `${fmtInt(s.trueCount)} true` : undefined;
    return {
      key: path.toLowerCase(),
      cells: [
        { t: path, mono: true },
        { t: typeLabel(t) },
        { t: s ? fmtInt(s.values) : "–", num: true },
        { t: nulls == null ? "–" : fmtInt(nulls), num: true },
        { t: pct == null ? "–" : `${pct < 0.01 && nulls ? "<0.01" : pct.toFixed(pct < 10 ? 2 : 1)}%`, num: true },
        { t: min ?? boolText ?? "–", mono: true },
        { t: max ?? "–", mono: true },
        { t: min !== undefined || max !== undefined ? "✓" : "–", cls: "rv-stat", title: min !== undefined ? "Min/max statistics are stored in the file" : "No min/max statistics stored" },
        { t: s?.bytesOnDisk != null ? fmtBytes(s.bytesOnDisk) : "–", num: true },
      ],
    };
  });
  // Drop the Size column when the writer didn't record bytes on disk.
  if (!flat.some(({ id }) => footer.statistics[id]?.bytesOnDisk != null)) {
    head.pop();
    for (const r of body) r.cells.pop();
  }
  return { head, rows: body, count: body.length };
}

// ---- validate --------------------------------------------------------------------

const P = (id, label, detail) => ({ id, label, status: "pass", detail });
const F = (id, label, detail) => ({ id, label, status: "fail", detail });
const W = (id, label, detail) => ({ id, label, status: "warn", detail });

function validate(ps, footer, size, tailLength) {
  const checks = [];
  checks.push(P("magic", "ORC magic at both ends", "The file starts with ORC and its postscript says ORC."));
  checks.push(P("tail", "Postscript and footer fit", `${fmtBytes(tailLength)} tail inside a ${fmtBytes(size)} file.`));
  checks.push(P("footer", "Footer decompresses and decodes", `${COMPRESSION[ps.compression]}-compressed footer decoded: ${fmtInt(footer.types.length)} types, ${fmtInt(footer.stripes.length)} stripe${footer.stripes.length === 1 ? "" : "s"}.`));
  checks.push(footer.encrypted ? W("encrypted", "Not encrypted", "This file uses ORC column encryption, which the viewer can't read.") : P("encrypted", "Not encrypted", "No encryption metadata."));

  const root = footer.types[0];
  const rootProblem = !root ? "The footer has no types."
    : KINDS[root.kind] !== "STRUCT" ? "The root type isn't a struct."
    : root.subtypes.length !== root.names.length ? `The root struct has ${root.subtypes.length} columns but ${root.names.length} names.`
    : root.subtypes.find((s) => s >= footer.types.length) !== undefined ? "A column refers to a type that doesn't exist."
    : null;
  checks.push(rootProblem ? F("root", "Root struct and column types", rootProblem) : P("root", "Root struct and column types", `${fmtInt(root.subtypes.length)} columns under a struct root.`));

  const contentEnd = size - tailLength - ps.metadataLength;
  let stripeProblem = null;
  let prevEnd = Math.max(3, footer.headerLength || 0);
  footer.stripes.forEach((s, i) => {
    const end = s.offset + s.indexLength + s.dataLength + s.footerLength;
    if (!stripeProblem && (end > contentEnd || end < s.offset)) stripeProblem = `Stripe ${i} runs to byte ${fmtInt(end)}, past the file's content area (${fmtInt(contentEnd)}).`;
    else if (!stripeProblem && s.offset < prevEnd) stripeProblem = `Stripe ${i} starts at byte ${fmtInt(s.offset)}, inside the previous stripe or the header.`;
    prevEnd = end;
  });
  checks.push(stripeProblem ? F("stripes", "Stripes lie inside the file, in order", stripeProblem) : P("stripes", "Stripes lie inside the file, in order", `${fmtInt(footer.stripes.length)} stripe${footer.stripes.length === 1 ? "" : "s"}, each within the content area and non-overlapping.`));

  const sum = footer.stripes.reduce((n, s) => n + s.rows, 0);
  checks.push(sum === footer.numberOfRows ? P("rows", "Row counts add up", `Stripes total ${fmtInt(sum)} rows, matching the file's ${fmtInt(footer.numberOfRows)}.`) : F("rows", "Row counts add up", `Stripes total ${fmtInt(sum)} rows but the file says ${fmtInt(footer.numberOfRows)}.`));

  if (footer.statistics.length === 0) checks.push(W("stats", "Column statistics present", "The file has no file-level column statistics."));
  else checks.push(footer.statistics.length === footer.types.length ? P("stats", "Column statistics cover every column", `${fmtInt(footer.statistics.length)} statistics entries for ${fmtInt(footer.types.length)} types.`) : F("stats", "Column statistics cover every column", `${footer.statistics.length} statistics entries for ${footer.types.length} types.`));

  const failed = checks.filter((c) => c.status === "fail").length;
  const warned = checks.filter((c) => c.status === "warn").length;
  return { checks, failed, warned, verdict: failed ? "fail" : warned ? "pass-with-warnings" : "pass" };
}

// ---- model -----------------------------------------------------------------------

export async function openOrc(source) {
  const { ps, footer, tailLength } = await readTail(source);
  if (!footer.types.length || KINDS[footer.types[0].kind] !== "STRUCT") {
    // Not enough to build views; the validate view reports why.
    throw bad("CORRUPT", "This ORC file's root type isn't a struct, so the file is probably corrupt.", "root type");
  }
  const size = source.size;
  const codec = COMPRESSION[ps.compression];
  const top = footer.types[0].subtypes.length;
  const stripes = footer.stripes;
  const writerName = footer.writer != null ? WRITERS[footer.writer] ?? `writer ${footer.writer}` : "";
  const writer = footer.softwareVersion && /[A-Za-z]/.test(footer.softwareVersion) ? footer.softwareVersion
    : [writerName, footer.softwareVersion].filter(Boolean).join(" ");
  return {
    format: "orc",
    label: "ORC",
    size,
    tabs: ["info", "schema", "preview", "describe", "validate"],
    summary: () => `${fmtInt(footer.numberOfRows)} rows · ${fmtInt(stripes.length)} stripe${stripes.length === 1 ? "" : "s"}`,
    info() {
      const dataBytes = stripes.reduce((n, s) => n + s.indexLength + s.dataLength + s.footerLength, 0);
      const rows = [
        ["File size", fmtBytes(size)],
        ["Rows", fmtInt(footer.numberOfRows)],
        ["Columns", fmtInt(top)],
        ["Stripes", fmtInt(stripes.length)],
      ];
      if (stripes.length) rows.push(["Rows per stripe", fmtInt(Math.round(footer.numberOfRows / stripes.length))]);
      rows.push(["Compression", codec === "NONE" ? "NONE" : `${codec} (${fmtBytes(ps.blockSize)} blocks)`]);
      if (dataBytes) rows.push(["Stripe data", fmtBytes(dataBytes)]);
      if (writer) rows.push(["Created by", writer]);
      if (ps.version.length) rows.push(["ORC version", ps.version.join(".")]);
      if (footer.rowIndexStride) rows.push(["Row index stride", fmtInt(footer.rowIndexStride) + " rows"]);
      if (footer.metadata.length) rows.push(["User metadata keys", footer.metadata.join(", ")]);
      return rows;
    },
    units: () => ({
      title: "Stripes",
      head: ["#", "Rows", "Index", "Data", "Footer", "Offset"],
      rows: stripes.map((s, i) => [i, fmtInt(s.rows), fmtBytes(s.indexLength), fmtBytes(s.dataLength), fmtBytes(s.footerLength), fmtInt(s.offset)]),
    }),
    schema: () => buildTree(footer.types),
    describe: () => describeTable(footer),
    validate: () => validate(ps, footer, size, tailLength),
    preview: {
      kind: "unavailable",
      title: "Row preview isn't available for ORC yet",
      text: "Info, Schema, Describe (with min/max from the file's statistics) and Validate work now, and they read nothing but the file's tail.",
    },
  };
}

// Exposed for tests.
export const _internals = { parseFooter, parsePostscript, decompress, flatten };
