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

        // Check physical type - must be int32, int64, or byte_array
        if (col.physical_type != "int32" && col.physical_type != "int64" &&
            col.physical_type != "byte_array") {
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
                           const std::string &column_name) {
  DecodedColumn result;

  try {
    // Read metadata to find the column
    FileStats metadata = ReadParquetMetadata(path);

    // Find the column in the first row group (for prototype)
    if (metadata.row_groups.empty()) {
      return result;
    }

    const RowGroupStats &rg = metadata.row_groups[0];
    const ColumnStats *target_col = nullptr;

    for (const auto &col : rg.columns) {
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
    }

  } catch (...) {
    result.success = false;
  }

  return result;
}
