#include "decode.hpp"
#include "metadata.hpp"
#include "thrift.hpp"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>

// Helper function to read LE integers from buffer
static inline int32_t ReadLE32(const uint8_t *p) {
  return (int32_t)p[0] | ((int32_t)p[1] << 8) | ((int32_t)p[2] << 16) |
         ((int32_t)p[3] << 24);
}

static inline int64_t ReadLE64(const uint8_t *p) {
  return (int64_t)p[0] | ((int64_t)p[1] << 8) | ((int64_t)p[2] << 16) |
         ((int64_t)p[3] << 24) | ((int64_t)p[4] << 32) | ((int64_t)p[5] << 40) |
         ((int64_t)p[6] << 48) | ((int64_t)p[7] << 56);
}

// Helper functions to read LE floats from buffer
static inline float ReadFloat32(const uint8_t *p) {
  uint32_t bits = ReadLE32(p);
  return *reinterpret_cast<const float*>(&bits);
}

static inline double ReadFloat64(const uint8_t *p) {
  uint64_t bits = ReadLE64(p);
  return *reinterpret_cast<const double*>(&bits);
}

bool CanDecode(const std::string &path) {
  try {
    // Read metadata to check if we can decode this file
    FileStats metadata = ReadParquetMetadata(path);

    // Check all columns in all row groups
    for (const auto &rg : metadata.row_groups) {
      for (const auto &col : rg.columns) {
        // Check compression codec - must be uncompressed (codec == 0)
        if (col.codec != 0) {
          return false;
        }

        // Check physical type - must be supported primitive types
        if (col.physical_type != "int32" && col.physical_type != "int64" &&
            col.physical_type != "byte_array" && col.physical_type != "boolean" &&
            col.physical_type != "float32" && col.physical_type != "float64") {
          return false;
        }

        // Check encodings - must contain PLAIN (encoding 0)
        bool has_plain = false;
        for (int32_t enc : col.encodings) {
          if (enc == 0) {
            has_plain = true;
            break;
          }
        }
        if (!has_plain) {
          return false;
        }
      }
    }

    return true;
  } catch (...) {
    return false;
  }
}

bool CanDecode(const uint8_t* data, size_t size) {
  try {
    // Read metadata from memory buffer to check if we can decode this data
    FileStats metadata = ReadParquetMetadataFromBuffer(data, size);

    // Check all columns in all row groups
    for (const auto &rg : metadata.row_groups) {
      for (const auto &col : rg.columns) {
        // Check compression codec - must be uncompressed (codec == 0)
        if (col.codec != 0) {
          return false;
        }

        // Check physical type - must be supported primitive types
        if (col.physical_type != "int32" && col.physical_type != "int64" &&
            col.physical_type != "byte_array" && col.physical_type != "boolean" &&
            col.physical_type != "float32" && col.physical_type != "float64") {
          return false;
        }

        // Check encodings - must contain PLAIN (encoding 0)
        bool has_plain = false;
        for (int32_t enc : col.encodings) {
          if (enc == 0) {
            has_plain = true;
            break;
          }
        }
        if (!has_plain) {
          return false;
        }
      }
    }

    return true;
  } catch (...) {
    return false;
  }
}

// Parse a PageHeader to get page type, uncompressed size, and value count
struct PageHeader {
  int32_t page_type = -1;          // 0=DATA_PAGE, 1=INDEX_PAGE, 2=DICTIONARY_PAGE, etc.
  int32_t uncompressed_page_size = 0;
  int32_t compressed_page_size = 0;
  int32_t num_values = 0;
};

static PageHeader ParsePageHeader(TInput &in) {
  PageHeader header;
  int16_t last_id = 0;

  while (true) {
    auto fh = ReadFieldHeader(in, last_id);
    if (fh.type == 0)
      break;

    switch (fh.id) {
    case 1: // type
      header.page_type = ReadI32(in);
      break;
    case 2: // uncompressed_page_size
      header.uncompressed_page_size = ReadI32(in);
      break;
    case 3: // compressed_page_size
      header.compressed_page_size = ReadI32(in);
      break;
    case 5: { // data_page_header (struct) - field type should be 12 for STRUCT
      int16_t dph_last_id = 0;
      while (true) {
        auto dph_fh = ReadFieldHeader(in, dph_last_id);
        if (dph_fh.type == 0)
          break;
        switch (dph_fh.id) {
        case 1: // num_values
          header.num_values = ReadI32(in);
          break;
        default:
          SkipField(in, dph_fh.type);
          break;
        }
      }
      break;
    }
    default:
      SkipField(in, fh.type);
      break;
    }
  }

  return header;
}

