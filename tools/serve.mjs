// Local preview server for docs/, with HTTP Range support.
//   node tools/serve.mjs [port]        (default 8787)
// `python3 -m http.server` ignores Range, so the JavaScript examples (which read
// /data/*.parquet by byte range, as GitHub Pages serves them) fail under it.
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../docs");
const PORT = Number(process.argv[2] ?? process.env.PORT ?? 8787);
const TYPES = {
  ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8", ".json": "application/json", ".wasm": "application/wasm",
  ".svg": "image/svg+xml", ".png": "image/png", ".gif": "image/gif", ".mp4": "video/mp4",
};

http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    let file = path.join(ROOT, path.normalize(decodeURIComponent(url.pathname)));
    if (file !== ROOT && !file.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
    let info = await stat(file);
    if (info.isDirectory()) {
      if (!url.pathname.endsWith("/")) { res.writeHead(301, { Location: `${url.pathname}/${url.search}` }).end(); return; }
      file = path.join(file, "index.html");
      info = await stat(file);
    }
    const headers = {
      "Content-Type": TYPES[path.extname(file)] ?? "application/octet-stream",
      "Accept-Ranges": "bytes",
      "Cache-Control": "no-store",
    };
    const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
    if (!range || (range[1] === "" && range[2] === "")) {
      res.writeHead(200, { ...headers, "Content-Length": info.size });
      if (req.method === "HEAD") { res.end(); return; }
      createReadStream(file).pipe(res);
      return;
    }
    // bytes=start-end, bytes=start-, or the suffix form bytes=-n (the last n bytes)
    const start = range[1] === "" ? Math.max(0, info.size - Number(range[2])) : Number(range[1]);
    const end = range[1] === "" || range[2] === "" ? info.size - 1 : Math.min(Number(range[2]), info.size - 1);
    if (start > end) { res.writeHead(416, { "Content-Range": `bytes */${info.size}` }).end(); return; }
    res.writeHead(206, { ...headers, "Content-Range": `bytes ${start}-${end}/${info.size}`, "Content-Length": end - start + 1 });
    if (req.method === "HEAD") { res.end(); return; }
    createReadStream(file, { start, end }).pipe(res);
  } catch {
    res.writeHead(404, { "Content-Type": "text/plain" }).end("not found");
  }
}).listen(PORT, () => console.log(`rugo.dev preview: http://localhost:${PORT}/`));
