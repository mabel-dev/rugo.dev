// Rugo Parquet viewer UI. mountViewer(root, options) renders the whole viewer
// into `root`; it has no dependency on the surrounding page, so the same module
// serves rugo.dev and a VSCode webview (see README.md).
//
//   mountViewer(root, {
//     engine,          // optional: a ready engine (see engine.js)
//     wasmBase,        // otherwise: URL of the folder holding rugo_footer.mjs
//     initialUrl,      // optional: open this URL straight away
//     initialFile,     // optional: open this File/Blob straight away
//   })  ->  { openFile(file), openUrl(url), destroy() }
//
// File contents are only ever sliced by byte range and handed to the local
// WebAssembly module. Every piece of file-derived text is inserted with
// textContent, never as HTML.

import { loadEngine, classifyError, ViewerError } from "./engine.js";
import {
  fmtBytes, fmtInt, buildInfo, rowGroupTable, buildSchemaTree, countNodes,
  describeColumns, validateFooter, validateFailure, unsupportedCodecs,
} from "./viewer-core.js";

const TABS = [
  ["info", "Info"],
  ["schema", "Schema"],
  ["preview", "Preview"],
  ["describe", "Describe"],
  ["validate", "Validate"],
];

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const ERROR_TITLES = {
  NOT_PARQUET: "Not a Parquet file",
  EMPTY: "Empty file",
  TRUNCATED: "Truncated file",
  CORRUPT: "Corrupt file",
  UNSUPPORTED_CODEC: "Unsupported compression",
  NETWORK: "Couldn't reach that URL",
  RANGE_UNSUPPORTED: "Server doesn't support range requests",
  HTTP: "Server error",
  ENGINE_LOAD: "Engine failed to load",
  UNKNOWN: "Couldn't open this file",
};

