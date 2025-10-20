"""
Tests for JSON lines reader functionality.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import rugo.jsonl as rj


def test_get_schema_basic():
    """Test schema extraction from basic JSON lines data."""
    data = b'''{"id": 1, "name": "Alice", "age": 30}
{"id": 2, "name": "Bob", "age": 25}
{"id": 3, "name": "Charlie", "age": 35}'''
    
    schema = rj.get_jsonl_schema(data)
    
    assert isinstance(schema, list)
    assert len(schema) == 3
    
    # Check column names
    names = [col['name'] for col in schema]
    assert 'id' in names
    assert 'name' in names
    assert 'age' in names


def test_read_all_columns():
    """Test reading all columns from JSON lines data."""
    data = b'''{"id": 1, "name": "Alice", "age": 30}
{"id": 2, "name": "Bob", "age": 25}
{"id": 3, "name": "Charlie", "age": 35}'''
    
    result = rj.read_jsonl(data)
    
    assert result['success']
    assert result['num_rows'] == 3
    assert len(result['column_names']) == 3
    assert len(result['columns']) == 3


def test_read_with_projection():
    """Test reading specific columns (projection pushdown)."""
    data = b'''{"id": 1, "name": "Alice", "age": 30, "salary": 50000.0}
{"id": 2, "name": "Bob", "age": 25, "salary": 45000.0}
{"id": 3, "name": "Charlie", "age": 35, "salary": 55000.0}'''
    
    result = rj.read_jsonl(data, columns=['name', 'salary'])
    
    assert result['success']
    assert result['num_rows'] == 3
    assert result['column_names'] == ['name', 'salary']
    assert len(result['columns']) == 2
    
    # Check the data
    names = result['columns'][0]
    salaries = result['columns'][1]
    
    assert names == ['Alice', 'Bob', 'Charlie']
    assert salaries == [50000.0, 45000.0, 55000.0]


def test_read_int64_column():
    """Test reading integer columns."""
    data = b'''{"id": 1, "count": 100}
{"id": 2, "count": 200}
{"id": 3, "count": 300}'''
    
    result = rj.read_jsonl(data, columns=['id', 'count'])
    
    assert result['success']
    ids = result['columns'][0]
    counts = result['columns'][1]
    
    assert ids == [1, 2, 3]
    assert counts == [100, 200, 300]


def test_read_string_column():
    """Test reading string columns."""
    data = b'''{"name": "Alice", "city": "NYC"}
{"name": "Bob", "city": "LA"}
{"name": "Charlie", "city": "SF"}'''
    
    result = rj.read_jsonl(data, columns=['name', 'city'])
    
    assert result['success']
    names = result['columns'][0]
    cities = result['columns'][1]
    
    assert names == ['Alice', 'Bob', 'Charlie']
    assert cities == ['NYC', 'LA', 'SF']


def test_read_double_column():
    """Test reading double/float columns."""
    data = b'''{"price": 19.99, "tax": 1.5}
{"price": 29.99, "tax": 2.25}
{"price": 39.99, "tax": 3.0}'''
    
    result = rj.read_jsonl(data, columns=['price', 'tax'])
    
    assert result['success']
    prices = result['columns'][0]
    taxes = result['columns'][1]
    
    assert prices == [19.99, 29.99, 39.99]
    assert taxes == [1.5, 2.25, 3.0]


def test_read_boolean_column():
    """Test reading boolean columns."""
    data = b'''{"active": true, "verified": false}
{"active": false, "verified": true}
{"active": true, "verified": true}'''
    
    result = rj.read_jsonl(data, columns=['active', 'verified'])
    
    assert result['success']
    active = result['columns'][0]
    verified = result['columns'][1]
    
    assert active == [True, False, True]
    assert verified == [False, True, True]


def test_read_with_nulls():
    """Test reading data with null values."""
    data = b'''{"id": 1, "name": "Alice", "age": 30}
{"id": 2, "name": null, "age": 25}
{"id": 3, "name": "Charlie", "age": null}'''
    
    result = rj.read_jsonl(data, columns=['id', 'name', 'age'])
    
    assert result['success']
    ids = result['columns'][0]
    names = result['columns'][1]
    ages = result['columns'][2]
    
    assert ids == [1, 2, 3]
    assert names == ['Alice', None, 'Charlie']
    assert ages == [30, 25, None]


def test_empty_data():
    """Test handling empty data."""
    data = b''
    
    result = rj.read_jsonl(data)
    
    # Empty data should return failure or empty result
    assert not result['success'] or result['num_rows'] == 0


def test_malformed_json():
    """Test handling malformed JSON."""
    data = b'''{"id": 1, "name": "Alice"
{"id": 2, "name": "Bob"}'''  # Missing closing brace on first line
    
    result = rj.read_jsonl(data)
    
    # Should handle gracefully - might skip malformed lines
    # At minimum shouldn't crash
    assert isinstance(result, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
