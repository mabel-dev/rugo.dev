// Engine adapter: the only module that talks to Rugo's WebAssembly build.
//
// The WASM build (rugo.dev/wasm) exposes blobSource / httpSource / readFooter.
// This adapter wraps it so the rest of the viewer sees one stable contract and
// machine-readable errors, whatever the underlying build can do today:
//
//   engine = {
//     capabilities: { footer: true, preview: bool, minMax: bool },
//     openFile(File)  -> source          // File.slice(): only requested bytes are read
//     openUrl(string) -> Promise<source> // HTTP Range requests
//     readFooter(source) -> Promise<footer>
//     readRowGroup?(source, footer, index, { columns, limit })   // optional, see below
//   }
//
//   readRowGroup resolves { columns: string[], rows: any[][], totalRows: number }.
//   It must read only that row group's column chunks through source.read().
//
// Nothing here reads a whole file, and nothing here sends file bytes anywhere.

export class ViewerError extends Error {
  constructor(code, message, detail) {
    super(message);
    this.name = "ViewerError";
    this.code = code;
    this.detail = detail;
  }
}

const MAGIC = [0x50, 0x41, 0x52, 0x31]; // "PAR1"
const isMagic = (u8) => u8.length >= 4 && MAGIC.every((b, i) => u8[i] === b);

// Turns whatever the WASM build (or fetch) threw into a ViewerError with a code.
// The WASM build throws plain Errors with message strings, so this is the one
// place that knows those strings.
export async function classifyError(err, source) {
  if (err instanceof ViewerError) return err;
  const msg = String(err && err.message ? err.message : err);

  if (/no PAR1 trailer/i.test(msg)) {
    // Starts with PAR1 but the end is missing: a cut-off download, not a different format.
    try {
      const head = await source.read(0, 4);
      if (isMagic(head)) {
        return new ViewerError(
          "TRUNCATED",
          "This file starts like a Parquet file but its end is missing. It looks truncated, perhaps from an interrupted download or copy.",
          msg,
        );
      }
    } catch (_) { /* fall through */ }
    return new ViewerError(
      "NOT_PARQUET",
      "This isn't a Parquet file. Parquet files begin and end with the bytes PAR1, and this one doesn't.",
      msg,
    );
  }
  if (/file too small/i.test(msg)) {
    return source && source.size === 0
      ? new ViewerError("EMPTY", "This file is empty.", msg)
      : new ViewerError("NOT_PARQUET", "This file is too small to be a Parquet file.", msg);
  }
  if (/footer length invalid/i.test(msg)) {
    return new ViewerError(
      "CORRUPT",
      "This Parquet file is corrupt: its footer length points outside the file.",
      msg,
    );
  }
  if (/codec|compress|unsupported/i.test(msg)) {
    return new ViewerError("UNSUPPORTED_CODEC", `Rugo can't read this file's compression: ${msg.replace(/^rugo:\s*/, "")}`, msg);
  }
  if (/^rugo:/i.test(msg)) {
    return new ViewerError(
      "CORRUPT",
      "This Parquet file's footer couldn't be decoded, so the file is probably corrupt or truncated.",
      msg.replace(/^rugo:\s*/, ""),
    );
  }
  const http = /HTTP (\d{3})/.exec(msg);
  if (http) {
    const status = Number(http[1]);
    // The WASM build reports any non-206 as "ignored Range"; only a 200 really means that.
    if (status === 200) {
      return new ViewerError(
        "RANGE_UNSUPPORTED",
        "That server doesn't support HTTP range requests, so the viewer can't read just the parts of the file it needs. Download the file and open it from disk instead.",
        msg,
      );
    }
    const why = { 401: "it needs authentication", 403: "access is forbidden", 404: "there's no file at that address", 416: "the file is empty or the range was rejected" }[status];
    return new ViewerError("HTTP", `The server answered HTTP ${status}${why ? `: ${why}` : ""}.`, msg);
  }
  if (err instanceof TypeError) {
    return new ViewerError(
      "NETWORK",
      "Couldn't fetch that URL. Either the server is unreachable or it doesn't allow cross-origin requests (CORS). The server must send Access-Control-Allow-Origin, allow the Range header and expose Content-Range. Download the file and open it from disk if you can't change the server.",
      msg,
    );
  }
  return new ViewerError("UNKNOWN", msg, msg);
}

// wasmBase: URL of the folder that holds rugo_footer.mjs (and dist/rugo.{mjs,wasm}).
export async function loadEngine({ wasmBase } = {}) {
  const base = wasmBase ?? new URL("../wasm/", import.meta.url).href;
  let mod;
  try {
    mod = await import(/* @vite-ignore */ new URL("rugo_footer.mjs", base).href);
    await mod.loadRugo();
  } catch (err) {
    throw new ViewerError(
      "ENGINE_LOAD",
      "Couldn't load the Rugo engine (WebAssembly). Check your connection and reload the page.",
      String(err && err.message ? err.message : err),
    );
  }

  const engine = {
    capabilities: {
      footer: true,
      preview: typeof mod.readRowGroup === "function",
      minMax: false, // set true once the build returns min/max values per column chunk
    },
    openFile: (file) => mod.blobSource(file),
    openUrl: async (url) => {
      try {
        return await mod.httpSource(url);
      } catch (err) {
        throw await classifyError(err, null);
      }
    },
    readFooter: async (source) => {
      try {
        return await mod.readFooter(source);
      } catch (err) {
        throw await classifyError(err, source);
      }
    },
  };
  if (engine.capabilities.preview) {
    engine.readRowGroup = async (source, footer, index, opts) => {
      try {
        return await mod.readRowGroup(source, footer, index, opts);
      } catch (err) {
        throw await classifyError(err, source);
      }
    };
  }
  return engine;
}