DecodedColumn DecodeColumn(const std::string &path,
                           const std::string &column_name,
                           const RowGroupStats &row_group, 
                           int row_group_index) {
  DecodedColumn result;

  try {
    // Find the column in the provided row group
    const ColumnStats *target_col = nullptr;

    for (const auto &col : row_group.columns) {
      if (col.name == column_name) {
        target_col = &col;
        break;
      }
    }

    if (!target_col) {
      return result;
    }

    // Check if we can decode this column
    if (target_col->codec != 0) {
      return result; // Not uncompressed
    }

    bool has_plain = false;
    for (int32_t enc : target_col->encodings) {
      if (enc == 0) {
        has_plain = true;
        break;
      }
    }
    if (!has_plain) {
      return result; // No PLAIN encoding
    }

    // Set the type
    result.type = target_col->physical_type;

    // Open the file and read the entire column chunk
    std::ifstream file(path, std::ios::binary);
    if (!file.is_open()) {
      return result;
    }

    int64_t offset = target_col->data_page_offset;
    int64_t total_size = target_col->total_compressed_size;
    if (offset < 0 || total_size <= 0) {
      return result;
    }

    file.seekg(offset);

    // Read the entire column chunk
    std::vector<uint8_t> chunk_data(total_size);
    file.read(reinterpret_cast<char *>(chunk_data.data()), total_size);
    if (file.gcount() != total_size) {
      return result;
    }

    // Parse the page header to find where the data starts
    TInput header_in{chunk_data.data(), chunk_data.data() + chunk_data.size()};
    PageHeader page_header = ParsePageHeader(header_in);

    if (page_header.page_type != 0) {
      return result; // Not a data page
    }

    // Calculate how much of the buffer was used for the header
    size_t header_size = header_in.p - chunk_data.data();

    // The data starts after the header
    // For non-nullable PLAIN-encoded columns, data follows immediately
    const uint8_t *data_ptr = chunk_data.data() + header_size;
    size_t data_size = chunk_data.size() - header_size;

    int32_t num_values = target_col->num_values;
    if (num_values <= 0) {
      num_values = page_header.num_values;
    }

    // Decode based on type
    if (result.type == "int32") {
      result.int32_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 4 <= chunk_data.data() + chunk_data.size(); i++) {
        int32_t value = ReadLE32(data_ptr);
        result.int32_values.push_back(value);
        data_ptr += 4;
      }
      result.success = (result.int32_values.size() == (size_t)num_values);
    } else if (result.type == "int64") {
      result.int64_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 8 <= chunk_data.data() + chunk_data.size(); i++) {
        int64_t value = ReadLE64(data_ptr);
        result.int64_values.push_back(value);
        data_ptr += 8;
      }
      result.success = (result.int64_values.size() == (size_t)num_values);
    } else if (result.type == "byte_array") {
      // PLAIN encoding for byte_array: each value is 4-byte length + data
      result.string_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 4 <= chunk_data.data() + chunk_data.size(); i++) {
        int32_t length = ReadLE32(data_ptr);
        data_ptr += 4;

        if (data_ptr + length > chunk_data.data() + chunk_data.size()) {
          break;
        }

        std::string value(reinterpret_cast<const char *>(data_ptr), length);
        result.string_values.push_back(value);
        data_ptr += length;
      }
      result.success = (result.string_values.size() == (size_t)num_values);
    } else if (result.type == "boolean") {
      // PLAIN encoding for boolean: 1 bit per value, packed into bytes
      result.boolean_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr < chunk_data.data() + chunk_data.size(); i++) {
        // Each byte contains up to 8 boolean values
        uint8_t byte_value = data_ptr[i / 8];
        uint8_t bit_value = (byte_value >> (i % 8)) & 1;
        result.boolean_values.push_back(bit_value);
        if ((i + 1) % 8 == 0) {
          data_ptr += 1;
        }
      }
      // Move past the last partial byte if necessary
      if (num_values % 8 != 0 && num_values > 0) {
        data_ptr += 1;
      }
      result.success = (result.boolean_values.size() == (size_t)num_values);
    } else if (result.type == "float32") {
      result.float32_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 4 <= chunk_data.data() + chunk_data.size(); i++) {
        float value = ReadFloat32(data_ptr);
        result.float32_values.push_back(value);
        data_ptr += 4;
      }
      result.success = (result.float32_values.size() == (size_t)num_values);
    } else if (result.type == "float64") {
      result.float64_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 8 <= chunk_data.data() + chunk_data.size(); i++) {
        double value = ReadFloat64(data_ptr);
        result.float64_values.push_back(value);
        data_ptr += 8;
      }
      result.success = (result.float64_values.size() == (size_t)num_values);
    }

  } catch (...) {
    result.success = false;
  }

  return result;
}

