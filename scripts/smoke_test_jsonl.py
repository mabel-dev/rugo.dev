# Quick smoke test for read_jsonl with arrays and objects

import sys
from pathlib import Path

from rugo import jsonl

# Add current directory to path for running from repo
sys.path.insert(0, str(Path(__file__).parent))


# Build a small JSONL with two fields, values contains an array and an object
# Two rows
lines = [b'{"id": 1, "values": [1, 2, {"x": 3}] }\n', b'{"id": 2, "values": {"a": 10, "b": [true, false]} }\n']
raw = b"".join(lines)

res = jsonl.read_jsonl(raw)
print('success:', res['success'])
print('columns:', res['column_names'])
print('num_rows:', res['num_rows'])
for name, col in zip(res['column_names'], res['columns']):
    print('column', name, '->', col)

# Try with parse_objects=False
res2 = jsonl.read_jsonl(raw, None, True, False)
print('\nparse_objects=False:')
for name, col in zip(res2['column_names'], res2['columns']):
    print('column', name, '->', col)
