"""
Example: Reading JSON Lines files with Rugo
"""
import rugo.jsonl as rj

# Sample JSON Lines data
sample_data = b'''{"id": 1, "name": "Alice", "age": 30, "salary": 50000.0, "active": true}
{"id": 2, "name": "Bob", "age": 25, "salary": 45000.0, "active": false}
{"id": 3, "name": "Charlie", "age": 35, "salary": 55000.0, "active": true}
{"id": 4, "name": "Diana", "age": 28, "salary": 48000.0, "active": true}
{"id": 5, "name": "Eve", "age": 32, "salary": 52000.0, "active": false}'''

print("=" * 60)
print("Example: Reading JSON Lines with Rugo")
print("=" * 60)

# 1. Get schema from the data
print("\n1. Extract Schema:")
print("-" * 60)
schema = rj.get_jsonl_schema(sample_data)
for col in schema:
    print(f"  {col['name']:15} {col['type']:10} nullable={col['nullable']}")

# 2. Read all columns
print("\n2. Read All Columns:")
print("-" * 60)
result = rj.read_jsonl(sample_data)
print(f"Success: {result['success']}")
print(f"Rows: {result['num_rows']}")
print(f"Columns: {result['column_names']}")
print("\nFirst few rows:")
for i in range(min(3, result['num_rows'])):
    row = {name: result['columns'][j][i] for j, name in enumerate(result['column_names'])}
    print(f"  {row}")

# 3. Read with projection (only specific columns)
print("\n3. Projection Pushdown (only read 'name' and 'salary'):")
print("-" * 60)
result = rj.read_jsonl(sample_data, columns=['name', 'salary'])
print(f"Success: {result['success']}")
print(f"Rows: {result['num_rows']}")
print(f"Columns: {result['column_names']}")
print("\nData:")
for i in range(result['num_rows']):
    print(f"  {result['columns'][0][i]:15} ${result['columns'][1][i]:,.2f}")

# 4. Working with null values
print("\n4. Handling Null Values:")
print("-" * 60)
data_with_nulls = b'''{"id": 1, "name": "Alice", "score": 85.5}
{"id": 2, "name": null, "score": 90.0}
{"id": 3, "name": "Charlie", "score": null}'''

result = rj.read_jsonl(data_with_nulls)
print("Data with nulls:")
for i in range(result['num_rows']):
    row = {name: result['columns'][j][i] for j, name in enumerate(result['column_names'])}
    print(f"  {row}")

# 5. Working with file data
print("\n5. Reading from File:")
print("-" * 60)
import tempfile
import os

# Write sample data to a file
with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.jsonl') as f:
    f.write(sample_data)
    temp_file = f.name

# Read the file
with open(temp_file, 'rb') as f:
    file_data = f.read()
    
result = rj.read_jsonl(file_data, columns=['id', 'name', 'age'])
print(f"Read {result['num_rows']} rows from {temp_file}")
print(f"Columns: {result['column_names']}")

# Cleanup
os.unlink(temp_file)

print("\n" + "=" * 60)
print("Performance Advantages:")
print("=" * 60)
print("✓ Memory-based processing (no file I/O overhead)")
print("✓ Projection pushdown (read only needed columns)")
print("✓ Fast schema inference")
print("✓ Columnar output format")
print("✓ Native null handling")
print("=" * 60)