export function mountViewer(root, options = {}) {
  let engine = options.engine ?? null;
  let enginePromise = null;
  let state = null; // { source, footer, name, size, tab }
  let loadToken = 0;
  let previewToken = 0;

  root.classList.add("rv");
  const getEngine = () => {
    if (engine) return Promise.resolve(engine);
    return (enginePromise ??= loadEngine({ wasmBase: options.wasmBase }).then((e) => (engine = e)));
  };
  // Start fetching the engine while the user picks a file.
  getEngine().catch(() => { enginePromise = null; });

  // ---- landing ---------------------------------------------------------------

  const fileInput = h("input", {
    type: "file", class: "rv-hidden", "aria-label": "Choose a Parquet file",
    onchange: (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) openFile(f); },
  });
  const urlInput = h("input", {
    type: "url", class: "rv-url", placeholder: "https://example.com/data.parquet", "aria-label": "Parquet file URL",
  });
  const drop = h("div", {
    class: "rv-drop", role: "button", tabindex: "0",
    onclick: () => fileInput.click(),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } },
  },
    h("div", { class: "rv-drop-title", text: "Drop a Parquet file here" }),
    h("div", { class: "rv-drop-sub", text: "or click to choose one" }),
  );
  const landing = h("div", { class: "rv-landing" },
    drop, fileInput,
    h("form", {
      class: "rv-urlform",
      onsubmit: (e) => { e.preventDefault(); if (urlInput.value.trim()) openUrl(urlInput.value.trim()); },
    },
      h("label", { class: "rv-urllabel" }, "Or open a URL ", h("span", { class: "rv-faint", text: "(server must allow CORS and range requests)" })),
      h("div", { class: "rv-urlrow" }, urlInput, h("button", { type: "submit", class: "rv-btn", text: "Open" })),
    ),
  );

  const status = h("div", { class: "rv-status", role: "status", "aria-live": "polite" });
  const stage = h("div", { class: "rv-stage" });
  root.append(landing, status, stage);

  // Drag and drop anywhere in the viewer.
  const onDragOver = (e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); root.classList.add("rv-dragging"); } };
  const onDragLeave = (e) => { if (e.target === root || !root.contains(e.relatedTarget)) root.classList.remove("rv-dragging"); };
  const onDrop = (e) => {
    root.classList.remove("rv-dragging");
    const f = e.dataTransfer?.files?.[0];
    if (!f) return;
    e.preventDefault();
    openFile(f);
  };
  root.addEventListener("dragover", onDragOver);
  root.addEventListener("dragleave", onDragLeave);
  root.addEventListener("drop", onDrop);

  // ---- loading ----------------------------------------------------------------

  function setBusy(msg) {
    status.textContent = msg ?? "";
    root.classList.toggle("rv-busy", !!msg);
  }

  async function open(describe, makeSource) {
    const token = ++loadToken;
    previewToken++;
    stage.replaceChildren();
    state = null;
    setBusy(`Reading ${describe}…`);
    let source = null;
    try {
      const eng = await getEngine();
      source = await makeSource(eng);
      const footer = await eng.readFooter(source);
      if (token !== loadToken) return;
      state = { source, footer, name: describe, size: source.size, tab: "info", engine: eng };
      setBusy("");
      landing.hidden = true;
      renderLoaded();
    } catch (err) {
      if (token !== loadToken) return;
      const verr = err instanceof ViewerError ? err : await classifyError(err, source);
      setBusy("");
      landing.hidden = false;
      renderError(verr);
    }
  }

  function openFile(file) {
    return open(file.name || "file", async (eng) => eng.openFile(file));
  }
  function openUrl(url) {
    urlInput.value = url;
    let label = url;
    try { label = new URL(url).pathname.split("/").pop() || url; } catch (_) { /* leave as typed */ }
    return open(label, (eng) => eng.openUrl(url));
  }

  // ---- errors -----------------------------------------------------------------

  function renderError(err) {
    const result = validateFailure(err);
    const fileProblem = !["NETWORK", "ENGINE_LOAD", "HTTP", "RANGE_UNSUPPORTED"].includes(err.code);
    stage.replaceChildren(...[
      h("div", { class: "rv-error", role: "alert" },
        h("div", { class: "rv-error-title", text: ERROR_TITLES[err.code] ?? ERROR_TITLES.UNKNOWN }),
        h("p", { text: err.message }),
        err.detail && err.detail !== err.message ? h("p", { class: "rv-faint rv-mono", text: err.detail }) : null,
      ),
      fileProblem ? renderChecks(result, "Validation") : null,
    ].filter(Boolean));
  }

  // ---- loaded state -------------------------------------------------------------

  const panels = {};

  function renderLoaded() {
    const { name, size, footer } = state;
    const tablist = h("div", { class: "rv-tabs", role: "tablist", "aria-label": "Views" });
    TABS.forEach(([id, label]) => {
      tablist.append(h("button", {
        class: "rv-tab", role: "tab", id: `rv-tab-${id}`, "aria-controls": `rv-panel-${id}`,
        "aria-selected": id === state.tab ? "true" : "false", tabindex: id === state.tab ? "0" : "-1",
        text: label, onclick: () => selectTab(id),
        onkeydown: (e) => {
          const i = TABS.findIndex(([t]) => t === id);
          const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
          if (next != null) { e.preventDefault(); selectTab(TABS[(next + TABS.length) % TABS.length][0], true); }
        },
      }));
    });
    for (const [id] of TABS) {
      panels[id] = h("div", { class: "rv-panel", role: "tabpanel", id: `rv-panel-${id}`, "aria-labelledby": `rv-tab-${id}`, hidden: id !== state.tab });
    }
    stage.replaceChildren(...[
      h("div", { class: "rv-bar" },
        h("div", { class: "rv-file" },
          h("span", { class: "rv-file-name", text: name }),
          h("span", { class: "rv-faint", text: ` · ${fmtBytes(size)} · ${fmtInt(footer.num_rows)} rows` }),
        ),
        h("button", { class: "rv-btn rv-btn-ghost", text: "Open another file", onclick: reset }),
      ),
      codecNote(),
      tablist,
      ...TABS.map(([id]) => panels[id]),
    ].filter(Boolean));
    renderPanel(state.tab);
  }

  // A file can be perfectly valid Parquet and still use a codec Rugo can't decompress.
  function codecNote() {
    const bad = unsupportedCodecs(state.footer);
    if (!bad.length) return null;
    return h("div", { class: "rv-note rv-note-warn" },
      h("div", { class: "rv-note-title", text: `${bad.join(", ")} compression isn't supported` }),
      h("p", { text: "This is valid Parquet, but Rugo can't decompress that codec yet. Info, Schema, Describe and Validate still work because they only use the footer; reading row data won't." }));
  }

  function reset() {
    loadToken++;
    previewToken++;
    state = null;
    stage.replaceChildren();
    landing.hidden = false;
    setBusy("");
  }

  function selectTab(id, focus) {
    state.tab = id;
    for (const [t] of TABS) {
      const btn = stage.querySelector(`#rv-tab-${t}`);
      btn.setAttribute("aria-selected", String(t === id));
      btn.tabIndex = t === id ? 0 : -1;
      panels[t].hidden = t !== id;
      if (focus && t === id) btn.focus();
    }
    renderPanel(id);
  }

  function renderPanel(id) {
    const panel = panels[id];
    if (panel.dataset.ready) return; // each view is built once per file
    panel.dataset.ready = "1";
    ({ info: renderInfo, schema: renderSchema, preview: renderPreview, describe: renderDescribe, validate: renderValidate })[id](panel);
  }

  // info
  function renderInfo(panel) {
    const { footer, size } = state;
    const dl = h("dl", { class: "rv-dl" });
    for (const [k, v] of buildInfo(footer, size)) dl.append(h("dt", { text: k }), h("dd", { text: v }));
    const groups = rowGroupTable(footer);
    const LIMIT = 100;
    const tbody = h("tbody");
    const fill = (n) => {
      tbody.replaceChildren(...groups.slice(0, n).map((g) => h("tr", {},
        h("td", { class: "rv-num", text: g.index }),
        h("td", { class: "rv-num", text: fmtInt(g.rows) }),
        h("td", { class: "rv-num", text: fmtBytes(g.compressed) }),
        h("td", { class: "rv-num", text: fmtBytes(g.uncompressed) }),
        h("td", { class: "rv-num", text: fmtInt(g.offset) }),
      )));
    };
    fill(LIMIT);
    const more = groups.length > LIMIT
      ? h("button", { class: "rv-btn rv-btn-ghost", text: `Show all ${fmtInt(groups.length)} row groups`, onclick: (e) => { fill(groups.length); e.target.remove(); } })
      : null;
    panel.append(...[
      dl,
      groups.length ? h("h3", { class: "rv-h3", text: "Row groups" }) : null,
      groups.length ? h("div", { class: "rv-tablewrap" }, h("table", { class: "rv-table" },
        h("thead", {}, h("tr", {}, ...["#", "Rows", "Compressed", "Uncompressed", "Offset"].map((t) => h("th", { class: "rv-num", text: t })))),
        tbody)) : null,
      more,
    ].filter(Boolean));
  }

  // schema
  function renderSchema(panel) {
    const roots = buildSchemaTree(state.footer);
    const total = countNodes(roots);
    const node = (n) => {
      const label = h("span", { class: "rv-node" },
        h("span", { class: `rv-kind rv-kind-${n.kind}`, text: n.kind === "leaf" ? "" : n.kind }),
        h("span", { class: "rv-node-name", text: n.name }),
        n.kind === "leaf" || n.kind === "list" || n.kind === "map" ? h("span", { class: "rv-node-type", text: n.type }) : null,
        n.nullable === false ? h("span", { class: "rv-faint", text: "required" }) : null,
      );
      if (!n.children.length) return h("li", { class: "rv-leaf" }, label);
      return h("li", {}, h("details", { open: true }, h("summary", {}, label), h("ul", {}, n.children.map(node))));
    };
    panel.append(
      h("div", { class: "rv-toolbar" },
        h("span", { class: "rv-faint", text: `${fmtInt(roots.length)} fields · ${fmtInt(total)} nodes` }),
        h("span", {},
          h("button", { class: "rv-btn rv-btn-ghost", text: "Expand all", onclick: () => panel.querySelectorAll("details").forEach((d) => (d.open = true)) }),
          h("button", { class: "rv-btn rv-btn-ghost", text: "Collapse all", onclick: () => panel.querySelectorAll("details").forEach((d) => (d.open = false)) }),
        ),
      ),
      h("ul", { class: "rv-tree" }, roots.map(node)),
    );
  }

  // preview: one row group at a time
  function renderPreview(panel) {
    const { footer, engine: eng } = state;
    const bad = unsupportedCodecs(footer);
    if (bad.length) {
      panel.append(h("div", { class: "rv-error", role: "alert" },
        h("div", { class: "rv-error-title", text: ERROR_TITLES.UNSUPPORTED_CODEC }),
        h("p", { text: `Rugo can't decompress ${bad.join(", ")}, so rows can't be previewed.` })));
      return;
    }
    if (!eng.readRowGroup) {
      panel.append(h("div", { class: "rv-note" },
        h("div", { class: "rv-note-title", text: "Row preview isn't in this build yet" }),
        h("p", { text: "Previewing rows needs Rugo's WebAssembly page decoder, which the current build doesn't include. Info, Schema, Describe and Validate work now, and they read nothing but the file's footer." }),
      ));
      return;
    }
    const groups = footer.row_groups ?? [];
    const sel = h("select", { class: "rv-select", "aria-label": "Row group" },
      groups.map((g, i) => h("option", { value: String(i), text: `Row group ${i} · ${fmtInt(g.num_rows)} rows` })));
    const limit = h("input", { class: "rv-limit", type: "number", min: "1", max: "1000", value: "50", "aria-label": "Rows to show" });
    const out = h("div", { class: "rv-tablewrap" });
    const load = async () => {
      const token = ++previewToken;
      out.replaceChildren(h("p", { class: "rv-faint", text: "Reading row group…" }));
      try {
        const res = await eng.readRowGroup(state.source, footer, Number(sel.value), { limit: Math.max(1, Math.min(1000, Number(limit.value) || 50)) });
        if (token !== previewToken) return;
        out.replaceChildren(h("table", { class: "rv-table" },
          h("thead", {}, h("tr", {}, res.columns.map((c) => h("th", { text: c })))),
          h("tbody", {}, res.rows.map((r) => h("tr", {}, r.map((v) => v == null ? h("td", { class: "rv-null", text: "null" }) : h("td", { text: typeof v === "bigint" ? v.toString() : typeof v === "object" ? JSON.stringify(v, (_, x) => (typeof x === "bigint" ? x.toString() : x)) : String(v) })))))));
      } catch (err) {
        if (token !== previewToken) return;
        const verr = err instanceof ViewerError ? err : await classifyError(err, state.source);
        out.replaceChildren(h("div", { class: "rv-error", role: "alert" }, h("div", { class: "rv-error-title", text: ERROR_TITLES[verr.code] ?? ERROR_TITLES.UNKNOWN }), h("p", { text: verr.message })));
      }
    };
    sel.addEventListener("change", load);
    limit.addEventListener("change", load);
    panel.append(h("div", { class: "rv-toolbar" }, h("label", {}, sel), h("label", { class: "rv-faint" }, "Rows ", limit)), out);
    if (groups.length) load();
  }

  // describe
  function renderDescribe(panel) {
    const cols = describeColumns(state.footer);
    const showMinMax = cols.some((c) => c.min !== undefined || c.max !== undefined);
    const tbody = h("tbody");
    const fmtV = (v) => (v === undefined ? "–" : typeof v === "bigint" ? v.toString() : String(v));
    const fill = (q) => {
      const rows = cols.filter((c) => c.name.toLowerCase().includes(q));
      tbody.replaceChildren(...rows.map((c) => h("tr", {},
        h("td", { class: "rv-mono", text: c.name }),
        h("td", { text: c.type }),
        h("td", { text: c.codecs }),
        h("td", { class: "rv-num", text: fmtInt(c.nulls) }),
        h("td", { class: "rv-num", text: c.nullPct == null ? "–" : `${c.nullPct < 0.01 && c.nulls ? "<0.01" : c.nullPct.toFixed(c.nullPct < 10 ? 2 : 1)}%` }),
        h("td", { class: "rv-num", text: c.distinct == null ? "–" : fmtInt(c.distinct) }),
        showMinMax ? h("td", { class: "rv-mono", text: fmtV(c.min) }) : null,
        showMinMax ? h("td", { class: "rv-mono", text: fmtV(c.max) }) : null,
        h("td", { class: "rv-stat", title: c.hasStats ? "Min/max statistics are stored in the file" : "No min/max statistics stored", text: c.hasStats ? "✓" : "–" }),
        h("td", { class: "rv-num", text: fmtBytes(c.compressed) }),
      )));
      count.textContent = `${fmtInt(rows.length)} of ${fmtInt(cols.length)} columns`;
    };
    const count = h("span", { class: "rv-faint" });
    const filter = h("input", { class: "rv-filter", type: "search", placeholder: "Filter columns…", "aria-label": "Filter columns", oninput: (e) => fill(e.target.value.toLowerCase()) });
    const heads = ["Column", "Type", "Compression", "Nulls", "Null %", "Distinct", ...(showMinMax ? ["Min", "Max"] : []), "Stats", "Size"];
    panel.append(
      h("div", { class: "rv-toolbar" }, filter, count),
      h("div", { class: "rv-tablewrap" }, h("table", { class: "rv-table" },
        h("thead", {}, h("tr", {}, heads.map((t) => h("th", { class: ["Nulls", "Null %", "Distinct", "Size"].includes(t) ? "rv-num" : "", text: t })))),
        tbody)),
    );
    fill("");
  }

  // validate
  function renderValidate(panel) {
    panel.append(renderChecks(validateFooter(state.footer, state.size), "Validation"));
  }

  function renderChecks(result, title) {
    const verdictText = { pass: "Pass", fail: "Fail", "pass-with-warnings": "Pass with warnings" }[result.verdict];
    return h("div", { class: "rv-validate" },
      h("div", { class: `rv-verdict rv-verdict-${result.verdict}` },
        h("span", { class: "rv-verdict-label", text: verdictText }),
        h("span", { class: "rv-faint", text: ` ${title} · ${result.checks.length} checks${result.failed ? ` · ${result.failed} failed` : ""}${result.warned ? ` · ${result.warned} warning${result.warned > 1 ? "s" : ""}` : ""}` }),
      ),
      h("ul", { class: "rv-checks" }, result.checks.map((c) => h("li", { class: `rv-check rv-check-${c.status}` },
        h("span", { class: "rv-check-icon", "aria-label": c.status, text: { pass: "✓", fail: "✗", warn: "!", skip: "–" }[c.status] }),
        h("div", {}, h("div", { class: "rv-check-label", text: c.label }), h("div", { class: "rv-faint", text: c.detail })),
      ))),
    );
  }

  if (options.initialFile) openFile(options.initialFile);
  else if (options.initialUrl) openUrl(options.initialUrl);

  return {
    openFile, openUrl,
    destroy() {
      root.removeEventListener("dragover", onDragOver);
      root.removeEventListener("dragleave", onDragLeave);
      root.removeEventListener("drop", onDrop);
      root.replaceChildren();
      root.classList.remove("rv");
    },
  };
}
