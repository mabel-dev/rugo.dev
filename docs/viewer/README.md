# Rugo Parquet viewer

Static, serverless Parquet viewer for rugo.dev (`/viewer/`). The file is read from disk (or a URL) by byte range
and handed to Rugo's WebAssembly build in the same tab. Nothing is uploaded.

| File | Role |
|---|---|
| `index.html` | The rugo.dev page: nav, privacy statement, mounts the viewer |
| `viewer.js` | UI. `mountViewer(root, options)` renders the whole viewer into any element |
| `viewer-core.js` | Pure data layer (info, schema tree, describe, validate). No DOM, no WASM |
| `engine.js` | The only module that touches Rugo's WASM; maps its failures to error codes |
| `viewer.css` | Styles, scoped under `.rv` and driven by `--rv-*` variables |

The engine is loaded from `../wasm/` (`rugo_footer.mjs`, `dist/rugo.{mjs,wasm}`), which the
`release-rugo-wasm` workflow in opteryx-core publishes to `docs/wasm/` on each release tag.

## Views

| View | Source |
|---|---|
| Info | file size, rows, columns, row groups, codecs, data size, created-by (when the engine supplies it) |
| Schema | tree from Rugo's top-level fields plus leaf paths; list / struct / map shown nested |
| Preview | one row group at a time through `engine.readRowGroup` (shown only when the engine has it) |
| Describe | per-column nulls, null %, distinct, stats flag, size; min / max when the engine supplies values |
| Validate | metadata checks on the footer: magic, row counts, column consistency, bounds, overlap, codec support |

## Reusing it in a VSCode webview

```js
import { mountViewer } from "./viewer.js";
mountViewer(document.getElementById("root"), {
  wasmBase: webviewUri("media/wasm/"),      // folder holding rugo_footer.mjs and dist/
  initialFile: fileFromHost,                // optional File/Blob, or `initialUrl`
});
```

* Ship `viewer.js`, `viewer-core.js`, `engine.js`, `viewer.css` and the `wasm/` folder as webview resources.
* Retheme by overriding `--rv-bg`, `--rv-text`, `--rv-accent` and friends on the mount element,
  for example `var(--vscode-editor-background)`.
* The webview CSP needs `script-src ${webview.cspSource} 'wasm-unsafe-eval'`. The emscripten glue
  contains a guarded `import("node:module")` that only runs under Node; a strict bundler may warn about it.
* A webview that can't give the page a `File` can pass its own engine: `mountViewer(root, { engine })`
  with `{ capabilities, openFile, openUrl, readFooter, readRowGroup? }` (see the header of `engine.js`).

## Engine contract

`readFooter(source)` resolves the footer JSON that Rugo's WASM build returns. `source` is
`{ size, read(offset, length) -> Uint8Array }`. The viewer uses these fields when present and
leaves a view out rather than guess when they aren't: `created_by`, per-chunk `min` / `max`,
and `readRowGroup(source, footer, index, { limit }) -> { columns, rows }`.

## Tests

```
node --test tools/test_viewer_core.mjs
```
