"""
Example: JSON Lines to Orso Schema Conversion
"""
import rugo.jsonl as rj
from rugo.converters.orso import jsonl_to_orso_schema

# Sample JSON Lines data
sample_data = b'''{"user_id": 1, "username": "alice", "score": 95.5, "active": true}
{"user_id": 2, "username": "bob", "score": 87.2, "active": false}
{"user_id": 3, "username": "charlie", "score": 92.8, "active": true}'''

print("=" * 60)
print("Example: JSON Lines to Orso Schema Conversion")
print("=" * 60)

# 1. Extract schema from JSON Lines data
print("\n1. Extract JSON Lines Schema:")
print("-" * 60)
jsonl_schema = rj.get_jsonl_schema(sample_data)
print("JSON Lines Schema:")
for col in jsonl_schema:
    print(f"  {col['name']:15} {col['type']:10} nullable={col['nullable']}")

# 2. Convert to Orso schema
print("\n2. Convert to Orso Schema:")
print("-" * 60)
orso_schema = jsonl_to_orso_schema(jsonl_schema, schema_name="users")
print(f"Schema Name: {orso_schema.name}")
print(f"Columns: {len(orso_schema.columns)}")
print("\nOrso Columns:")
for col in orso_schema.columns:
    print(f"  {col.name:15} {col.type} (nullable={col.nullable})")

# 3. Demonstrate schema validation with Orso
print("\n3. Schema Information:")
print("-" * 60)
print(f"Column count: {len(orso_schema.columns)}")
print(f"Column names: {[c.name for c in orso_schema.columns]}")

# Check specific column types
for col in orso_schema.columns:
    if col.name == "user_id":
        print(f"\n'{col.name}' column type: {col.type}")
        print(f"  Is integer type: {col.type.name == 'INTEGER'}")
    elif col.name == "score":
        print(f"'{col.name}' column type: {col.type}")
        print(f"  Is double type: {col.type.name == 'DOUBLE'}")
    elif col.name == "username":
        print(f"'{col.name}' column type: {col.type}")
        print(f"  Is varchar type: {col.type.name == 'VARCHAR'}")

print("\n" + "=" * 60)
print("Use Cases:")
print("=" * 60)
print("✓ Query planning with schema-aware optimizations")
print("✓ Type validation before data processing")
print("✓ Integration with Orso-based data systems")
print("✓ Automatic type inference from JSON data")
print("=" * 60)
