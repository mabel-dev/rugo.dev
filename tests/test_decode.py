"""
Tests for Parquet data decoding functionality.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest

import rugo.parquet as rp


def test_can_decode_uncompressed_plain():
    """Test that can_decode returns True for uncompressed PLAIN-encoded files."""
    # The binary.parquet file has uncompressed, PLAIN-encoded byte_array columns
    assert rp.can_decode('tests/data/binary.parquet') is True


def test_can_decode_compressed():
    """Test that can_decode returns True for SNAPPY compressed files."""
    # The snappy_compressed.parquet file uses SNAPPY compression with PLAIN encoding
    # SNAPPY compression is supported by our decoder
    assert rp.can_decode('tests/data/snappy_compressed.parquet') is True


def test_can_decode_dictionary_encoded():
    """Test that can_decode returns True for files with dictionary encoding."""
    # The dictionary_encoded.parquet file uses SNAPPY compression with RLE_DICTIONARY encoding
    # Both SNAPPY and RLE_DICTIONARY are supported
    assert rp.can_decode('tests/data/dictionary_encoded.parquet') is True


def test_can_decode_unsupported_types():
    """Test that can_decode returns False for files with unsupported types."""
    # The alltypes_plain.parquet has boolean, float, etc. which are not supported
    assert rp.can_decode('tests/data/alltypes_plain.parquet') is False


def test_decode_string_column():
    """Test decoding a string column from binary.parquet."""
    data = rp.decode_column('tests/data/binary.parquet', 'foo')
    
    # binary.parquet has 12 string values
    assert data is not None
    assert isinstance(data, list)
    assert len(data) == 12
    assert all(isinstance(s, str) for s in data)


def test_decode_nonexistent_column():
    """Test that decoding a non-existent column returns None."""
    data = rp.decode_column('tests/data/binary.parquet', 'nonexistent')
    assert data is None


def test_decode_compressed_column():
    """Test that decoding a column with unsupported encoding returns None."""
    # planets.parquet uses DELTA_BYTE_ARRAY encoding
    # We don't support DELTA_BYTE_ARRAY for decoding yet
    data = rp.decode_column('tests/data/planets.parquet', 'name')
    assert data is None


def test_decode_int32_column():
    """Test decoding an int32 column."""
    data = rp.decode_column('tests/data/test_decode.parquet', 'int32_col')
    
    assert data is not None
    assert isinstance(data, list)
    assert len(data) == 5
    assert data == [10, 20, 30, 40, 50]


def test_decode_int64_column():
    """Test decoding an int64 column."""
    data = rp.decode_column('tests/data/test_decode.parquet', 'int64_col')
    
    assert data is not None
    assert isinstance(data, list)
    assert len(data) == 5
    assert data == [100, 200, 300, 400, 500]


def test_decode_string_column_types():
    """Test decoding a string column."""
    data = rp.decode_column('tests/data/test_decode.parquet', 'string_col')
    
    assert data is not None
    assert isinstance(data, list)
    assert len(data) == 5
    assert data == ['test1', 'test2', 'test3', 'test4', 'test5']


def test_can_decode_test_file():
    """Test that can_decode works for test_decode.parquet."""
    assert rp.can_decode('tests/data/test_decode.parquet') is True


if __name__ == "__main__":

    pytest.main([__file__, "-v"])
