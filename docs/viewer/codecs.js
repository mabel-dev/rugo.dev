// Decompressors for the Avro and ORC metadata paths. Small and dependency-free:
// DEFLATE uses the browser's built-in DecompressionStream; Snappy and LZ4 blocks
// are decoded here. Zstandard and bzip2 aren't implemented; callers report them
// as UNSUPPORTED_CODEC.
import { ViewerError } from "./errors.js";

const corrupt = (what, format) => new ViewerError("CORRUPT", `Compressed data is damaged (${what}).`, what, format);

// Raw DEFLATE (RFC 1951), which is what Avro "deflate" and ORC "ZLIB" both use.
// A small inflate of our own rather than DecompressionStream: it behaves the same in
// every browser, and it stops at the end of the DEFLATE stream and ignores whatever
// follows, which matters because some Avro writers leave a few stray bytes there.
// Table-driven decoding after the "tiny-inflate" design.
const LEN_CLC_ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];
const lenBits = new Uint8Array(30);
const lenBase = new Uint16Array(30);
const distBits = new Uint8Array(30);
const distBase = new Uint16Array(30);
(function initTables() {
  const bitsBase = (bits, base, delta, first) => {
    for (let i = 0; i < 30 - delta; i++) bits[i + delta] = (i / delta) | 0;
    let sum = first;
    for (let i = 0; i < 30; i++) { base[i] = sum; sum += 1 << bits[i]; }
  };
  bitsBase(lenBits, lenBase, 4, 3);
  bitsBase(distBits, distBase, 2, 1);
  lenBits[28] = 0;
  lenBase[28] = 258;
})();

const newTree = () => ({ table: new Uint16Array(16), trans: new Uint16Array(288) });
function buildTree(t, lengths, off, num) {
  t.table.fill(0);
  for (let i = 0; i < num; i++) t.table[lengths[off + i]]++;
  t.table[0] = 0;
  const offs = new Uint16Array(16);
  let sum = 0;
  for (let i = 0; i < 16; i++) { offs[i] = sum; sum += t.table[i]; }
  for (let i = 0; i < num; i++) if (lengths[off + i]) t.trans[offs[lengths[off + i]]++] = i;
}
const fixedLit = newTree();
const fixedDist = newTree();
(function initFixed() {
  for (let i = 0; i < 7; i++) fixedLit.table[i] = 0;
  fixedLit.table[7] = 24; fixedLit.table[8] = 152; fixedLit.table[9] = 112;
  for (let i = 0; i < 24; i++) fixedLit.trans[i] = 256 + i;
  for (let i = 0; i < 144; i++) fixedLit.trans[24 + i] = i;
  for (let i = 0; i < 8; i++) fixedLit.trans[24 + 144 + i] = 280 + i;
  for (let i = 0; i < 112; i++) fixedLit.trans[24 + 144 + 8 + i] = 144 + i;
  for (let i = 0; i < 5; i++) fixedDist.table[i] = 0;
  fixedDist.table[5] = 32;
  for (let i = 0; i < 32; i++) fixedDist.trans[i] = i;
})();

export function inflateRawSync(src, format, maxOut = 1 << 28) {
  const bad = (what) => corrupt("deflate: " + what, format);
  let out = new Uint8Array(Math.max(1024, src.length * 4));
  let outLen = 0;
  let pos = 0;
  let tag = 0;
  let bitcount = 0;
  const lit = newTree();
  const dist = newTree();
  const clc = newTree();
  const lengths = new Uint8Array(288 + 32);

  const getbit = () => {
    if (!bitcount--) { tag = src[pos++]; bitcount = 7; }
    const b = tag & 1;
    tag >>>= 1;
    return b;
  };
  const bits = (num, base) => {
    if (!num) return base;
    while (bitcount < 24) { tag |= src[pos++] << bitcount; bitcount += 8; }
    const v = tag & (0xffff >>> (16 - num));
    tag >>>= num;
    bitcount -= num;
    return v + base;
  };
  const symbol = (t) => {
    let sum = 0;
    let cur = 0;
    let len = 0;
    do { cur = 2 * cur + getbit(); len++; if (len > 15) throw bad("invalid code"); sum += t.table[len]; cur -= t.table[len]; } while (cur >= 0);
    return t.trans[sum + cur];
  };
  const room = (n) => {
    if (outLen + n <= out.length) return;
    if (outLen + n > maxOut) throw bad("output too large");
    const bigger = new Uint8Array(Math.min(maxOut, Math.max(out.length * 2, outLen + n)));
    bigger.set(out.subarray(0, outLen));
    out = bigger;
  };

  let last;
  do {
    last = getbit();
    const type = bits(2, 0);
    if (pos > src.length + 8) throw bad("truncated");
    if (type === 0) {
      while (bitcount > 8) { pos--; bitcount -= 8; }
      const len = src[pos + 1] * 256 + src[pos];
      const inv = src[pos + 3] * 256 + src[pos + 2];
      if (len !== (~inv & 0xffff)) throw bad("stored block length mismatch");
      pos += 4;
      if (pos + len > src.length) throw bad("truncated");
      room(len);
      out.set(src.subarray(pos, pos + len), outLen);
      outLen += len;
      pos += len;
      bitcount = 0;
      continue;
    }
    let lt;
    let dt;
    if (type === 1) { lt = fixedLit; dt = fixedDist; }
    else if (type === 2) {
      const hlit = bits(5, 257);
      const hdist = bits(5, 1);
      const hclen = bits(4, 4);
      lengths.fill(0, 0, 19);
      for (let i = 0; i < hclen; i++) lengths[LEN_CLC_ORDER[i]] = bits(3, 0);
      buildTree(clc, lengths, 0, 19);
      for (let n = 0; n < hlit + hdist;) {
        const sym = symbol(clc);
        if (sym === 16) { if (n === 0) throw bad("bad repeat"); const prev = lengths[n - 1]; for (let k = bits(2, 3); k; k--) lengths[n++] = prev; }
        else if (sym === 17) for (let k = bits(3, 3); k; k--) lengths[n++] = 0;
        else if (sym === 18) for (let k = bits(7, 11); k; k--) lengths[n++] = 0;
        else lengths[n++] = sym;
        if (n > hlit + hdist) throw bad("code lengths overrun");
        if (pos > src.length + 8) throw bad("truncated");
      }
      buildTree(lit, lengths, 0, hlit);
      buildTree(dist, lengths, hlit, hdist);
      lt = lit; dt = dist;
    } else throw bad("invalid block type");
    for (;;) {
      if (pos > src.length + 8) throw bad("truncated");
      const sym = symbol(lt);
      if (sym === 256) break;
      if (sym < 256) { room(1); out[outLen++] = sym; continue; }
      const s = sym - 257;
      if (s >= 29) throw bad("invalid length symbol");
      const length = bits(lenBits[s], lenBase[s]);
      const d = symbol(dt);
      if (d >= 30) throw bad("invalid distance symbol");
      const off = outLen - bits(distBits[d], distBase[d]);
      if (off < 0) throw bad("distance too far back");
      room(length);
      for (let i = 0; i < length; i++) { out[outLen] = out[off + i]; outLen++; }
    }
  } while (!last);
  if (pos - (bitcount >> 3) > src.length) throw bad("truncated");
  return out.subarray(0, outLen);
}

