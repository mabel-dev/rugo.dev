"""
Tests for Parquet data decoding functionality.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import rugo.parquet as parquet_meta


def test_can_decode_uncompressed_plain():
    """Test that can_decode returns True for uncompressed PLAIN-encoded files."""
    # The binary.parquet file has uncompressed, PLAIN-encoded byte_array columns
    assert parquet_meta.can_decode('tests/data/binary.parquet') is True


def test_can_decode_compressed():
    """Test that can_decode returns False for compressed files."""
    # The planets.parquet file uses SNAPPY compression
    assert parquet_meta.can_decode('tests/data/planets.parquet') is False


def test_can_decode_unsupported_types():
    """Test that can_decode returns False for files with unsupported types."""
    # The alltypes_plain.parquet has boolean, float, etc. which are not supported
    assert parquet_meta.can_decode('tests/data/alltypes_plain.parquet') is False


def test_decode_string_column():
    """Test decoding a string column from binary.parquet."""
    data = parquet_meta.decode_column('tests/data/binary.parquet', 'foo')
    
    # binary.parquet has 12 string values
    assert data is not None
    assert isinstance(data, list)
    assert len(data) == 12
    assert all(isinstance(s, str) for s in data)


def test_decode_nonexistent_column():
    """Test that decoding a non-existent column returns None."""
    data = parquet_meta.decode_column('tests/data/binary.parquet', 'nonexistent')
    assert data is None


def test_decode_compressed_column():
    """Test that decoding a compressed column returns None."""
    # planets.parquet uses SNAPPY compression
    data = parquet_meta.decode_column('tests/data/planets.parquet', 'name')
    assert data is None


def test_decode_int32_column():
    """Test decoding an int32 column."""
    data = parquet_meta.decode_column('tests/data/test_decode.parquet', 'int32_col')
    
    assert data is not None
    assert isinstance(data, list)
    assert len(data) == 5
    assert data == [10, 20, 30, 40, 50]


def test_decode_int64_column():
    """Test decoding an int64 column."""
    data = parquet_meta.decode_column('tests/data/test_decode.parquet', 'int64_col')
    
    assert data is not None
    assert isinstance(data, list)
    assert len(data) == 5
    assert data == [100, 200, 300, 400, 500]


def test_decode_string_column_types():
    """Test decoding a string column."""
    data = parquet_meta.decode_column('tests/data/test_decode.parquet', 'string_col')
    
    assert data is not None
    assert isinstance(data, list)
    assert len(data) == 5
    assert data == ['test1', 'test2', 'test3', 'test4', 'test5']


def test_can_decode_test_file():
    """Test that can_decode works for test_decode.parquet."""
    assert parquet_meta.can_decode('tests/data/test_decode.parquet') is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