// Helper function to decode column data from a memory buffer
static DecodedColumn DecodeColumnFromChunk(const uint8_t* chunk_data, size_t chunk_size, 
                                          const ColumnStats* target_col) {
  DecodedColumn result;
  
  try {
    // Check if we can decode this column
    if (target_col->codec != 0) {
      return result; // Not uncompressed
    }

    bool has_plain = false;
    for (int32_t enc : target_col->encodings) {
      if (enc == 0) {
        has_plain = true;
        break;
      }
    }
    if (!has_plain) {
      return result; // No PLAIN encoding
    }

    // Set the type
    result.type = target_col->physical_type;

    // Parse the page header to find where the data starts
    TInput header_in{chunk_data, chunk_data + chunk_size};
    PageHeader page_header = ParsePageHeader(header_in);

    if (page_header.page_type != 0) {
      return result; // Not a data page
    }

    // Calculate how much of the buffer was used for the header
    size_t header_size = header_in.p - chunk_data;

    // The data starts after the header
    const uint8_t *data_ptr = chunk_data + header_size;

    int32_t num_values = target_col->num_values;
    if (num_values <= 0) {
      num_values = page_header.num_values;
    }

    // Decode based on type
    if (result.type == "int32") {
      result.int32_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 4 <= chunk_data + chunk_size; i++) {
        int32_t value = ReadLE32(data_ptr);
        result.int32_values.push_back(value);
        data_ptr += 4;
      }
      result.success = (result.int32_values.size() == (size_t)num_values);
    } else if (result.type == "int64") {
      result.int64_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 8 <= chunk_data + chunk_size; i++) {
        int64_t value = ReadLE64(data_ptr);
        result.int64_values.push_back(value);
        data_ptr += 8;
      }
      result.success = (result.int64_values.size() == (size_t)num_values);
    } else if (result.type == "byte_array") {
      // PLAIN encoding for byte_array: each value is 4-byte length + data
      result.string_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 4 <= chunk_data + chunk_size; i++) {
        int32_t length = ReadLE32(data_ptr);
        data_ptr += 4;

        if (data_ptr + length > chunk_data + chunk_size) {
          break;
        }

        std::string value(reinterpret_cast<const char *>(data_ptr), length);
        result.string_values.push_back(value);
        data_ptr += length;
      }
      result.success = (result.string_values.size() == (size_t)num_values);
    } else if (result.type == "boolean") {
      // PLAIN encoding for boolean: 1 bit per value, packed into bytes
      result.boolean_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr < chunk_data + chunk_size; i++) {
        // Each byte contains up to 8 boolean values
        uint8_t byte_value = data_ptr[i / 8];
        uint8_t bit_value = (byte_value >> (i % 8)) & 1;
        result.boolean_values.push_back(bit_value);
        if ((i + 1) % 8 == 0) {
          data_ptr += 1;
        }
      }
      // Move past the last partial byte if necessary
      if (num_values % 8 != 0 && num_values > 0) {
        data_ptr += 1;
      }
      result.success = (result.boolean_values.size() == (size_t)num_values);
    } else if (result.type == "float32") {
      result.float32_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 4 <= chunk_data + chunk_size; i++) {
        float value = ReadFloat32(data_ptr);
        result.float32_values.push_back(value);
        data_ptr += 4;
      }
      result.success = (result.float32_values.size() == (size_t)num_values);
    } else if (result.type == "float64") {
      result.float64_values.reserve(num_values);
      for (int32_t i = 0; i < num_values && data_ptr + 8 <= chunk_data + chunk_size; i++) {
        double value = ReadFloat64(data_ptr);
        result.float64_values.push_back(value);
        data_ptr += 8;
      }
      result.success = (result.float64_values.size() == (size_t)num_values);
    }

  } catch (...) {
    result.success = false;
  }

  return result;
}

