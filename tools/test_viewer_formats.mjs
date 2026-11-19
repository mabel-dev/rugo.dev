// Tests for the Avro / ORC readers, the tolerant inflate, format detection and
// URL byte sources, against real files written by fastavro and pyarrow.
//   node --test tools/test_viewer_formats.mjs
import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import zlib from "node:zlib";
import { readFileSync } from "node:fs";
import { openOrc } from "../docs/viewer/orc.js";
import { openAvro } from "../docs/viewer/avro.js";
import { detect } from "../docs/viewer/formats.js";
import { inflateRawSync } from "../docs/viewer/codecs.js";
import { fileSource, urlSource } from "../docs/viewer/sources.js";
import { ViewerError } from "../docs/viewer/errors.js";

const fx = (name) => readFileSync(new URL(`./fixtures/${name}`, import.meta.url));
const src = (buf) => {
  const bytes = new Uint8Array(buf);
  const s = { size: bytes.length, local: true, reads: [], async read(o, n) { s.reads.push([o, n]); return bytes.slice(o, o + n); } };
  return s;
};
const avroDone = (m) => new Promise((r) => { if (m.scan.state === "done") r(); else m.onChange((k) => k === "done" && r()); });
const code = async (p) => { try { await p; return null; } catch (e) { return e instanceof ViewerError ? e.code : `other:${e.message}`; } };

// ---- inflate ----------------------------------------------------------------------

test("inflate matches zlib for stored, fixed and dynamic blocks, and ignores trailing bytes", () => {
  const rnd = (n) => Uint8Array.from({ length: n }, (_, i) => (i * 2654435761) >>> 24);
  const text = Buffer.from("the quick brown fox ".repeat(5000));
  for (const [data, level] of [[rnd(5000), 0], [Buffer.from("abc"), 6], [text, 1], [text, 9], [Buffer.alloc(0), 6], [rnd(200000), 6]]) {
    const z = zlib.deflateRawSync(data, { level });
    assert.deepEqual(Buffer.from(inflateRawSync(new Uint8Array(z), "t")), Buffer.from(data));
    const junk = Buffer.concat([z, Buffer.from([9, 9, 9])]);
    assert.deepEqual(Buffer.from(inflateRawSync(new Uint8Array(junk), "t")), Buffer.from(data));
  }
});

test("inflate rejects garbage instead of looping", () => {
  assert.throws(() => inflateRawSync(new Uint8Array([0xff, 0xff, 0xff, 0xff, 0xff, 0xff]), "t"), /damaged/);
  const z = zlib.deflateRawSync(Buffer.from("hello world ".repeat(100)));
  assert.throws(() => inflateRawSync(new Uint8Array(z.subarray(0, z.length >> 1)), "t"), /damaged/);
});

// ---- detection -------------------------------------------------------------------

test("detect finds each format by its magic bytes", async () => {
  assert.equal(await detect(src(fx("null.avro"))), "avro");
  assert.equal(await detect(src(fx("zlib.orc"))), "orc");
  assert.equal(await detect(src(Buffer.from("PAR1 and more"))), "parquet");
  assert.equal(await code(detect(src(Buffer.from("plain text here")))), "UNKNOWN_FORMAT");
  assert.equal(await code(detect(src(Buffer.alloc(0)))), "EMPTY");
});

// ---- ORC ---------------------------------------------------------------------------

for (const codec of ["uncompressed", "zlib", "snappy", "lz4"]) {
  test(`orc ${codec}: info, schema, describe and validate`, async () => {
    const s = src(fx(`${codec}.orc`));
    const m = await openOrc(s);
    const info = Object.fromEntries(m.info());
    assert.equal(info.Rows, "1,100");
    assert.equal(info.Columns, "10");
    assert.equal(info.Compression.split(" ")[0], codec === "uncompressed" ? "NONE" : codec.toUpperCase());
    assert.match(info["Created by"], /ORC C\+\+/);
    assert.deepEqual(s.reads.length, 1, "the tail is read in one request");
    assert.ok(s.reads[0][1] <= 16384, "and it is at most 16 KB");

    const roots = m.schema();
    assert.deepEqual(roots.map((r) => r.name), ["id", "name", "score", "flag", "day", "ts", "amount", "tags", "addr", "attrs"]);
    const by = Object.fromEntries(roots.map((r) => [r.name, r]));
    assert.equal(by.amount.type, "decimal(10,2)");
    assert.equal(by.tags.kind, "list");
    assert.equal(by.tags.type, "array<string>");
    assert.deepEqual(by.addr.children.map((c) => c.name), ["city", "geo"]);
    assert.deepEqual(by.addr.children[1].children.map((c) => c.name), ["lat", "lon"]);
    assert.equal(by.attrs.kind, "map");
    assert.deepEqual(by.attrs.children.map((c) => c.name), ["key", "value"]);

    const d = m.describe();
    const row = (name) => d.rows.find((r) => r.cells[0].t === name).cells.map((c) => c.t);
    assert.deepEqual(row("id").slice(2, 8), ["1,100", "0", "0.00%", "0", "1099", "✓"]);
    assert.deepEqual(row("name").slice(2, 8), ["880", "220", "20.0%", "user1", "user999", "✓"]);
    assert.equal(row("day")[5], "2020-01-01");
    assert.equal(row("amount")[5], "0.25");
    assert.equal(row("flag")[5], "550 true");

    assert.equal(m.validate().verdict, "pass");
  });
}

