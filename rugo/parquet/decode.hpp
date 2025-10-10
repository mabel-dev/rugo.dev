#pragma once
#include "metadata.hpp"
#include <cstdint>
#include <string>
#include <vector>

// Structure to hold decoded column data
struct DecodedColumn {
  std::vector<int32_t> int32_values;
  std::vector<int64_t> int64_values;
  std::vector<std::string> string_values;
  std::string type; // "int32", "int64", "string"
  bool success = false;
};

// Check if a parquet file can be decoded with our limited decoder
// Returns true only if:
// - All columns are uncompressed
// - All columns use PLAIN encoding
// - All columns are int32, int64, or string types
bool CanDecode(const std::string &path);

// Decode a specific column from a parquet file
// Returns decoded data in the appropriate vector based on column type
DecodedColumn DecodeColumn(const std::string &path, const std::string &column_name);
