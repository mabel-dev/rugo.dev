// Parquet model: wraps the footer that Rugo's WASM build returns in the shape the
// UI renders, using the pure functions in viewer-core.js.
import {
  fmtBytes, fmtInt, buildInfo, rowGroupTable, buildSchemaTree, describeColumns,
  validateFooter, unsupportedCodecs, temporalFormatter,
} from "./viewer-core.js";

export async function openParquet(source, engine) {
  const footer = await engine.readFooter(source);
  const size = source.size;
  const groups = footer.row_groups ?? [];
  const bad = unsupportedCodecs(footer);

  let preview;
  if (bad.length) {
    preview = { kind: "error", code: "UNSUPPORTED_CODEC", title: "Unsupported compression", text: `Rugo can't decompress ${bad.join(", ")}, so rows can't be previewed.` };
  } else if (!engine.readRowGroup) {
    preview = {
      kind: "unavailable",
      title: "Row preview isn't in this build yet",
      text: "Previewing rows needs Rugo's WebAssembly page decoder, which the current build doesn't include. Info, Schema, Describe and Validate work now, and they read nothing but the file's footer.",
    };
  } else {
    preview = {
      kind: "rows",
      unitLabel: "Row group",
      count: () => groups.length,
      label: (i) => `Row group ${i} · ${fmtInt(groups[i].num_rows)} rows`,
      // The engine returns stored ints for dates, times and timestamps; render them by the column's type.
      read: async (i, limit) => {
        const res = await engine.readRowGroup(source, footer, i, { limit });
        const types = new Map(groups[i].columns.map((c) => [c.name, c.logical_type]));
        const fmts = res.columns.map((c) => temporalFormatter(types.get(c)));
        return { ...res, rows: res.rows.map((r) => r.map((v, j) => (v == null || !fmts[j] ? v : fmts[j](v)))) };
      },
    };
  }

  return {
    format: "parquet",
    label: "Parquet",
    size,
    tabs: ["info", "schema", "preview", "describe", "validate"],
    summary: () => `${fmtInt(footer.num_rows)} rows`,
    notice: bad.length
      ? { title: `${bad.join(", ")} compression isn't supported`, text: "This is valid Parquet, but Rugo can't decompress that codec yet. Info, Schema, Describe and Validate still work because they only use the footer; reading row data won't." }
      : null,
    info: () => buildInfo(footer, size),
    units: () => ({
      title: "Row groups",
      head: ["#", "Rows", "Compressed", "Uncompressed", "Offset"],
      rows: rowGroupTable(footer).map((g) => [g.index, fmtInt(g.rows), fmtBytes(g.compressed), fmtBytes(g.uncompressed), fmtInt(g.offset)]),
    }),
    schema: () => buildSchemaTree(footer),
    describe() {
      const cols = describeColumns(footer);
      const minMax = cols.some((c) => c.min !== undefined || c.max !== undefined);
      const v = (x) => (x === undefined ? "–" : typeof x === "bigint" ? x.toString() : String(x));
      const head = [
        { t: "Column" }, { t: "Type" }, { t: "Compression" }, { t: "Nulls", num: true }, { t: "Null %", num: true }, { t: "Distinct", num: true },
        ...(minMax ? [{ t: "Min" }, { t: "Max" }] : []), { t: "Stats" }, { t: "Size", num: true },
      ];
      const rows = cols.map((c) => ({
        key: c.name.toLowerCase(),
        cells: [
          { t: c.name, mono: true }, { t: c.type }, { t: c.codecs },
          { t: fmtInt(c.nulls), num: true },
          { t: c.nullPct == null ? "–" : `${c.nullPct < 0.01 && c.nulls ? "<0.01" : c.nullPct.toFixed(c.nullPct < 10 ? 2 : 1)}%`, num: true },
          { t: c.distinct == null ? "–" : fmtInt(c.distinct), num: true },
          ...(minMax ? [{ t: v(c.min), mono: true }, { t: v(c.max), mono: true }] : []),
          { t: c.hasStats ? "✓" : "–", cls: "rv-stat", title: c.hasStats ? "Min/max statistics are stored in the file" : "No min/max statistics stored" },
          { t: fmtBytes(c.compressed), num: true },
        ],
      }));
      return { head, rows, count: rows.length };
    },
    validate: () => validateFooter(footer, size),
    preview,
  };
}
