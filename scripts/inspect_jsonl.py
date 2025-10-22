from rugo import jsonl


def _build_sample():
    lines = [
        b'{"id": 1, "values": [1, 2, {"x": 3}] }\n',
        b'{"id": 2, "values": {"a": 10, "b": [true, false]} }\n',
        b'{"id": 3, "values": [[1,2],[3,4,[5,6]]] }\n',
        b'{"id": 4, "values": [1, 2, [3, 4} }\n',
    ]
    return b"".join(lines)


if __name__ == '__main__':
    raw = _build_sample()
    res = jsonl.read_jsonl(raw)
    print('success=', res['success'])
    print('num_rows=', res['num_rows'])
    print('column_names=', res['column_names'])
    for i, col in enumerate(res['columns']):
        if col is None:
            print(f'col {i} is None')
            continue
        print(f'col {i} len={len(col)} sample types: {[type(x) for x in col]}')
    print('full values column:', res['columns'][1])