export async function inflateRaw(bytes, format) {
  return inflateRawSync(bytes, format);
}

// Snappy raw block format.
export function snappyDecompress(src, format, maxOut = 1 << 28) {
  let pos = 0;
  let len = 0;
  let shift = 0;
  for (;;) {
    if (pos >= src.length) throw corrupt("snappy: truncated length", format);
    const b = src[pos++];
    len += (b & 0x7f) * 2 ** shift;
    if (!(b & 0x80)) break;
    shift += 7;
    if (shift > 35) throw corrupt("snappy: bad length", format);
  }
  if (len > maxOut) throw corrupt("snappy: implausible output size", format);
  const out = new Uint8Array(len);
  let o = 0;
  while (pos < src.length) {
    const tag = src[pos++];
    const type = tag & 3;
    if (type === 0) {
      let l = tag >> 2;
      if (l < 60) l += 1;
      else {
        const nb = l - 59;
        l = 0;
        for (let i = 0; i < nb; i++) l += src[pos++] * 2 ** (8 * i);
        l += 1;
      }
      if (pos + l > src.length || o + l > len) throw corrupt("snappy: literal overruns", format);
      out.set(src.subarray(pos, pos + l), o);
      pos += l;
      o += l;
    } else {
      let l;
      let off;
      if (type === 1) { l = ((tag >> 2) & 7) + 4; off = ((tag >> 5) << 8) | src[pos++]; }
      else if (type === 2) { l = (tag >> 2) + 1; off = src[pos] | (src[pos + 1] << 8); pos += 2; }
      else { l = (tag >> 2) + 1; off = src[pos] + src[pos + 1] * 256 + src[pos + 2] * 65536 + src[pos + 3] * 16777216; pos += 4; }
      if (off === 0 || off > o || o + l > len) throw corrupt("snappy: bad copy", format);
      for (let i = 0; i < l; i++, o++) out[o] = out[o - off];
    }
  }
  if (o !== len) throw corrupt("snappy: output length mismatch", format);
  return out;
}

// LZ4 block format (no frame), as ORC stores it. `maxOut` is the block size bound.
export function lz4BlockDecompress(src, maxOut, format) {
  const out = new Uint8Array(maxOut);
  let pos = 0;
  let o = 0;
  while (pos < src.length) {
    const token = src[pos++];
    let lit = token >> 4;
    if (lit === 15) { let b; do { if (pos >= src.length) throw corrupt("lz4: truncated", format); b = src[pos++]; lit += b; } while (b === 255); }
    if (pos + lit > src.length || o + lit > maxOut) throw corrupt("lz4: literal overruns", format);
    out.set(src.subarray(pos, pos + lit), o);
    pos += lit;
    o += lit;
    if (pos >= src.length) break; // the last sequence has literals only
    if (pos + 2 > src.length) throw corrupt("lz4: truncated offset", format);
    const off = src[pos] | (src[pos + 1] << 8);
    pos += 2;
    let m = token & 15;
    if (m === 15) { let b; do { if (pos >= src.length) throw corrupt("lz4: truncated", format); b = src[pos++]; m += b; } while (b === 255); }
    m += 4;
    if (off === 0 || off > o || o + m > maxOut) throw corrupt("lz4: bad match", format);
    for (let i = 0; i < m; i++, o++) out[o] = out[o - off];
  }
  return out.subarray(0, o);
}

let crcTable;
export function crc32(bytes) {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crcTable[n] = c >>> 0; }
  }
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = crcTable[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
