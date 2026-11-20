# Rugo data-file viewer

Static, serverless viewer for Parquet, Avro and ORC files on rugo.dev (`/viewer/`). The file is read
from disk (or a URL) by byte range, in the same tab. Nothing is uploaded.

| File | Role |
|---|---|
| `index.html` | The rugo.dev page: nav, privacy statement, mounts the viewer |
| `viewer.js` | UI. `mountViewer(root, options)` renders the whole viewer into any element |
| `viewer-core.js` | Pure helpers: formatting, Parquet schema tree / describe / validate |
| `formats.js` | Detects the format from its magic bytes and builds a model |
| `parquet-model.js` | Parquet model, on the footer from Rugo's WebAssembly build |
| `orc.js` | ORC reader: postscript + footer (schema, stripes, per-column statistics) |
| `avro.js` | Avro reader: header, schema, windowed block scan, record decoding |
| `codecs.js`, `proto.js` | DEFLATE / Snappy / LZ4 decoders and a minimal protobuf reader |
| `sources.js` | Byte sources: `fileSource(File)` and `urlSource(url)` (HTTP Range) |
| `engine.js` | The only module that touches the WASM build (Parquet); maps its failures to error codes |
| `errors.js` | `ViewerError` and its codes |
| `viewer.css` | Styles, scoped under `.rv` and driven by `--rv-*` variables |

Parquet uses rugo's own C++ compiled to WebAssembly (`../wasm/`, published by the `release-rugo-wasm`
workflow in opteryx-core). Avro and ORC are read by small JavaScript parsers instead, because rugo's native
readers for those formats take the whole file as one buffer. Neither needs the WASM engine, so they work
even if it fails to load.

## What each format shows

| View | Parquet | ORC | Avro |
|---|---|---|---|
| Info | rows, columns, row groups, codecs, sizes | rows, columns, stripes, codec, writer, version | records, blocks, codec, record name, metadata |
| Schema | tree (list / struct / map) | tree (list / struct / map / union) | tree (record / array / map / union / enum / logical types) |
| Preview | needs engine `readRowGroup` | not yet | block by block (null, deflate, snappy) |
| Describe | nulls, null %, stats flag, sizes | nulls, null %, **min / max**, values | none: Avro stores no statistics |
| Validate | footer consistency checks | postscript, footer, stripe and statistics checks | header, schema, every block's sync marker |

How big files are handled:

* **Parquet / ORC:** only the tail is read (about 64 KB, more when the footer is bigger).
* **Avro:** the header is read first. Counting records and checking block sync markers walks every block
  header in 4 MB windows, so memory stays flat. For a local file it starts automatically and shows
  progress; for a URL it waits for a click when the file is over 8 MB, because it reads the whole file.
  Block 0 previews immediately either way.

## Standalone sites (avroviewer.com, orcviewer.com)

The same viewer is also published on its own domains, each with a landing page written for its format.
`node tools/build_sites.mjs` copies this folder and `docs/wasm/` into `build/sites/<domain>/` (git-ignored),
one complete static site per domain; copy and FAQ live in `tools/sites/sites.mjs`. To host one, point a
static host at its folder: build command `node tools/build_sites.mjs`, publish directory
`build/sites/<domain>`. GitHub Pages allows one custom domain per repo, so rugo.dev keeps that and the
standalone domains go on a host that can serve a folder per domain. On Cloudflare, `tools/sites/<domain>/wrangler.jsonc`
serves the built folder as static assets on the domain (Workers Builds: build command
`node tools/build_sites.mjs`, deploy command `npx wrangler deploy --config tools/sites/<domain>/wrangler.jsonc`).

## Reusing it in a VSCode webview

```js
import { mountViewer } from "./viewer.js";
mountViewer(document.getElementById("root"), {
  wasmBase: webviewUri("media/wasm/"),      // Parquet only: folder holding rugo_footer.mjs and dist/
  initialFile: fileFromHost,                // optional File/Blob, or `initialUrl`
});
```

* Ship every `.js` file here, `viewer.css` and (for Parquet) the `wasm/` folder as webview resources.
* Retheme by overriding `--rv-bg`, `--rv-text`, `--rv-accent` and friends on the mount element,
  for example `var(--vscode-editor-background)`.
* The webview CSP needs `script-src ${webview.cspSource} 'wasm-unsafe-eval'`. The emscripten glue
  contains a guarded `import("node:module")` that only runs under Node; a strict bundler may warn about it.
* A webview that can't give the page a `File` can pass its own Parquet engine: `mountViewer(root, { engine })`
  with `{ capabilities, readFooter, readRowGroup? }` (see the header of `engine.js`).

## Models

`formats.js` returns a model, and `viewer.js` renders only from models, so a new format is one module:

```
{ format, label, size, tabs: ["info", ...], summary(), info() -> [[k, v]], units() -> table | null,
  schema() -> tree, describe() -> { head, rows } | absent, validate() -> { checks, verdict },
  preview: { kind: "rows", unitLabel, count(), label(i), read(i, limit) -> { columns, rows } }
         | { kind: "unavailable" | "error", title, text },
  scan?, onChange?(fn) }       // Avro's long-running block scan
```

## Parquet engine contract

`readFooter(source)` resolves the footer JSON that Rugo's WASM build returns. `source` is
`{ size, read(offset, length) -> Uint8Array, prefetched? }`. The viewer uses these fields when present and
leaves a view out rather than guess when they aren't: `created_by`, per-chunk `min` / `max`,
and `readRowGroup(source, footer, index, { limit }) -> { columns, rows }`.

## Not supported yet

* ORC files whose footer is compressed with ZSTD or LZO (NONE, ZLIB, SNAPPY and LZ4 work).
* Avro blocks compressed with zstandard, bzip2 or xz can't be previewed (the rest of the views work).
* ORC row preview, and Parquet row preview until the WASM build can decode pages.

## Tests

```
node --test tools/test_viewer_core.mjs tools/test_viewer_formats.mjs
```

Fixtures in `tools/fixtures/` are real files written by fastavro and pyarrow.