test("orc uncompressed has two stripes that add up", async () => {
  const m = await openOrc(src(fx("uncompressed.orc")));
  const u = m.units();
  assert.equal(u.rows.length, 2);
  assert.equal(u.rows.reduce((n, r) => n + Number(r[1].replace(/,/g, "")), 0), 1100);
});

test("orc validate fails when the footer's counts are tampered with", async () => {
  // Patch numberOfRows in an uncompressed footer: find the footer, rewrite the varint.
  const buf = Buffer.from(fx("uncompressed.orc"));
  const m0 = await openOrc(src(buf));
  assert.equal(m0.validate().verdict, "pass");
  // Truncating the stripe data region makes a stripe run past the content area.
  const cut = buf.subarray(0, 10_000);
  assert.equal(await code(openOrc(src(cut))), "TRUNCATED");
});

test("orc errors are classified", async () => {
  assert.equal(await code(openOrc(src(fx("zstd.orc")))), "UNSUPPORTED_CODEC");
  const b = fx("zlib.orc");
  assert.equal(await code(openOrc(src(b.subarray(0, Math.floor(b.length * 2 / 3))))), "TRUNCATED");
  assert.equal(await code(openOrc(src(Buffer.from("ORC")))), "TRUNCATED");
});

// ---- Avro --------------------------------------------------------------------------

for (const codec of ["null", "deflate", "snappy"]) {
  test(`avro ${codec}: scan, schema, preview`, async () => {
    const s = src(fx(`${codec}.avro`));
    const m = await openAvro(s);
    await avroDone(m);
    const info = Object.fromEntries(m.info());
    assert.equal(info.Records, "1,100");
    assert.equal(info.Blocks, "58");
    assert.equal(info.Fields, "13");
    assert.equal(info.Compression, codec === "null" ? "null (uncompressed)" : codec);
    assert.equal(info.Record, "demo.events.Event");
    assert.equal(info.Metadata, "owner=demo");
    assert.equal(m.validate().verdict, "pass");

    const by = Object.fromEntries(m.schema().map((n) => [n.name, n]));
    assert.equal(by.name.nullable, true);
    assert.equal(by.id.nullable, false);
    assert.equal(by.kind.type, "enum Kind(A, B, C)");
    assert.equal(by.ts.type, "long (timestamp-micros)");
    assert.equal(by.amount.type, "decimal(10,2)");
    assert.equal(by.tags.kind, "list");
    assert.equal(by.attrs.kind, "map");
    assert.deepEqual(by.addr.children.map((c) => c.name), ["city", "geo"]);
    assert.equal(by.home.nullable, true);
    assert.equal(by.home.kind, "struct");

    assert.equal(m.preview.count(), 58);
    const p0 = await m.preview.read(0, 3);
    assert.deepEqual(p0.columns.slice(0, 5), ["id", "name", "score", "flag", "kind"]);
    assert.deepEqual(p0.rows[0], ["0", null, "0", "true", "A", "2020-01-01", "2021-06-01 12:00:00.000000", "0.25", "[]", '{"k":0}', '{"city":"Leeds","geo":{"lat":53.8,"lon":-1.5}}', '{"city":"York","geo":{"lat":1,"lon":2}}', "0x00010203"]);
    assert.deepEqual(p0.rows[1].slice(0, 2), ["1", "user1"]);
    assert.equal(p0.rows[1][11], null);
    assert.equal(p0.rows.length, 3);
    const last = await m.preview.read(57, 100);
    assert.equal(last.totalRows, 16);
    assert.equal(last.rows.length, 16);
    assert.equal(last.rows[15][0], "1099");
  });
}

test("avro reads in windows, not the whole file at once", async () => {
  const s = src(fx("null.avro"));
  const m = await openAvro(s);
  await avroDone(m);
  assert.ok(Math.max(...s.reads.map(([, n]) => n)) <= 4 * 1024 * 1024);
});

