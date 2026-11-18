// Tests for the viewer's data layer and error classifier. No browser, no WASM.
//   node --test tools/test_viewer_core.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  buildInfo, buildSchemaTree, describeColumns, validateFooter, validateFailure,
  unsupportedCodecs, fmtBytes, leafColumns,
} from "../docs/viewer/viewer-core.js";
import { classifyError } from "../docs/viewer/engine.js";

// Real output of Rugo's WASM readFooter for a pyarrow-written file with nested columns.
const { fileSize, footer } = JSON.parse(readFileSync(new URL("./fixtures/footer_nested.json", import.meta.url)));
const clone = () => structuredClone(footer);

test("info reports size, rows, groups, compression", () => {
  const info = Object.fromEntries(buildInfo(footer, fileSize));
  assert.equal(info["Rows"], "3,000");
  assert.equal(info["Row groups"], "2");
  assert.equal(info["Columns"], "10");
  assert.equal(info["Compression"], "SNAPPY");
  assert.equal(info["Created by"], undefined, "created_by is omitted when the engine doesn't supply it");
  assert.equal(Object.fromEntries(buildInfo({ ...footer, created_by: "parquet-cpp 1.2" }, fileSize))["Created by"], "parquet-cpp 1.2");
});

test("schema tree nests struct, list and map", () => {
  const roots = buildSchemaTree(footer);
  const by = Object.fromEntries(roots.map((r) => [r.name, r]));
  assert.deepEqual(roots.map((r) => r.name), ["id", "name", "score", "ts", "tags", "addr", "attrs"]);
  assert.equal(by.tags.kind, "list");
  assert.equal(by.tags.type, "array<varchar>");
  assert.equal(by.addr.kind, "struct");
  assert.deepEqual(by.addr.children.map((c) => c.name), ["city", "geo"]);
  assert.deepEqual(by.addr.children[1].children.map((c) => c.name), ["lat", "lon"]);
  assert.equal(by.addr.children[1].kind, "struct");
  assert.equal(by.attrs.kind, "map");
  assert.deepEqual(by.attrs.children.map((c) => c.name), ["key", "value"], "key_value wrapper is folded away");
  assert.equal(by.id.kind, "leaf");
});

test("schema tree handles flat column names containing dots", () => {
  const f = {
    num_rows: 1, num_row_groups: 1,
    schema: [{ name: "a.b", physical_type: "int64", logical_type: "int64", nullable: true }],
    row_groups: [{ num_rows: 1, total_byte_size: 1, total_compressed_size: 1, file_offset: 4, columns: [{ name: "a.b", physical_type: "int64", logical_type: "int64", codec: "SNAPPY", num_values: 1, null_count: 0, total_compressed_size: 1, total_uncompressed_size: 1 }] }],
  };
  const [n] = buildSchemaTree(f);
  assert.equal(n.name, "a.b");
  assert.equal(n.children.length, 0);
});

test("describe aggregates nulls across row groups; null % only for flat columns", () => {
  const cols = Object.fromEntries(describeColumns(footer).map((c) => [c.name, c]));
  assert.equal(cols.name.nulls, 429); // ceil(3000/7) rows have a null name
  assert.ok(Math.abs(cols.name.nullPct - 14.3) < 0.1);
  assert.equal(cols.id.nulls, 0);
  assert.equal(cols.tags.nullPct, null);
  assert.equal(cols.id.hasStats, true);
  assert.equal(cols.id.min, undefined, "min/max values appear only when the engine supplies them");
});

test("describe combines min/max values when supplied", () => {
  const f = clone();
  f.row_groups[0].columns[0].min = 0; f.row_groups[0].columns[0].max = 1499;
  f.row_groups[1].columns[0].min = 1500; f.row_groups[1].columns[0].max = 2999;
  const id = describeColumns(f).find((c) => c.name === "id");
  assert.equal(id.min, 0);
  assert.equal(id.max, 2999);
});

test("validate passes a healthy file", () => {
  const v = validateFooter(footer, fileSize);
  assert.equal(v.verdict, "pass", JSON.stringify(v.checks.filter((c) => c.status !== "pass")));
  assert.equal(v.failed, 0);
});

test("validate fails when row counts disagree", () => {
  const f = clone(); f.num_rows += 1;
  const v = validateFooter(f, fileSize);
  assert.equal(v.verdict, "fail");
  assert.equal(v.checks.find((c) => c.id === "rows").status, "fail");
});

test("validate fails on mismatched columns, impossible nulls and out-of-file row groups", () => {
  let f = clone(); f.row_groups[1].columns.pop();
  assert.equal(validateFooter(f, fileSize).checks.find((c) => c.id === "columns").status, "fail");
  f = clone(); f.row_groups[0].columns[0].null_count = 1e9;
  assert.equal(validateFooter(f, fileSize).checks.find((c) => c.id === "nulls").status, "fail");
  f = clone();
  assert.equal(validateFooter(f, 1000).checks.find((c) => c.id === "bounds").status, "fail");
});

test("validate warns, not fails, on a codec Rugo can't read", () => {
  const f = clone(); for (const rg of f.row_groups) for (const c of rg.columns) c.codec = "BROTLI";
  assert.deepEqual(unsupportedCodecs(f), ["BROTLI"]);
  const v = validateFooter(f, fileSize);
  assert.equal(v.verdict, "pass-with-warnings");
});

test("validate copes with a file with no row groups", () => {
  const f = { num_rows: 0, num_row_groups: 0, schema: [], row_groups: [] };
  assert.equal(validateFooter(f, 12).verdict, "pass");
  assert.deepEqual(leafColumns(f), []);
});

test("validateFailure marks the failing stage", () => {
  assert.equal(validateFailure({ code: "NOT_PARQUET", message: "x" }).checks[0].status, "fail");
  const c = validateFailure({ code: "CORRUPT", message: "x" });
  assert.deepEqual(c.checks.map((x) => x.status), ["pass", "fail"]);
});

test("fmtBytes", () => {
  assert.equal(fmtBytes(0), "0 B");
  assert.equal(fmtBytes(1500), "1.50 KB");
  assert.equal(fmtBytes(1_259_784_098), "1.26 GB");
});

test("classifyError maps WASM / fetch failures to codes", async () => {
  const head = (bytes) => ({ size: 100, read: async () => new Uint8Array(bytes) });
  const code = async (e, src) => (await classifyError(e, src)).code;
  assert.equal(await code(new Error("not a parquet file (no PAR1 trailer)"), head([1, 2, 3, 4])), "NOT_PARQUET");
  assert.equal(await code(new Error("not a parquet file (no PAR1 trailer)"), head([0x50, 0x41, 0x52, 0x31])), "TRUNCATED");
  assert.equal(await code(new Error("file too small to be parquet"), { size: 0 }), "EMPTY");
  assert.equal(await code(new Error("file too small to be parquet"), { size: 5 }), "NOT_PARQUET");
  assert.equal(await code(new Error("footer length invalid")), "CORRUPT");
  assert.equal(await code(new Error("rugo: EOF")), "CORRUPT");
  assert.equal(await code(new Error("rugo: unsupported compression codec BROTLI")), "UNSUPPORTED_CODEC");
  assert.equal(await code(new Error("u: server ignored Range (HTTP 200)")), "RANGE_UNSUPPORTED");
  assert.equal(await code(new Error("u: server ignored Range (HTTP 404)")), "HTTP");
  assert.equal(await code(new TypeError("Failed to fetch")), "NETWORK");
});
