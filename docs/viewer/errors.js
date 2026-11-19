// Viewer errors carry a machine-readable `code`:
//   UNKNOWN_FORMAT  not Parquet, Avro or ORC          EMPTY              zero-byte file
//   TRUNCATED       starts right, end is missing      CORRUPT            signature ok, body isn't
//   UNSUPPORTED_CODEC  valid file, compression the viewer can't decompress
//   NETWORK / RANGE_UNSUPPORTED / HTTP    URL mode    ENGINE_LOAD        WASM engine didn't load
export class ViewerError extends Error {
  constructor(code, message, detail, format) {
    super(message);
    this.name = "ViewerError";
    this.code = code;
    this.detail = detail;
    this.format = format; // "parquet" | "avro" | "orc" when known
  }
}
