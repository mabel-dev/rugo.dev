// Byte sources: { size, read(offset, length) -> Promise<Uint8Array> }.
// Both read only the requested range; nothing here keeps the file in memory.
import { ViewerError } from "./errors.js";

const TAIL = 64 * 1024;

// A local File/Blob. slice() reads just the range from disk.
export function fileSource(blob) {
  return {
    size: blob.size,
    local: true,
    async read(offset, length) {
      return new Uint8Array(await blob.slice(offset, offset + length).arrayBuffer());
    },
  };
}

const networkError = (err) =>
  new ViewerError(
    "NETWORK",
    "Couldn't fetch that URL. Either the server is unreachable or it doesn't allow cross-origin requests (CORS). The server must send Access-Control-Allow-Origin, allow the Range header and expose Content-Range. Download the file and open it from disk if you can't change the server.",
    String(err && err.message ? err.message : err),
  );
const rangeError = (url, status) =>
  new ViewerError(
    "RANGE_UNSUPPORTED",
    "That server doesn't support HTTP range requests, so the viewer can't read just the parts of the file it needs. Download the file and open it from disk instead.",
    `${url}: server ignored Range (HTTP ${status})`,
  );
const httpError = (status, detail) => {
  const why = { 401: "it needs authentication", 403: "access is forbidden", 404: "there's no file at that address", 416: "the range was rejected" }[status];
  return new ViewerError("HTTP", `The server answered HTTP ${status}${why ? `: ${why}` : ""}.`, detail);
};

async function ranged(url, range) {
  let r;
  try { r = await fetch(url, { headers: { Range: range } }); } catch (e) { throw networkError(e); }
  return r;
}

// A URL read with HTTP Range requests. The first request asks for the last 64 KB,
// which gives the file size (Content-Range) and the tail where Parquet and ORC keep
// their metadata. `prefetched` holds those tail bytes.
export async function urlSource(url) {
  const r = await ranged(url, `bytes=-${TAIL}`);
  if (r.status === 416) {
    const m = /\*\/(\d+)/.exec(r.headers.get("Content-Range") ?? "");
    if (m && Number(m[1]) === 0) return { size: 0, local: false, read: async () => new Uint8Array(0) };
    throw httpError(416, `${url}: HTTP 416`);
  }
  if (r.status === 200) { r.body?.cancel?.(); throw rangeError(url, 200); }
  if (r.status !== 206) { r.body?.cancel?.(); throw httpError(r.status, `${url}: HTTP ${r.status}`); }
  const m = /\/(\d+)$/.exec(r.headers.get("Content-Range") ?? "");
  if (!m) throw new ViewerError("RANGE_UNSUPPORTED", "That server answered a range request without saying how big the file is (no readable Content-Range header). If it's a cross-origin server, it must expose Content-Range.", `${url}: no Content-Range total`);
  const size = Number(m[1]);
  const tail = new Uint8Array(await r.arrayBuffer());
  return {
    size,
    local: false,
    prefetched: tail,
    async read(offset, length) {
      length = Math.min(length, size - offset);
      if (length <= 0) return new Uint8Array(0);
      if (offset >= size - tail.length) return tail.subarray(offset - (size - tail.length), offset - (size - tail.length) + length);
      const res = await ranged(url, `bytes=${offset}-${offset + length - 1}`);
      if (res.status === 200) { res.body?.cancel?.(); throw rangeError(url, 200); }
      if (res.status !== 206) { res.body?.cancel?.(); throw httpError(res.status, `${url}: HTTP ${res.status}`); }
      return new Uint8Array(await res.arrayBuffer());
    },
  };
}
