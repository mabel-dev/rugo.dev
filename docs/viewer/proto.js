// Minimal protobuf wire reader: just enough for ORC's PostScript and Footer.
export class ProtoError extends Error {}

export function readVarint(buf, pos) {
  let result = 0;
  let shift = 0;
  let big = null;
  for (let n = 0; n < 10; n++) {
    if (pos >= buf.length) throw new ProtoError("truncated varint");
    const b = buf[pos++];
    if (shift < 49) result += (b & 0x7f) * 2 ** shift;
    else { big ??= BigInt(result); big |= BigInt(b & 0x7f) << BigInt(shift); }
    shift += 7;
    if (!(b & 0x80)) {
      if (big === null) return [result, pos];
      return [big <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(big) : big, pos];
    }
  }
  throw new ProtoError("varint too long");
}

// zigzag (sint32 / sint64) -> Number, or BigInt when it doesn't fit.
export function unzigzag(v) {
  if (typeof v === "bigint") {
    const r = (v >> 1n) ^ -(v & 1n);
    return r >= BigInt(Number.MIN_SAFE_INTEGER) && r <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(r) : r;
  }
  return v % 2 === 0 ? v / 2 : -(v + 1) / 2;
}

// Yields [fieldNumber, wireType, value]. Varints give Number/BigInt, length-delimited
// fields a Uint8Array view, fixed32/fixed64 a Uint8Array view of 4/8 bytes.
export function* fields(buf) {
  let pos = 0;
  while (pos < buf.length) {
    let tag;
    [tag, pos] = readVarint(buf, pos);
    const field = Math.floor(Number(tag) / 8);
    const wire = Number(tag) % 8;
    if (wire === 0) {
      let v;
      [v, pos] = readVarint(buf, pos);
      yield [field, 0, v];
    } else if (wire === 2) {
      let n;
      [n, pos] = readVarint(buf, pos);
      if (typeof n !== "number" || pos + n > buf.length) throw new ProtoError("length-delimited field overruns its message");
      yield [field, 2, buf.subarray(pos, pos + n)];
      pos += n;
    } else if (wire === 1 || wire === 5) {
      const n = wire === 1 ? 8 : 4;
      if (pos + n > buf.length) throw new ProtoError("fixed field overruns its message");
      yield [field, wire, buf.subarray(pos, pos + n)];
      pos += n;
    } else {
      throw new ProtoError(`unsupported wire type ${wire}`);
    }
  }
}

// A repeated uint field, packed (one length-delimited blob) or not.
export function pushVarints(list, wire, value) {
  if (wire === 0) list.push(value);
  else { let p = 0; while (p < value.length) { let v; [v, p] = readVarint(value, p); list.push(v); } }
}

export const f64 = (u8) => new DataView(u8.buffer, u8.byteOffset, 8).getFloat64(0, true);
export const utf8 = (u8) => new TextDecoder().decode(u8);
