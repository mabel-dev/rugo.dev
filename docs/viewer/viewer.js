// Rugo data-file viewer UI (Parquet, Avro, ORC). mountViewer(root, options) renders
// the whole viewer into `root`; it has no dependency on the surrounding page, so the
// same module serves rugo.dev and a VSCode webview (see README.md).
//
//   mountViewer(root, {
//     engine,          // optional: a ready Parquet engine (see engine.js)
//     wasmBase,        // otherwise: URL of the folder holding rugo_footer.mjs
//     initialUrl,      // optional: open this URL straight away
//     initialFile,     // optional: open this File/Blob straight away
//   })  ->  { openFile(file), openUrl(url), destroy() }
//
// File contents are only ever sliced by byte range. Every piece of file-derived text
// is inserted with textContent, never as HTML.

import { loadEngine, classifyError } from "./engine.js";
import { ViewerError } from "./errors.js";
import { fileSource, urlSource } from "./sources.js";
import { openModel } from "./formats.js";
import { fmtBytes, fmtInt, countNodes, displayValue, validateFailure } from "./viewer-core.js";

const TAB_LABELS = { info: "Info", schema: "Schema", preview: "Preview", describe: "Describe", validate: "Validate" };

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
  UNKNOWN_FORMAT: "Not a Parquet, Avro or ORC file",
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
// Errors about getting the bytes, not about the file's contents: no validation to show.
const TRANSPORT_ERRORS = new Set(["NETWORK", "ENGINE_LOAD", "HTTP", "RANGE_UNSUPPORTED"]);

