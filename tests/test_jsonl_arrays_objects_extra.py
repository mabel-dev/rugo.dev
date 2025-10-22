from rugo import jsonl


def _build_sample():
    lines = [
        b'{"id": 1, "values": [1, 2, {"x": 3}] }\n',
        b'{"id": 2, "values": {"a": 10, "b": [true, false]} }\n',
        # nested arrays
        b'{"id": 3, "values": [[1,2],[3,4,[5,6]]]}\n',
        # malformed slice (unterminated array) - should fallback to raw string or raise handledly
        b'{"id": 4, "values": [1, 2, [3, 4} }\n',
    ]
    return b"".join(lines)


def test_nested_arrays_and_objects_default():
    raw = _build_sample()
    res = jsonl.read_jsonl(raw)
    assert res['success'] is True
    values = res['columns'][1]
    # row 0 values
    assert isinstance(values[0], list)
    assert isinstance(values[0][2], (dict, bytes, bytearray, str))
    # row 2 nested arrays
    assert isinstance(values[2], list)
    assert isinstance(values[2][1], list)
    # row 3 malformed should not crash the reader; accept bytes/str fallback
    assert isinstance(values[3], (bytes, bytearray, str))


def test_flag_permutations():
    raw = _build_sample()
    # arrays disabled, objects enabled
    res = jsonl.read_jsonl(raw, None, False, True)
    values = res['columns'][1]
    assert isinstance(values[0], str)
    assert isinstance(values[1], dict)

    # arrays enabled, objects disabled
    res2 = jsonl.read_jsonl(raw, None, True, False)
    values2 = res2['columns'][1]
    assert isinstance(values2[0], list)
    # inner object inside array should be bytes/str when objects disabled
    assert isinstance(values2[0][2], (bytes, bytearray, str))


def test_malformed_slice_fallback():
    raw = _build_sample()
    # ensure parser doesn't raise SystemError or crash on malformed nested structure
    res = jsonl.read_jsonl(raw)
    values = res['columns'][1]
    assert isinstance(values[3], (bytes, bytearray, str))