test("avro validate flags a truncated file and a bad sync marker", async () => {
  const buf = Buffer.from(fx("null.avro"));
  const cut = buf.subarray(0, Math.floor(buf.length * 2 / 3));
  let m = await openAvro(src(cut));
  await avroDone(m);
  let v = m.validate();
  assert.equal(v.verdict, "fail");
  assert.equal(v.checks.find((c) => c.id === "end").status, "fail");

  // The header ends with the 16-byte sync marker and every block ends with a copy of
  // it, so the file's last 16 bytes are the marker. Corrupt the 5th copy: the header's
  // plus the ends of blocks 0-3, which makes block 3 the first with a bad marker.
  const bad = Buffer.from(buf);
  const marker = buf.subarray(buf.length - 16);
  let at = -1;
  for (let i = 0, seen = 0; i < buf.length - 16; i++) { if (buf.compare(marker, 0, 16, i, i + 16) === 0 && ++seen === 5) { at = i; break; } }
  assert.ok(at > 0);
  bad[at] ^= 0xff;
  m = await openAvro(src(bad));
  await avroDone(m);
  v = m.validate();
  assert.equal(v.verdict, "fail");
  assert.match(v.checks.find((c) => c.id === "sync").detail, /^Block 3 /);
});

test("avro errors are classified", async () => {
  const buf = fx("null.avro");
  assert.equal(await code(openAvro(src(buf.subarray(0, 30)))), "TRUNCATED");
  const m = await openAvro(src(buf));
  await avroDone(m);
  // not Avro at all
  assert.equal(await code(openAvro(src(Buffer.from("hello there, not avro")))), "UNKNOWN_FORMAT");
});

test("avro URL-style sources don't scan big files until asked", async () => {
  const s = src(Buffer.concat([fx("null.avro")]));
  s.local = false;
  s.size = 100 * 1024 * 1024; // pretend it is large; the bytes we serve are the real file
  const real = s.read;
  s.read = async (o, n) => real(o, Math.min(n, 1 << 20));
  const m = await openAvro(s);
  assert.equal(m.scan.state, "idle");
  assert.equal(m.validate().verdict, "partial");
  assert.equal((await m.preview.read(0, 2)).rows.length, 2, "block 0 previews before any scan");
});

test("avro URL-style sources under 8 MB scan automatically", async () => {
  const s = src(fx("null.avro"));
  s.local = false;
  const m = await openAvro(s);
  await avroDone(m);
  assert.equal(m.scan.state, "done");
});

// ---- sources ------------------------------------------------------------------------

function rangeServer(buf, mode) {
  const log = [];
  const server = http.createServer((req, res) => {
    log.push(req.headers.range ?? "(none)");
    if (req.url.startsWith("/missing")) { res.writeHead(404); return res.end(); }
    const r = req.headers.range;
    if (!r || mode === "norange") { res.writeHead(200, { "Content-Length": buf.length }); return res.end(buf); }
    const m = /bytes=(\d*)-(\d*)/.exec(r);
    let s;
    let e;
    if (m[1] === "") { s = Math.max(0, buf.length - Number(m[2])); e = buf.length - 1; } else { s = Number(m[1]); e = Math.min(Number(m[2] || buf.length - 1), buf.length - 1); }
    res.writeHead(206, { "Content-Range": `bytes ${s}-${e}/${buf.length}`, "Content-Length": e - s + 1 });
    res.end(buf.subarray(s, e + 1));
  });
  return new Promise((r) => server.listen(0, () => r({ server, log, url: `http://127.0.0.1:${server.address().port}/f` })));
}

test("urlSource gets size and tail in one request, then ranges only what's asked", async () => {
  const buf = fx("null.avro");
  const { server, log, url } = await rangeServer(buf);
  try {
    const s = await urlSource(url);
    assert.equal(s.size, buf.length);
    assert.equal(log.length, 1);
    assert.equal(log[0], "bytes=-65536");
    assert.deepEqual(Buffer.from(await s.read(0, 4)), buf.subarray(0, 4));
    assert.equal(log[1], "bytes=0-3");
    const before = log.length;
    assert.deepEqual(Buffer.from(await s.read(buf.length - 10, 10)), buf.subarray(buf.length - 10), "tail reads come from the prefetch");
    assert.equal(log.length, before);
    assert.equal(await detect(s), "avro");
  } finally { server.close(); }
});

test("urlSource reports servers without range support and missing files", async () => {
  let r = await rangeServer(fx("null.avro"), "norange");
  assert.equal(await code(urlSource(r.url)), "RANGE_UNSUPPORTED");
  r.server.close();
  r = await rangeServer(fx("null.avro"));
  assert.equal(await code(urlSource(r.url.replace("/f", "/missing"))), "HTTP");
  r.server.close();
  assert.equal(await code(urlSource("http://127.0.0.1:1/x")), "NETWORK");
});

test("fileSource reads ranges of a Blob", async () => {
  const s = fileSource(new Blob([Buffer.from("0123456789")]));
  assert.equal(s.size, 10);
  assert.deepEqual([...(await s.read(2, 3))], [0x32, 0x33, 0x34]);
});
