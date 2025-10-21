"""Cython wrapper for JSONL reader (new name `jsonl_reader`)."""

# distutils: language = c++
# cython: language_level=3
# cython: nonecheck=False
# cython: cdivision=True
# cython: boundscheck=False
# cython: wraparound=False
# cython: infer_types=True

from libc.stdint cimport uint8_t, int64_t
from libcpp.string cimport string
from libcpp.vector cimport vector
from cpython.buffer cimport PyBUF_CONTIG_RO, PyObject_GetBuffer, PyBuffer_Release, Py_buffer

cdef extern from "decode.hpp":
    cdef enum JsonType:
        pass
    cdef cppclass ColumnSchema:
        string name
        JsonType type
        bint nullable
    cdef cppclass JsonlColumn:
        vector[int64_t] int_values
        vector[double] double_values
        vector[string] string_values
        vector[uint8_t] boolean_values
        vector[uint8_t] null_mask
        string type
        bint success
    cdef cppclass JsonlTable:
        vector[JsonlColumn] columns
        vector[string] column_names
        size_t num_rows
        bint success
    vector[ColumnSchema] GetJsonlSchema(const uint8_t* data, size_t size, size_t sample_size) except +
    JsonlTable ReadJsonl(const uint8_t* data, size_t size, const vector[string]& column_names) except +
    JsonlTable ReadJsonl(const uint8_t* data, size_t size) except +

def get_jsonl_schema(data, sample_size=1000):
    cdef const uint8_t* data_ptr
    cdef size_t data_size
    cdef bytes data_bytes
    cdef Py_buffer view
    cdef bint have_view = False
    if isinstance(data, bytes):
        data_bytes = <bytes>data
        data_ptr = <const uint8_t*>(<char*>data_bytes)
        data_size = len(data_bytes)
    else:
        if PyObject_GetBuffer(data, &view, PyBUF_CONTIG_RO) == -1:
            raise TypeError("object does not support contiguous buffer interface")
        have_view = True
        data_ptr = <const uint8_t*>view.buf
        data_size = <size_t>view.len
    cdef vector[ColumnSchema] schema = GetJsonlSchema(data_ptr, data_size, sample_size)
    if have_view:
        PyBuffer_Release(&view)
    result = []
    cdef size_t i
    cdef int type_val
    for i in range(schema.size()):
        col = schema[i]
        type_val = <int>col.type
        type_str = "string"
        if type_val == 0:
            type_str = "null"
        elif type_val == 1:
            type_str = "boolean"
        elif type_val == 2:
            type_str = "int64"
        elif type_val == 3:
            type_str = "double"
        elif type_val == 4:
            type_str = "string"
        result.append({
            'name': col.name.decode('utf-8'),
            'type': type_str,
            'nullable': col.nullable
        })
    return result


def read_jsonl(data, columns=None):
    cdef const uint8_t* data_ptr
    cdef size_t data_size
    cdef bytes data_bytes
    cdef Py_buffer view
    cdef bint have_view = False
    if isinstance(data, bytes):
        data_bytes = <bytes>data
        data_ptr = <const uint8_t*>(<char*>data_bytes)
        data_size = len(data_bytes)
    else:
        if PyObject_GetBuffer(data, &view, PyBUF_CONTIG_RO) == -1:
            raise TypeError("object does not support contiguous buffer interface")
        have_view = True
        data_ptr = <const uint8_t*>view.buf
        data_size = <size_t>view.len
    cdef vector[string] column_names_vec
    cdef JsonlTable table
    if columns is None:
        table = ReadJsonl(data_ptr, data_size)
    else:
        for col_name in columns:
            column_names_vec.push_back(col_name.encode('utf-8'))
        table = ReadJsonl(data_ptr, data_size, column_names_vec)
    if have_view:
        PyBuffer_Release(&view)
    if not table.success:
        return {
            'success': False,
            'column_names': [],
            'num_rows': 0,
            'columns': []
        }
    py_column_names = []
    cdef size_t i
    for i in range(table.column_names.size()):
        py_column_names.append(table.column_names[i].decode('utf-8'))
    py_columns = []
    cdef JsonlColumn* col
    for i in range(table.columns.size()):
        col = &table.columns[i]
        if not col.success:
            py_columns.append(None)
            continue
        col_type = col.type.decode('utf-8')
        if col_type == 'int64':
            py_list = []
            for j in range(col.int_values.size()):
                if col.null_mask[j]:
                    py_list.append(None)
                else:
                    py_list.append(col.int_values[j])
            py_columns.append(py_list)
        elif col_type == 'double':
            py_list = []
            for j in range(col.double_values.size()):
                if col.null_mask[j]:
                    py_list.append(None)
                else:
                    py_list.append(col.double_values[j])
            py_columns.append(py_list)
        elif col_type == 'string':
            py_list = []
            for j in range(col.string_values.size()):
                if col.null_mask[j]:
                    py_list.append(None)
                else:
                    py_list.append(col.string_values[j].decode('utf-8'))
            py_columns.append(py_list)
        elif col_type == 'boolean':
            py_list = []
            for j in range(col.boolean_values.size()):
                if col.null_mask[j]:
                    py_list.append(None)
                else:
                    py_list.append(bool(col.boolean_values[j]))
            py_columns.append(py_list)
        else:
            py_columns.append(None)
    return {
        'success': True,
        'column_names': py_column_names,
        'num_rows': table.num_rows,
        'columns': py_columns
    }
