// Pure data layer for the Rugo viewer: no DOM, no WASM, no network.
// Takes the footer object that Rugo's WASM build returns and derives what each
// view shows. Runs unchanged in a browser, a VSCode webview or Node (tests).

export const SUPPORTED_CODECS = ["UNCOMPRESSED", "SNAPPY", "GZIP", "ZSTD", "LZ4_RAW"];

const NESTED = new Set(["list", "struct", "map"]);

export function fmtBytes(n) {
  if (n == null || Number.isNaN(n)) return "–";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  let v = Number(n);
  while (v >= 1000 && i < units.length - 1) { v /= 1000; i++; }
  return `${i === 0 ? v : v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2)} ${units[i]}`;
}

export function fmtInt(n) {
  return n == null ? "–" : Number(n).toLocaleString("en-US");
}

// Days since 1970-01-01 -> "YYYY-MM-DD"; epoch milliseconds -> "YYYY-MM-DD HH:MM:SS.mmm" (UTC).
export function fmtDays(d) {
  try { return new Date(Number(d) * 86400000).toISOString().slice(0, 10); } catch (_) { return String(d); }
}
export function fmtTimestampMs(ms) {
  try { return new Date(Number(ms)).toISOString().replace("T", " ").replace("Z", ""); } catch (_) { return String(ms); }
}

// A cell value as text for the preview table. BigInt, bytes and nested values
// are rendered; null / undefined stay null so the table can show them as null.
export function displayValue(v) {
  if (v == null) return null;
  const plain = (x) => {
    if (typeof x === "bigint") return x.toString();
    if (x instanceof Uint8Array) return "0x" + [...x.subarray(0, 32)].map((b) => b.toString(16).padStart(2, "0")).join("") + (x.length > 32 ? `… (${x.length} bytes)` : "");
    if (x instanceof Date) return x.toISOString();
    return x;
  };
  if (typeof v === "object" && !(v instanceof Uint8Array) && !(v instanceof Date)) {
    return JSON.stringify(v, (_, x) => plain(x));
  }
  return String(plain(v));
}

const rowGroups = (f) => f.row_groups ?? [];

// Leaf columns, in file order. Nested fields appear as dotted paths ("addr.geo.lat").
export function leafColumns(footer) {
  const rg0 = rowGroups(footer)[0];
  return rg0 ? rg0.columns.map((c) => c.name) : (footer.schema ?? []).map((s) => s.name);
}

export function codecsOf(footer) {
  const counts = new Map();
  for (const rg of rowGroups(footer)) {
    for (const c of rg.columns) counts.set(c.codec, (counts.get(c.codec) ?? 0) + 1);
  }
  return counts;
}

export function unsupportedCodecs(footer) {
  return [...codecsOf(footer).keys()].filter((c) => !SUPPORTED_CODECS.includes(c));
}

// ---- info ------------------------------------------------------------------

export function buildInfo(footer, fileSize) {
  const rgs = rowGroups(footer);
  let comp = 0;
  let uncomp = 0;
  for (const rg of rgs) {
    for (const c of rg.columns) {
      comp += c.total_compressed_size ?? 0;
      uncomp += c.total_uncompressed_size ?? 0;
    }
  }
  const codecs = [...codecsOf(footer).keys()];
  const rows = [
    ["File size", fmtBytes(fileSize)],
    ["Rows", fmtInt(footer.num_rows)],
    ["Columns", fmtInt(leafColumns(footer).length)],
    ["Row groups", fmtInt(footer.num_row_groups ?? rgs.length)],
  ];
  if (rgs.length) rows.push(["Rows per row group", fmtInt(Math.round(footer.num_rows / rgs.length))]);
  rows.push(["Compression", codecs.length ? codecs.join(", ") : "–"]);
  if (comp && uncomp) rows.push(["Data size", `${fmtBytes(comp)} compressed · ${fmtBytes(uncomp)} uncompressed (${(uncomp / comp).toFixed(1)}×)`]);
  if (footer.created_by) rows.push(["Created by", footer.created_by]);
  return rows;
}

