"""
Example: Reading CSV/TSV files with Rugo
"""
import sys
from pathlib import Path

# Add current directory to path for running from repo
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import os
import rugo.csv as rc

# Sample CSV data
sample_csv = b'''name,age,salary,active
Alice,30,50000.0,true
Bob,25,45000.0,false
Charlie,35,55000.0,true
Diana,28,48000.0,true
Eve,32,52000.0,false'''

# Sample TSV data
sample_tsv = b'''name\tage\tsalary\tactive
Alice\t30\t50000.0\ttrue
Bob\t25\t45000.0\tfalse
Charlie\t35\t55000.0\ttrue'''

print("=" * 60)
print("Example: Reading CSV with Rugo")
print("=" * 60)

# 1. Get schema from the CSV data
print("\n1. Extract Schema:")
print("-" * 60)
schema = rc.get_csv_schema(sample_csv)
for col in schema:
    print(f"  {col['name']:15} {col['type']:10} nullable={col['nullable']}")

# 2. Read all columns
print("\n2. Read All Columns:")
print("-" * 60)
result = rc.read_csv(sample_csv)
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
result = rc.read_csv(sample_csv, columns=['name', 'salary'])
print(f"Success: {result['success']}")
print(f"Rows: {result['num_rows']}")
print(f"Columns: {result['column_names']}")
print("\nData:")
for i in range(result['num_rows']):
    print(f"  {result['columns'][0][i]:15} ${result['columns'][1][i]:,.2f}")

# 4. Working with null values
print("\n4. Handling Null/Empty Values:")
print("-" * 60)
csv_with_nulls = b'''name,age,score
Alice,30,85.5
Bob,,90.0
Charlie,35,80.0'''

result = rc.read_csv(csv_with_nulls)
print("Data with nulls:")
for i in range(result['num_rows']):
    row = {name: result['columns'][j][i] for j, name in enumerate(result['column_names'])}
    print(f"  {row}")

# 5. Auto-detect delimiter
print("\n5. Auto-Detect Delimiter:")
print("-" * 60)
dialect = rc.detect_csv_dialect(sample_csv)
print(f"Detected delimiter: '{dialect['delimiter']}'")
print(f"Quote character: '{dialect['quote_char']}'")

dialect_tsv = rc.detect_csv_dialect(sample_tsv)
print(f"\nFor TSV:")
print(f"Detected delimiter: '\\t' (tab)" if dialect_tsv['delimiter'] == '\t' else f"Detected delimiter: '{dialect_tsv['delimiter']}'")

# 6. Reading TSV data
print("\n6. Reading TSV (Tab-Separated Values):")
print("-" * 60)
result = rc.read_tsv(sample_tsv)
print(f"Success: {result['success']}")
print(f"Rows: {result['num_rows']}")
print(f"Columns: {result['column_names']}")
print("\nFirst row:")
row = {name: result['columns'][j][0] for j, name in enumerate(result['column_names'])}
print(f"  {row}")

# 7. Working with quoted fields
print("\n7. Handling Quoted Fields:")
print("-" * 60)
csv_with_quotes = b'''name,description,count
"Smith, John","A developer who likes ""quotes""",42
"Doe, Jane","Works in sales",31
Simple,No quotes here,15'''

result = rc.read_csv(csv_with_quotes)
print("Data with quoted fields:")
for i in range(result['num_rows']):
    row = {name: result['columns'][j][i] for j, name in enumerate(result['column_names'])}
    print(f"  {row}")

# 8. Working with file data
print("\n8. Reading from File:")
print("-" * 60)

# Write sample data to a file
with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv') as f:
    f.write(sample_csv)
    temp_file = f.name

# Read the file
with open(temp_file, 'rb') as f:
    file_data = f.read()
    
result = rc.read_csv(file_data, columns=['name', 'age', 'active'])
print(f"Read {result['num_rows']} rows from {temp_file}")
print(f"Columns: {result['column_names']}")

# Cleanup
os.unlink(temp_file)

print("\n" + "=" * 60)
print("Performance Advantages:")
print("=" * 60)
print("✓ Memory-based processing (no file I/O overhead)")
print("✓ Projection pushdown (skip unwanted columns during parsing)")
print("✓ Fast schema inference with type detection")
print("✓ Columnar output format")
print("✓ Native null handling")
print("✓ SIMD-optimized delimiter scanning (AVX2/SSE2)")
print("✓ RFC 4180 compliant (quoted fields, escape sequences)")
print("=" * 60)
