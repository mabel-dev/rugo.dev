# jsonl.pxd
from libc.stdint cimport uint8_t, int64_t
from libcpp.string cimport string
from libcpp.vector cimport vector

cdef extern from "jsonl_reader.hpp":
    # Forward declaration of enum
    cdef enum JsonType:
        pass
    
    # Column schema
    cdef cppclass ColumnSchema:
        string name
        JsonType type
        bint nullable
    
    # Column data structure
    cdef cppclass JsonlColumn:
        vector[int64_t] int_values
        vector[double] double_values
        vector[string] string_values
        vector[uint8_t] boolean_values
        vector[uint8_t] null_mask
        string type
        bint success
    
    # Table data structure
    cdef cppclass JsonlTable:
        vector[JsonlColumn] columns
        vector[string] column_names
        size_t num_rows
        bint success
    
    # Functions
    vector[ColumnSchema] GetJsonlSchema(const uint8_t* data, size_t size, size_t sample_size) except +
    JsonlTable ReadJsonl(const uint8_t* data, size_t size, const vector[string]& column_names) except +
    JsonlTable ReadJsonl(const uint8_t* data, size_t size) except +