export function mountViewer(root, options = {}) {
  let engine = options.engine ?? null;
  let enginePromise = null;
  let state = null; // { model, name, tab, unsubscribe }
  let loadToken = 0;
  let previewToken = 0;

  root.classList.add("rv");
  // The WebAssembly engine is only needed for Parquet; start fetching it while the
  // user picks a file, and ignore a failure until a Parquet file actually needs it.
  const getEngine = () => {
    if (engine) return Promise.resolve(engine);
    return (enginePromise ??= loadEngine({ wasmBase: options.wasmBase }).then((e) => (engine = e), (err) => { enginePromise = null; throw err; }));
  };
  getEngine().catch(() => {});

  // ---- landing ---------------------------------------------------------------

  const fileInput = h("input", {
    type: "file", class: "rv-hidden", "aria-label": "Choose a Parquet, Avro or ORC file",
    onchange: (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) openFile(f); },
  });
  const urlInput = h("input", {
    type: "url", class: "rv-url", placeholder: "https://example.com/data.parquet", "aria-label": "File URL",
  });
  const drop = h("div", {
    class: "rv-drop", role: "button", tabindex: "0",
    onclick: () => fileInput.click(),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } },
  },
    h("div", { class: "rv-drop-title", text: "Drop a Parquet, Avro or ORC file here" }),
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

  function dropState() {
    if (state) { state.model.scan?.cancel?.(); state.unsubscribe?.(); }
    state = null;
  }

  async function open(describe, makeSource) {
    const token = ++loadToken;
    previewToken++;
    stage.replaceChildren();
    dropState();
    setBusy(`Reading ${describe}…`);
    try {
      const source = await makeSource();
      const model = await openModel(source, getEngine);
      if (token !== loadToken) { model.scan?.cancel?.(); return; }
      state = { model, name: describe, tab: "info", unsubscribe: null };
      if (model.onChange) state.unsubscribe = model.onChange(onModelChange);
      setBusy("");
      landing.hidden = true;
      renderLoaded();
    } catch (err) {
      if (token !== loadToken) return;
      const verr = err instanceof ViewerError ? err : await classifyError(err, null);
      setBusy("");
      landing.hidden = false;
      renderError(verr);
    }
  }

  function openFile(file) {
    return open(file.name || "file", async () => fileSource(file));
  }
  function openUrl(url) {
    urlInput.value = url;
    let label = url;
    try { label = new URL(url).pathname.split("/").pop() || url; } catch (_) { /* leave as typed */ }
    return open(label, () => urlSource(url));
  }

  // ---- errors -----------------------------------------------------------------

  function renderError(err) {
    stage.replaceChildren(...[
      h("div", { class: "rv-error", role: "alert" },
        h("div", { class: "rv-error-title", text: ERROR_TITLES[err.code] ?? ERROR_TITLES.UNKNOWN }),
        h("p", { text: err.message }),
        err.detail && err.detail !== err.message ? h("p", { class: "rv-faint rv-mono", text: err.detail }) : null,
      ),
      TRANSPORT_ERRORS.has(err.code) ? null : renderChecks(validateFailure(err), "Validation"),
    ].filter(Boolean));
  }

  // ---- loaded state -------------------------------------------------------------

  const panels = {};
  let summaryEl = null;

  function renderLoaded() {
    const { model, name } = state;
    const tablist = h("div", { class: "rv-tabs", role: "tablist", "aria-label": "Views" });
    model.tabs.forEach((id) => {
      tablist.append(h("button", {
        class: "rv-tab", role: "tab", id: `rv-tab-${id}`, "aria-controls": `rv-panel-${id}`,
        "aria-selected": id === state.tab ? "true" : "false", tabindex: id === state.tab ? "0" : "-1",
        text: TAB_LABELS[id], onclick: () => selectTab(id),
        onkeydown: (e) => {
          const i = model.tabs.indexOf(id);
          const next = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
          if (next != null) { e.preventDefault(); selectTab(model.tabs[(next + model.tabs.length) % model.tabs.length], true); }
        },
      }));
    });
    for (const id of model.tabs) {
      panels[id] = h("div", { class: "rv-panel", role: "tabpanel", id: `rv-panel-${id}`, "aria-labelledby": `rv-tab-${id}`, hidden: id !== state.tab });
    }
    summaryEl = h("span", { class: "rv-faint" });
    stage.replaceChildren(...[
      h("div", { class: "rv-bar" },
        h("div", { class: "rv-file" },
          h("span", { class: "rv-file-name", text: name }),
          h("span", { class: "rv-badge", text: model.label }),
          h("span", { class: "rv-faint", text: ` ${fmtBytes(model.size)} · ` }),
          summaryEl,
        ),
        h("button", { class: "rv-btn rv-btn-ghost", text: "Open another file", onclick: reset }),
      ),
      model.notice ? h("div", { class: "rv-note rv-note-warn" }, h("div", { class: "rv-note-title", text: model.notice.title }), h("p", { text: model.notice.text })) : null,
      tablist,
      ...model.tabs.map((id) => panels[id]),
    ].filter(Boolean));
    updateSummary();
    renderPanel(state.tab);
  }

  const updateSummary = () => { if (summaryEl && state) summaryEl.textContent = state.model.summary(); };

  // Avro scans report progress and completion; refresh what depends on them.
  function onModelChange(kind) {
    if (!state) return;
    updateSummary();
    for (const id of ["info", "validate", ...(kind === "done" ? ["preview"] : [])]) {
      const p = panels[id];
      if (!p) continue;
      p.replaceChildren();
      delete p.dataset.ready;
      if (id === state.tab) renderPanel(id);
    }
  }

  function reset() {
    loadToken++;
    previewToken++;
    dropState();
    stage.replaceChildren();
    landing.hidden = false;
    setBusy("");
  }

  function selectTab(id, focus) {
    state.tab = id;
    for (const t of state.model.tabs) {
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

  // A running or not-yet-run block scan (Avro).
  function scanControl() {
    const sc = state.model.scan;
    if (!sc || sc.state === "done") return null;
    if (sc.state === "running") {
      return h("div", { class: "rv-scan" },
        h("progress", { max: "1", value: String(sc.progress), "aria-label": "Scan progress" }),
        h("span", { class: "rv-faint", text: ` Reading block headers… ${Math.round(sc.progress * 100)}%` }),
        h("button", { class: "rv-btn rv-btn-ghost", text: "Cancel", onclick: () => sc.cancel() }),
      );
    }
    if (sc.state === "error") {
      return h("div", { class: "rv-note" }, h("p", { text: `The scan stopped: ${sc.error?.message ?? sc.error}` }));
    }
    return h("div", { class: "rv-note" },
      h("p", { text: `Counting records and checking every block reads the whole file (${fmtBytes(state.model.size)}), so it only runs when you ask.` }),
      h("button", { class: "rv-btn", text: "Count records and check blocks", onclick: () => sc.start() }),
    );
  }

  // info
  function renderInfo(panel) {
    const { model } = state;
    const dl = h("dl", { class: "rv-dl" });
    for (const [k, v] of model.info()) dl.append(h("dt", { text: k }), h("dd", { text: v }));
    const units = model.units();
    const LIMIT = 100;
    const tbody = h("tbody");
    const fill = (n) => tbody.replaceChildren(...units.rows.slice(0, n).map((r) => h("tr", {}, r.map((c) => h("td", { class: "rv-num", text: c })))));
    let more = null;
    if (units) {
      fill(LIMIT);
      const total = units.total ?? units.rows.length;
      if (units.rows.length > LIMIT) more = h("button", { class: "rv-btn rv-btn-ghost", text: `Show all ${fmtInt(units.rows.length)} ${units.title.toLowerCase()}`, onclick: (e) => { fill(units.rows.length); e.target.remove(); } });
      else if (total > units.rows.length) more = h("p", { class: "rv-faint", text: `Showing the first ${fmtInt(units.rows.length)} of ${fmtInt(total)} ${units.title.toLowerCase()}.` });
    }
    panel.append(...[
      scanControl(),
      dl,
      units && units.rows.length ? h("h3", { class: "rv-h3", text: units.title }) : null,
      units && units.rows.length ? h("div", { class: "rv-tablewrap" }, h("table", { class: "rv-table" },
        h("thead", {}, h("tr", {}, units.head.map((t) => h("th", { class: "rv-num", text: t })))),
        tbody)) : null,
      more,
    ].filter(Boolean));
  }

  // schema
  function renderSchema(panel) {
    const roots = state.model.schema();
    const total = countNodes(roots);
    const node = (n) => {
      const label = h("span", { class: "rv-node" },
        h("span", { class: `rv-kind rv-kind-${n.kind}`, text: n.kind === "leaf" ? "" : n.kind }),
        h("span", { class: "rv-node-name", text: n.name }),
        n.kind === "leaf" || n.kind === "list" || n.kind === "map" || n.kind === "union" ? h("span", { class: "rv-node-type", text: n.type }) : null,
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

  // preview: one unit (row group / stripe / block) at a time
  function renderPreview(panel) {
    const { model } = state;
    const pv = model.preview;
    if (pv.kind === "error") {
      panel.append(h("div", { class: "rv-error", role: "alert" }, h("div", { class: "rv-error-title", text: pv.title ?? ERROR_TITLES[pv.code] }), h("p", { text: pv.text })));
      return;
    }
    if (pv.kind === "unavailable") {
      panel.append(h("div", { class: "rv-note" }, h("div", { class: "rv-note-title", text: pv.title }), h("p", { text: pv.text })));
      return;
    }
    const count = pv.count();
    const unit = count <= 300
      ? h("select", { class: "rv-select", "aria-label": pv.unitLabel }, Array.from({ length: count }, (_, i) => h("option", { value: String(i), text: pv.label(i) })))
      : h("input", { class: "rv-limit", type: "number", min: "0", max: String(count - 1), value: "0", "aria-label": `${pv.unitLabel} number` });
    const limit = h("input", { class: "rv-limit", type: "number", min: "1", max: "1000", value: "50", "aria-label": "Rows to show" });
    const out = h("div", { class: "rv-tablewrap" });
    const load = async () => {
      const token = ++previewToken;
      out.replaceChildren(h("p", { class: "rv-faint", text: `Reading ${pv.unitLabel.toLowerCase()}…` }));
      try {
        const i = Math.max(0, Math.min(count - 1, Number(unit.value) || 0));
        const res = await pv.read(i, Math.max(1, Math.min(1000, Number(limit.value) || 50)));
        if (token !== previewToken) return;
        out.replaceChildren(h("table", { class: "rv-table" },
          h("thead", {}, h("tr", {}, res.columns.map((c) => h("th", { text: c })))),
          h("tbody", {}, res.rows.map((r) => h("tr", {}, r.map((v) => { const t = displayValue(v); return t == null ? h("td", { class: "rv-null", text: "null" }) : h("td", { text: t }); }))))));
      } catch (err) {
        if (token !== previewToken) return;
        const verr = err instanceof ViewerError ? err : await classifyError(err, null);
        out.replaceChildren(h("div", { class: "rv-error", role: "alert" }, h("div", { class: "rv-error-title", text: ERROR_TITLES[verr.code] ?? ERROR_TITLES.UNKNOWN }), h("p", { text: verr.message })));
      }
    };
    unit.addEventListener("change", load);
    limit.addEventListener("change", load);
    panel.append(h("div", { class: "rv-toolbar" }, h("label", {}, unit), h("label", { class: "rv-faint" }, "Rows ", limit)), out);
    if (count) load();
  }

  // describe
  function renderDescribe(panel) {
    const d = state.model.describe();
    const tbody = h("tbody");
    const count = h("span", { class: "rv-faint" });
    const fill = (q) => {
      const rows = d.rows.filter((r) => r.key.includes(q));
      tbody.replaceChildren(...rows.map((r) => h("tr", {}, r.cells.map((c) => h("td", { class: [c.num ? "rv-num" : "", c.mono ? "rv-mono" : "", c.cls ?? ""].join(" ").trim(), title: c.title, text: c.t })))));
      count.textContent = `${fmtInt(rows.length)} of ${fmtInt(d.rows.length)} columns`;
    };
    const filter = h("input", { class: "rv-filter", type: "search", placeholder: "Filter columns…", "aria-label": "Filter columns", oninput: (e) => fill(e.target.value.toLowerCase()) });
    panel.append(
      h("div", { class: "rv-toolbar" }, filter, count),
      h("div", { class: "rv-tablewrap" }, h("table", { class: "rv-table" },
        h("thead", {}, h("tr", {}, d.head.map((c) => h("th", { class: c.num ? "rv-num" : "", text: c.t })))),
        tbody)),
    );
    fill("");
  }

  // validate
  function renderValidate(panel) {
    panel.append(...[scanControl(), renderChecks(state.model.validate(), "Validation")].filter(Boolean));
  }

  function renderChecks(result, title) {
    const verdictText = { pass: "Pass", fail: "Fail", "pass-with-warnings": "Pass with warnings", partial: "Header checks pass" }[result.verdict];
    const icons = { pass: "✓", fail: "✗", warn: "!", skip: "–", pending: "…" };
    return h("div", { class: "rv-validate" },
      h("div", { class: `rv-verdict rv-verdict-${result.verdict}` },
        h("span", { class: "rv-verdict-label", text: verdictText }),
        h("span", { class: "rv-faint", text: ` ${title} · ${result.checks.length} checks${result.failed ? ` · ${result.failed} failed` : ""}${result.warned ? ` · ${result.warned} warning${result.warned > 1 ? "s" : ""}` : ""}` }),
      ),
      h("ul", { class: "rv-checks" }, result.checks.map((c) => h("li", { class: `rv-check rv-check-${c.status}` },
        h("span", { class: "rv-check-icon", "aria-label": c.status, text: icons[c.status] }),
        h("div", {}, h("div", { class: "rv-check-label", text: c.label }), h("div", { class: "rv-faint", text: c.detail })),
      ))),
    );
  }

  if (options.initialFile) openFile(options.initialFile);
  else if (options.initialUrl) openUrl(options.initialUrl);

  return {
    openFile, openUrl,
    destroy() {
      dropState();
      root.removeEventListener("dragover", onDragOver);
      root.removeEventListener("dragleave", onDragLeave);
      root.removeEventListener("drop", onDrop);
      root.replaceChildren();
      root.classList.remove("rv");
    },
  };
}