export function rowGroupTable(footer) {
  return rowGroups(footer).map((rg, i) => ({
    index: i,
    rows: rg.num_rows,
    offset: rg.file_offset,
    compressed: rg.total_compressed_size,
    uncompressed: rg.total_byte_size,
  }));
}

// ---- schema ----------------------------------------------------------------

// Builds a tree from Rugo's top-level fields (list / struct / map are marked
// there) plus the dotted leaf-column paths. Parquet's list and map wrapper
// levels ("list.element", "key_value") are folded away.
export function buildSchemaTree(footer) {
  const top = footer.schema ?? [];
  const rg0 = rowGroups(footer)[0];
  const leaves = rg0 ? rg0.columns : [];
  const byName = new Map();
  const roots = top.map((f) => {
    const kind = NESTED.has(f.physical_type) ? f.physical_type : "leaf";
    const node = {
      name: f.name,
      path: f.name,
      kind,
      type: kind === "struct" ? "struct" : f.logical_type || f.physical_type,
      physical: f.physical_type,
      nullable: f.nullable !== false,
      children: [],
    };
    byName.set(f.name, node);
    return node;
  });

  const names = [...byName.keys()].sort((a, b) => b.length - a.length); // longest prefix wins
  for (const leaf of leaves) {
    const topName = names.find((n) => leaf.name === n || leaf.name.startsWith(n + "."));
    if (!topName || leaf.name === topName) {
      const node = byName.get(leaf.name);
      if (node) node.column = leaf.name;
      continue;
    }
    let parts = leaf.name.slice(topName.length + 1).split(".");
    let parent = byName.get(topName);
    if (parent.kind === "map" && /^(key_value|map)$/.test(parts[0]) && parts.length > 1) parts = parts.slice(1);
    if (parent.kind === "list") {
      if (/^(list|bag)$/.test(parts[0]) && parts.length > 1) parts = parts.slice(1);
      if (/^(element|item|array_element)$/.test(parts[0]) && parts.length > 1) parts = parts.slice(1);
    }
    parts.forEach((part, i) => {
      const last = i === parts.length - 1;
      let child = parent.children.find((c) => c.name === part);
      if (!child) {
        child = last
          ? { name: part, path: leaf.name, kind: "leaf", type: leaf.logical_type || leaf.physical_type, physical: leaf.physical_type, nullable: true, children: [], column: leaf.name }
          : { name: part, path: `${parent.path}.${part}`, kind: "struct", type: "struct", physical: "struct", nullable: true, children: [] };
        parent.children.push(child);
      }
      parent = child;
    });
  }
  return roots;
}

export function countNodes(nodes) {
  return nodes.reduce((n, x) => n + 1 + countNodes(x.children), 0);
}

// ---- describe --------------------------------------------------------------

