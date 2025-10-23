from rugo import jsonl

raw = b'{"id": 1, "values": [1, 2, {"x": 3}] }\n{"id": 2, "values": {"a": 10, "b": [true, false]} }\n'

print("Schema:")
schema = jsonl.get_jsonl_schema(raw)
for col in schema:
    print(f"  {col}")

print("\nData:")
res = jsonl.read_jsonl(raw)
print(f"Success: {res['success']}")
print(f"Columns: {res['column_names']}")
print(f"Num rows: {res['num_rows']}")

for i, col_name in enumerate(res['column_names']):
    print(f"\nColumn '{col_name}':")
    col = res['columns'][i]
    for j, val in enumerate(col):
        print(f"  Row {j}: {val!r} (type: {type(val).__name__})")
