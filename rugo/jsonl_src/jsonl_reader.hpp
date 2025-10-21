#pragma once
#include <cstdint>
#include <string>
#include <vector>
#include <unordered_map>
#include <variant>
#include <string_view>

// JSON value types that we support
enum class JsonType {
    Null,
    Boolean,
    Integer,
    Double,
    String
};

// Schema information for a column
struct ColumnSchema {
    std::string name;
    JsonType type;
    bool nullable = true;
};

// Structure to hold decoded column data (similar to parquet decoder)
struct JsonlColumn {
    std::vector<int64_t> int_values;
    std::vector<double> double_values;
    std::vector<std::string> string_values;
    // For fast-path non-escaped strings we can store slices pointing into
    // the original input buffer and materialize them later if needed.
    std::vector<std::pair<const char*, size_t>> string_slices;
    std::vector<uint8_t> boolean_values;
    std::vector<uint8_t> null_mask;  // 1 = null, 0 = not null
    std::string type;  // "int64", "double", "string", "boolean"
    bool success = false;
};

// Structure to hold a decoded table
struct JsonlTable {
    std::vector<JsonlColumn> columns;
    std::vector<std::string> column_names;
    size_t num_rows = 0;
    bool success = false;
};

// Get schema from JSON lines data
std::vector<ColumnSchema> GetJsonlSchema(const uint8_t* data, size_t size, size_t sample_size = 1000);

// Read JSON lines data with optional column projection
JsonlTable ReadJsonl(const uint8_t* data, size_t size, const std::vector<std::string>& column_names);

// Overload that reads all columns
JsonlTable ReadJsonl(const uint8_t* data, size_t size);