function cmp(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

// One row per leaf column, aggregated over every row group from footer metadata
// alone. min / max appear when the engine supplies decoded values on the chunks;
// hasStats says whether the file carries them.
export function describeColumns(footer) {
  const out = new Map();
  for (const rg of rowGroups(footer)) {
    for (const c of rg.columns) {
      let d = out.get(c.name);
      if (!d) {
        d = {
          name: c.name, type: c.logical_type || c.physical_type, physical: c.physical_type,
          codecs: new Set(), values: 0, nulls: 0, compressed: 0, uncompressed: 0,
          hasMin: true, hasMax: true, min: undefined, max: undefined, minOk: true, maxOk: true,
          distinct: null, bloom: false, pageIndex: false,
        };
        out.set(c.name, d);
      }
      d.codecs.add(c.codec);
      d.values += c.num_values ?? 0;
      d.nulls += c.null_count > 0 ? c.null_count : 0;
      d.compressed += c.total_compressed_size ?? 0;
      d.uncompressed += c.total_uncompressed_size ?? 0;
      d.hasMin &&= !!c.has_min;
      d.hasMax &&= !!c.has_max;
      d.bloom ||= !!c.has_bloom_filter;
      d.pageIndex ||= !!c.has_page_index;
      if (c.distinct_count >= 0) d.distinct = Math.max(d.distinct ?? 0, c.distinct_count);
      if (c.min !== undefined && d.minOk) d.min = d.min === undefined || cmp(c.min, d.min) < 0 ? c.min : d.min;
      else if (c.has_min) d.minOk = c.min !== undefined && d.minOk;
      if (c.max !== undefined && d.maxOk) d.max = d.max === undefined || cmp(c.max, d.max) > 0 ? c.max : d.max;
      else if (c.has_max) d.maxOk = c.max !== undefined && d.maxOk;
    }
  }
  // Null % is only meaningful for flat columns: nested leaves hold one value per
  // element, not per row.
  const flat = new Set((footer.schema ?? []).filter((s) => !NESTED.has(s.physical_type)).map((s) => s.name));
  return [...out.values()].map((d) => ({
    ...d,
    codecs: [...d.codecs].join(", "),
    nullPct: flat.has(d.name) && d.values ? (d.nulls / d.values) * 100 : null,
    min: d.minOk ? d.min : undefined,
    max: d.maxOk ? d.max : undefined,
    hasStats: d.hasMin && d.hasMax,
  }));
}

// ---- validate --------------------------------------------------------------

const pass = (id, label, detail) => ({ id, label, status: "pass", detail });
const fail = (id, label, detail) => ({ id, label, status: "fail", detail });
const warn = (id, label, detail) => ({ id, label, status: "warn", detail });

// Metadata checks over the decoded footer. They don't decompress data pages,
// so they say nothing about page contents; the details name what each check covers.
export function validateFooter(footer, fileSize) {
  const rgs = rowGroups(footer);
  const checks = [];

  checks.push(pass("magic", "PAR1 magic and footer length", "The file ends with PAR1 and the footer fits inside it."));
  checks.push(pass("thrift", "Footer decodes", "The footer parsed as valid Parquet metadata."));

  const declared = footer.num_row_groups ?? rgs.length;
  checks.push(
    declared === rgs.length
      ? pass("rg-count", "Row group count", `${fmtInt(declared)} row groups declared and present.`)
      : fail("rg-count", "Row group count", `Footer declares ${declared} row groups but lists ${rgs.length}.`),
  );

  const sum = rgs.reduce((n, rg) => n + rg.num_rows, 0);
  checks.push(
    sum === footer.num_rows
      ? pass("rows", "Row counts add up", `Row groups total ${fmtInt(sum)} rows, matching the file's ${fmtInt(footer.num_rows)}.`)
      : fail("rows", "Row counts add up", `Row groups total ${fmtInt(sum)} rows but the file says ${fmtInt(footer.num_rows)}.`),
  );

  if (rgs.length) {
    const ref = rgs[0].columns.map((c) => c.name).join("\u0000");
    const bad = rgs.findIndex((rg) => rg.columns.map((c) => c.name).join("\u0000") !== ref);
    checks.push(
      bad < 0
        ? pass("columns", "Same columns in every row group", `${fmtInt(rgs[0].columns.length)} columns in each of ${fmtInt(rgs.length)} row groups.`)
        : fail("columns", "Same columns in every row group", `Row group ${bad} has different columns from row group 0.`),
    );
  }

  const topNames = new Set((footer.schema ?? []).map((s) => s.name));
  const leaves = rgs[0]?.columns ?? [];
  const orphan = leaves.find((c) => ![...topNames].some((n) => c.name === n || c.name.startsWith(n + ".")));
  const empty = [...topNames].find((n) => leaves.length && !leaves.some((c) => c.name === n || c.name.startsWith(n + ".")));
  checks.push(
    orphan
      ? fail("schema", "Schema matches columns", `Column "${orphan.name}" has no matching field in the schema.`)
      : empty
        ? fail("schema", "Schema matches columns", `Schema field "${empty}" has no stored column.`)
        : pass("schema", "Schema matches columns", `${fmtInt(topNames.size)} schema fields, all backed by stored columns.`),
  );

  // Flat columns store exactly one value per row (nulls included).
  const flat = new Set((footer.schema ?? []).filter((s) => !NESTED.has(s.physical_type)).map((s) => s.name));
  let mism = null;
  let nullBad = null;
  rgs.forEach((rg, i) => {
    for (const c of rg.columns) {
      if (!mism && flat.has(c.name) && c.num_values !== rg.num_rows) mism = `Row group ${i}, column "${c.name}": ${fmtInt(c.num_values)} values for ${fmtInt(rg.num_rows)} rows.`;
      if (!nullBad && (c.null_count > c.num_values)) nullBad = `Row group ${i}, column "${c.name}": ${fmtInt(c.null_count)} nulls out of ${fmtInt(c.num_values)} values.`;
    }
  });
  checks.push(mism ? fail("values", "Value counts match rows", mism) : pass("values", "Value counts match rows", "Every flat column holds one value per row."));
  checks.push(nullBad ? fail("nulls", "Null counts are possible", nullBad) : pass("nulls", "Null counts are possible", "No column reports more nulls than values."));

  let sizeBad = null;
  let prevEnd = 0;
  let order = null;
  rgs.forEach((rg, i) => {
    if (rg.total_compressed_size > 0 && rg.file_offset + rg.total_compressed_size > fileSize - 8 && !sizeBad) {
      sizeBad = `Row group ${i} runs to byte ${fmtInt(rg.file_offset + rg.total_compressed_size)}, past the data area of a ${fmtInt(fileSize)}-byte file.`;
    }
    if (rg.file_offset < prevEnd && !order) order = `Row group ${i} starts at byte ${fmtInt(rg.file_offset)}, inside the previous row group.`;
    prevEnd = rg.file_offset + (rg.total_compressed_size || 0);
  });
  checks.push(sizeBad ? fail("bounds", "Row groups lie inside the file", sizeBad) : pass("bounds", "Row groups lie inside the file", "Every row group's byte range fits within the file."));
  checks.push(order ? fail("order", "Row groups don't overlap", order) : pass("order", "Row groups don't overlap", "Row groups appear in file order without overlapping."));

  const codecs = [...codecsOf(footer).keys()];
  const unsupported = unsupportedCodecs(footer);
  checks.push(
    unsupported.length
      ? warn("codecs", "Compression readable by Rugo", `${unsupported.join(", ")} is valid Parquet, but Rugo can't decompress it yet.`)
      : pass("codecs", "Compression readable by Rugo", codecs.length ? `${codecs.join(", ")}.` : "No compressed data."),
  );

  return summarise(checks);
}

// What validate shows when the file couldn't be opened at all. `err.format` says
// which format's signature to check; with none, the format wasn't recognised.
const SIGNATURE = {
  parquet: ["PAR1 magic and footer length", "Footer decodes"],
  avro: ["Avro magic bytes", "Header and schema decode"],
  orc: ["ORC magic and postscript", "Footer decodes"],
};
export function validateFailure(err) {
  const [sigLabel, bodyLabel] = SIGNATURE[err.format] ?? ["Parquet, Avro or ORC signature", "Metadata decodes"];
  const signatureOk = err.code === "CORRUPT" || err.code === "UNSUPPORTED_CODEC"; // the file was recognised, the body wasn't readable
  const checks = [
    signatureOk ? pass("magic", sigLabel, "The file has the right signature.") : fail("magic", sigLabel, err.message),
    signatureOk
      ? fail("thrift", bodyLabel, err.message)
      : { id: "thrift", label: bodyLabel, status: "skip", detail: "Not run: the file couldn't be opened." },
  ];
  return summarise(checks);
}

function summarise(checks) {
  const failed = checks.filter((c) => c.status === "fail").length;
  const warned = checks.filter((c) => c.status === "warn").length;
  return {
    checks,
    failed,
    warned,
    verdict: failed ? "fail" : warned ? "pass-with-warnings" : "pass",
  };
}