// Decode a specific column from memory buffer for a specific row group
DecodedColumn DecodeColumnFromMemory(const uint8_t* data, size_t size, 
                                   const std::string &column_name,
                                   const RowGroupStats &row_group, 
                                   int row_group_index) {
  DecodedColumn result;

  try {
    // Find the column in the provided row group
    const ColumnStats *target_col = nullptr;

    for (const auto &col : row_group.columns) {
      if (col.name == column_name) {
        target_col = &col;
        break;
      }
    }

    if (!target_col) {
      return result;
    }

    int64_t offset = target_col->data_page_offset;
    int64_t total_size = target_col->total_compressed_size;
    if (offset < 0 || total_size <= 0) {
      return result;
    }

    // Check bounds
    if (offset + total_size > (int64_t)size) {
      return result;
    }

    // Extract the chunk data from the memory buffer
    const uint8_t* chunk_data = data + offset;
    
    return DecodeColumnFromChunk(chunk_data, total_size, target_col);

  } catch (...) {
    result.success = false;
  }

  return result;
}

// NEW PRIMARY API: Read parquet data from memory view with column selection
DecodedTable ReadParquet(const uint8_t* data, size_t size, const std::vector<std::string>& column_names) {
  DecodedTable table;
  
  try {
    // Read metadata from the memory buffer
    FileStats metadata = ReadParquetMetadataFromBuffer(data, size);
    
    // Set up the table structure
    table.column_names = column_names;
    table.row_groups.resize(metadata.row_groups.size());
    
    // Process each row group
    for (size_t rg_idx = 0; rg_idx < metadata.row_groups.size(); rg_idx++) {
      const RowGroupStats& row_group = metadata.row_groups[rg_idx];
      table.row_groups[rg_idx].resize(column_names.size());
      
      // Decode each requested column
      for (size_t col_idx = 0; col_idx < column_names.size(); col_idx++) {
        const std::string& column_name = column_names[col_idx];
        
        table.row_groups[rg_idx][col_idx] = DecodeColumnFromMemory(
          data, size, column_name, row_group, rg_idx
        );
      }
    }
    
    table.success = true;
    
  } catch (...) {
    table.success = false;
  }
  
  return table;
}

// Overload that decodes all columns when none are specified
DecodedTable ReadParquet(const uint8_t* data, size_t size) {
  DecodedTable table;
  
  try {
    // Read metadata from the memory buffer
    FileStats metadata = ReadParquetMetadataFromBuffer(data, size);
    
    // Extract all column names from the first row group
    std::vector<std::string> all_column_names;
    if (!metadata.row_groups.empty()) {
      for (const auto& col : metadata.row_groups[0].columns) {
        all_column_names.push_back(col.name);
      }
    }
    
    // Use the existing function with all column names
    return ReadParquet(data, size, all_column_names);
    
  } catch (...) {
    table.success = false;
  }
  
  return table;
}

// Backward compatibility overload - reads metadata and decodes from first row group
DecodedColumn DecodeColumn(const std::string &path, const std::string &column_name) {
  try {
    FileStats metadata = ReadParquetMetadata(path);
    if (metadata.row_groups.empty()) {
      return DecodedColumn{};
    }
    return DecodeColumn(path, column_name, metadata.row_groups[0], 0);
  } catch (...) {
    return DecodedColumn{};
  }
}
