// Format detection and model assembly. A "model" is what the UI renders; each
// format builds one (parquet-model.js, orc.js, avro.js). See README.md.
import { ViewerError } from "./errors.js";
import { openAvro } from "./avro.js";
import { openOrc } from "./orc.js";
import { openParquet } from "./parquet-model.js";

const startsWith = (u8, bytes) => u8.length >= bytes.length && bytes.every((b, i) => u8[i] === b);

export async function detect(source) {
  if (source.size === 0) throw new ViewerError("EMPTY", "This file is empty.");
  const head = await source.read(0, 4);
  if (startsWith(head, [0x50, 0x41, 0x52, 0x31])) return "parquet"; // PAR1
  if (startsWith(head, [0x4f, 0x62, 0x6a, 0x01])) return "avro"; // Obj\x01
  if (startsWith(head, [0x4f, 0x52, 0x43])) return "orc"; // ORC
  throw new ViewerError("UNKNOWN_FORMAT", "This isn't a Parquet, Avro or ORC file. Those formats begin with the bytes PAR1, Obj\\x01 and ORC, and this file doesn't.");
}

// getEngine() is only called for Parquet: Avro and ORC are read without WebAssembly.
export async function openModel(source, getEngine) {
  const format = await detect(source);
  try {
    if (format === "avro") return await openAvro(source);
    if (format === "orc") return await openOrc(source);
    return await openParquet(source, await getEngine());
  } catch (err) {
    if (err instanceof ViewerError) err.format ??= format;
    throw err;
  }
}
