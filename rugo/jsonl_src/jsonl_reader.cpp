#include "jsonl_reader.hpp"
#include "simd_helpers.hpp"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <unordered_set>
#include "vendor/fast_float/fast_float.h"

// Fast JSON parser optimized for JSON lines format
class JsonParser {
public:
    JsonParser(const uint8_t* data, size_t size) 
        : data_(reinterpret_cast<const char*>(data)), 
          size_(size), 
          pos_(0) {}

    // Parse a single JSON line and return key/value slices to avoid allocations.
    // Each entry: key_start, key_len, value_start, value_len, JsonType, has_escape
    bool ParseLineKV(std::vector<std::tuple<const char*, size_t, const char*, size_t, JsonType, bool>>& out_kvs) {
        out_kvs.clear();

        // Skip whitespace to start of object
        SkipWhitespace();
        if (pos_ >= size_) return false;

        // Expect '{'
        if (data_[pos_] != '{') {
            // Skip to end of line and try next
            while (pos_ < size_ && data_[pos_] != '\n') pos_++;
            if (pos_ < size_) pos_++;  // Skip newline
            return false;
        }
        pos_++;

        SkipWhitespace();

        // Empty object
        if (pos_ < size_ && data_[pos_] == '}') {
            pos_++;
            SkipToNextLine();
            return true;
        }

        // Parse key-value pairs
        while (pos_ < size_) {
            SkipWhitespace();

            // End of object
            if (data_[pos_] == '}') {
                pos_++;
                SkipToNextLine();
                return true;
            }

            // Parse key (must be a string)
            size_t key_start = 0;
            size_t key_len = 0;
            if (!ParseStringSlice(key_start, key_len)) {
                SkipToNextLine();
                return false;
            }

            SkipWhitespace();

            // Expect ':'
            if (pos_ >= size_ || data_[pos_] != ':') {
                SkipToNextLine();
                return false;
            }
            pos_++;

            SkipWhitespace();

            // Parse value
            JsonType type;
            size_t value_start = 0;
            size_t value_len = 0;
            bool has_escape = false;
            if (!ParseValueSlice(type, value_start, value_len, has_escape)) {
                SkipToNextLine();
                return false;
            }

            out_kvs.emplace_back(data_ + key_start, key_len, data_ + value_start, value_len, type, has_escape);

            SkipWhitespace();

            // Check for comma or end of object
            if (pos_ >= size_) {
                SkipToNextLine();
                return false;
            }

            if (data_[pos_] == ',') {
                pos_++;
            } else if (data_[pos_] == '}') {
                pos_++;
                SkipToNextLine();
                return true;
            } else {
                SkipToNextLine();
                return false;
            }
        }

        return false;
    }

private:
    void SkipWhitespace() {
        while (pos_ < size_ && (data_[pos_] == ' ' || data_[pos_] == '\t' || 
                                data_[pos_] == '\r')) {
            pos_++;
        }
    }
    
    void SkipToNextLine() {
        if (pos_ >= size_) return;
        
        size_t remaining = size_ - pos_;
        const char* newline = simd::FindNewline(data_ + pos_, remaining);
        if (newline) {
            pos_ = (newline - data_) + 1;  // Skip past the newline
        } else {
            pos_ = size_;  // No newline found, go to end
        }
    }
    
    bool ParseString(std::string& result) {
        result.clear();
        
        if (pos_ >= size_ || data_[pos_] != '"') return false;
        pos_++;
        
        size_t start = pos_;
        
        // Fast path: scan for end quote or escape without allocating
        while (pos_ < size_) {
            char c = data_[pos_];
            
            if (c == '"') {
                // Found closing quote - copy the whole string at once
                result.assign(data_ + start, pos_ - start);
                pos_++;
                return true;
            }
            
            if (c == '\\') {
                // Hit an escape - need to handle character by character
                // First, copy everything up to the escape
                result.assign(data_ + start, pos_ - start);
                
                // Now process escapes
                while (pos_ < size_) {
                    c = data_[pos_];
                    
                    if (c == '"') {
                        pos_++;
                        return true;
                    }
                    
                    if (c == '\\') {
                        pos_++;
                        if (pos_ >= size_) return false;
                        
                        char escaped = data_[pos_];
                        switch (escaped) {
                            case '"':  result += '"'; break;
                            case '\\': result += '\\'; break;
                            case '/':  result += '/'; break;
                            case 'b':  result += '\b'; break;
                            case 'f':  result += '\f'; break;
                            case 'n':  result += '\n'; break;
                            case 'r':  result += '\r'; break;
                            case 't':  result += '\t'; break;
                            case 'u':
                                // Unicode escape - simplified handling
                                pos_++;
                                if (pos_ + 3 < size_) {
                                    // For simplicity, just skip the 4 hex digits
                                    pos_ += 3;
                                }
                                break;
                            default:
                                result += escaped;
                        }
                        pos_++;
                    } else {
                        result += c;
                        pos_++;
                    }
                }
                
                return false;  // No closing quote found
            }
            
            pos_++;
        }
        
        return false;  // No closing quote found
    }

    // Parse string but return slice offsets instead of allocating
    bool ParseStringSlice(size_t& out_start, size_t& out_len) {
        out_start = 0;
        out_len = 0;

        if (pos_ >= size_ || data_[pos_] != '"') return false;
        pos_++;

        size_t start = pos_;
        bool saw_escape = false;

        while (pos_ < size_) {
            char c = data_[pos_];

            if (c == '"') {
                // Found closing quote
                out_start = start;
                out_len = pos_ - start;
                pos_++;
                return true;
            }

            if (c == '\\') {
                saw_escape = true;
                // We still need to advance to find the closing quote; caller will
                // be signalled via has_escape in ParseValueSlice.
                pos_++; // move to escaped char
                if (pos_ < size_) pos_++;
                continue;
            }

            pos_++;
        }

        return false;  // No closing quote found
    }
    
    bool ParseValue(JsonType& type, std::string& value) {
        if (pos_ >= size_) return false;
        
        char c = data_[pos_];
        
        // Null - using memcmp for faster comparison
        if (c == 'n' && pos_ + 4 <= size_ && 
            memcmp(data_ + pos_, "null", 4) == 0) {
            type = JsonType::Null;
            value = "";
            pos_ += 4;
            return true;
        }
        
        // Boolean true - using memcmp for faster comparison
        if (c == 't' && pos_ + 4 <= size_ &&
            memcmp(data_ + pos_, "true", 4) == 0) {
            type = JsonType::Boolean;
            value = "true";
            pos_ += 4;
            return true;
        }
        
        // Boolean false - using memcmp for faster comparison
        if (c == 'f' && pos_ + 5 <= size_ &&
            memcmp(data_ + pos_, "false", 5) == 0) {
            type = JsonType::Boolean;
            value = "false";
            pos_ += 5;
            return true;
        }
        
        // String
        if (c == '"') {
            type = JsonType::String;
            return ParseString(value);
        }
        
        // Number (integer or double)
        if (c == '-' || c == '+' || (c >= '0' && c <= '9')) {
            size_t start = pos_;
            bool is_double = false;
            
            // Sign
            if (c == '-' || c == '+') pos_++;
            
            // Digits
            while (pos_ < size_ && data_[pos_] >= '0' && data_[pos_] <= '9') {
                pos_++;
            }
            
            // Decimal point
            if (pos_ < size_ && data_[pos_] == '.') {
                is_double = true;
                pos_++;
                while (pos_ < size_ && data_[pos_] >= '0' && data_[pos_] <= '9') {
                    pos_++;
                }
            }
            
            // Exponent
            if (pos_ < size_ && (data_[pos_] == 'e' || data_[pos_] == 'E')) {
                is_double = true;
                pos_++;
                if (pos_ < size_ && (data_[pos_] == '+' || data_[pos_] == '-')) {
                    pos_++;
                }
                while (pos_ < size_ && data_[pos_] >= '0' && data_[pos_] <= '9') {
                    pos_++;
                }
            }
            
            value = std::string(data_ + start, pos_ - start);
            type = is_double ? JsonType::Double : JsonType::Integer;
            return true;
        }
        
        // Skip arrays and objects for now (not supported in columnar format)
        if (c == '[' || c == '{') {
            int depth = 0;
            char open = c;
            char close = (c == '[') ? ']' : '}';
            
            while (pos_ < size_) {
                if (data_[pos_] == open) depth++;
                else if (data_[pos_] == close) {
                    depth--;
                    if (depth == 0) {
                        pos_++;
                        type = JsonType::Null;  // Treat nested structures as null
                        value = "";
                        return true;
                    }
                }
                pos_++;
            }
            return false;
        }
        
        return false;
    }

    // Parse value but return slice offsets and whether there are escapes for strings
    bool ParseValueSlice(JsonType& type, size_t& out_start, size_t& out_len, bool& out_has_escape) {
        out_start = 0;
        out_len = 0;
        out_has_escape = false;

        if (pos_ >= size_) return false;

        char c = data_[pos_];

        // Null - using memcmp for faster comparison
        if (c == 'n' && pos_ + 4 <= size_ && 
            memcmp(data_ + pos_, "null", 4) == 0) {
            type = JsonType::Null;
            out_start = 0; out_len = 0;
            pos_ += 4;
            return true;
        }

        // Boolean true
        if (c == 't' && pos_ + 4 <= size_ &&
            memcmp(data_ + pos_, "true", 4) == 0) {
            type = JsonType::Boolean;
            out_start = data_ + pos_ - data_; out_len = 4;
            pos_ += 4;
            return true;
        }

        // Boolean false
        if (c == 'f' && pos_ + 5 <= size_ &&
            memcmp(data_ + pos_, "false", 5) == 0) {
            type = JsonType::Boolean;
            out_start = data_ + pos_ - data_; out_len = 5;
            pos_ += 5;
            return true;
        }

        // String
        if (c == '"') {
            type = JsonType::String;
            size_t s_start = 0, s_len = 0;
            size_t saved_pos = pos_;
            // Try to parse slice; note ParseStringSlice advances pos_
            bool ok = ParseStringSlice(s_start, s_len);
            if (!ok) return false;
            // Check if this slice contains any escape sequences (simple scan)
            out_has_escape = false;
            for (size_t i = 0; i < s_len; ++i) {
                if (data_[s_start + i] == '\\') { out_has_escape = true; break; }
            }
            out_start = s_start;
            out_len = s_len;
            return true;
        }

        // Number (integer or double)
        if (c == '-' || c == '+' || (c >= '0' && c <= '9')) {
            size_t start = pos_;
            bool is_double = false;

            // Sign
            if (c == '-' || c == '+') pos_++;

            // Digits
            while (pos_ < size_ && data_[pos_] >= '0' && data_[pos_] <= '9') {
                pos_++;
            }

            // Decimal point
            if (pos_ < size_ && data_[pos_] == '.') {
                is_double = true;
                pos_++;
                while (pos_ < size_ && data_[pos_] >= '0' && data_[pos_] <= '9') {
                    pos_++;
                }
            }

            // Exponent
            if (pos_ < size_ && (data_[pos_] == 'e' || data_[pos_] == 'E')) {
                is_double = true;
                pos_++;
                if (pos_ < size_ && (data_[pos_] == '+' || data_[pos_] == '-')) {
                    pos_++;
                }
                while (pos_ < size_ && data_[pos_] >= '0' && data_[pos_] <= '9') {
                    pos_++;
                }
            }

            out_start = start;
            out_len = pos_ - start;
            type = is_double ? JsonType::Double : JsonType::Integer;
            return true;
        }

        // Skip arrays and objects for now (not supported in columnar format)
        if (c == '[' || c == '{') {
            int depth = 0;
            char open = c;
            char close = (c == '[') ? ']' : '}';

            while (pos_ < size_) {
                if (data_[pos_] == open) depth++;
                else if (data_[pos_] == close) {
                    depth--;
                    if (depth == 0) {
                        pos_++;
                        type = JsonType::Null;  // Treat nested structures as null
                        out_start = 0; out_len = 0;
                        return true;
                    }
                }
                pos_++;
            }
            return false;
        }

        return false;
    }
    
    const char* data_;
    size_t size_;
    size_t pos_;
};

// Infer the type from multiple values (used for schema detection)
static JsonType InferType(JsonType type1, JsonType type2) {
    if (type1 == JsonType::Null) return type2;
    if (type2 == JsonType::Null) return type1;
    if (type1 == type2) return type1;
    
    // Integer can be promoted to Double
    if ((type1 == JsonType::Integer && type2 == JsonType::Double) ||
        (type1 == JsonType::Double && type2 == JsonType::Integer)) {
        return JsonType::Double;
    }
    
    // Everything else becomes String
    return JsonType::String;
}

// Fast integer parsing without string allocation (2-3x faster than std::stoll)
// Based on Opteryx's fast_atoll implementation
static inline int64_t FastParseInt(const char* str, size_t len) {
    if (len == 0) return 0;
    
    int64_t value = 0;
    size_t i = 0;
    bool negative = false;
    
    // Handle sign
    if (str[0] == '-') {
        negative = true;
        i = 1;
    } else if (str[0] == '+') {
        i = 1;
    }
    
    // Parse digits
    for (; i < len; i++) {
        char c = str[i];
        if (c >= '0' && c <= '9') {
            value = value * 10 + (c - '0');
        } else {
            break;  // Stop at non-digit (e.g., decimal point, 'e', etc.)
        }
    }
    
    return negative ? -value : value;
}

// Fast double parsing using fast_float library (2-4x faster than std::stod)
static inline double FastParseDouble(const char* str, size_t len) {
    double result = 0.0;
    auto answer = fast_float::from_chars(str, str + len, result);
    if (answer.ec != std::errc()) {
        // Fallback to stod on error
        return std::stod(std::string(str, len));
    }
    return result;
}

std::vector<ColumnSchema> GetJsonlSchema(const uint8_t* data, size_t size, size_t sample_size) {
    JsonParser parser(data, size);
    std::unordered_map<std::string, JsonType> schema;
    std::vector<std::string> column_order;

    size_t lines_read = 0;
    std::vector<std::tuple<const char*, size_t, const char*, size_t, JsonType, bool>> kvs;

    while (lines_read < sample_size && parser.ParseLineKV(kvs)) {
        for (const auto &ent : kvs) {
            const char* key_ptr; size_t key_len; const char* val_ptr; size_t val_len; JsonType type; bool has_escape;
            std::tie(key_ptr, key_len, val_ptr, val_len, type, has_escape) = ent;
            std::string key(key_ptr, key_len);
            auto it = schema.find(key);
            if (it == schema.end()) {
                schema[key] = type;
                column_order.push_back(key);
            } else {
                it->second = InferType(it->second, type);
            }
        }
        lines_read++;
    }
    
    // Convert to ColumnSchema vector
    std::vector<ColumnSchema> result;
    result.reserve(column_order.size());
    
    for (const auto& col : column_order) {
        ColumnSchema cs;
        cs.name = col;
        cs.type = schema[col];
        cs.nullable = true;  // JSON lines are always nullable
        result.push_back(cs);
    }
    
    return result;
}

JsonlTable ReadJsonl(const uint8_t* data, size_t size, const std::vector<std::string>& requested_columns) {
    JsonlTable table;
    
    // Pre-count lines for memory pre-allocation (5-8% speedup expected)
    size_t estimated_lines = simd::CountNewlines(reinterpret_cast<const char*>(data), size) + 1;
    
    // First, get the schema to know all available columns
    auto schema = GetJsonlSchema(data, size);
    
    if (schema.empty()) {
        table.success = false;
        return table;
    }
    
    // Determine which columns to read
    std::unordered_set<std::string> columns_to_read;
    if (requested_columns.empty()) {
        // Read all columns
        for (const auto& col : schema) {
            columns_to_read.insert(col.name);
        }
        for (const auto& col : schema) {
            table.column_names.push_back(col.name);
        }
    } else {
        // Only read requested columns
        for (const auto& col : requested_columns) {
            columns_to_read.insert(col);
        }
        table.column_names = requested_columns;
    }
    
    // Initialize columns
    table.columns.resize(table.column_names.size());
    for (size_t i = 0; i < table.column_names.size(); i++) {
        auto& col = table.columns[i];
        col.success = true;
        
        // Find the type from schema
        auto it = std::find_if(schema.begin(), schema.end(), 
                              [&](const ColumnSchema& cs) { return cs.name == table.column_names[i]; });
        if (it != schema.end()) {
            switch (it->type) {
                case JsonType::Integer:
                    col.type = "int64";
                    // Pre-allocate vectors based on estimated line count
                    col.int_values.reserve(estimated_lines);
                    col.null_mask.reserve(estimated_lines);
                    break;
                case JsonType::Double:
                    col.type = "double";
                    col.double_values.reserve(estimated_lines);
                    col.null_mask.reserve(estimated_lines);
                    break;
                case JsonType::String:
                    col.type = "string";
                    col.string_values.reserve(estimated_lines);
                    col.null_mask.reserve(estimated_lines);
                    break;
                case JsonType::Boolean:
                    col.type = "boolean";
                    col.boolean_values.reserve(estimated_lines);
                    col.null_mask.reserve(estimated_lines);
                    break;
                default:
                    col.type = "string";
                    col.string_values.reserve(estimated_lines);
                    col.null_mask.reserve(estimated_lines);
            }
        } else {
            // Column not found in schema, mark as unsuccessful
            col.success = false;
        }
    }
    // Build name -> index map for requested columns for O(1) lookup
    std::unordered_map<std::string, size_t> name_to_idx;
    for (size_t i = 0; i < table.column_names.size(); ++i) {
        name_to_idx[table.column_names[i]] = i;
    }

    // Parse all lines and populate columns directly using KV slices
    JsonParser parser(data, size);
    std::vector<std::tuple<const char*, size_t, const char*, size_t, JsonType, bool>> kvs;

    while (parser.ParseLineKV(kvs)) {
        // Prepare row: mark which columns were seen to append nulls later
        std::vector<char> seen(table.columns.size(), 0);

        for (const auto &ent : kvs) {
            const char* key_ptr; size_t key_len; const char* val_ptr; size_t val_len; JsonType type; bool has_escape;
            std::tie(key_ptr, key_len, val_ptr, val_len, type, has_escape) = ent;

            std::string key(key_ptr, key_len);
            auto it = name_to_idx.find(key);
            if (it == name_to_idx.end()) {
                continue; // column not requested
            }

            size_t col_idx = it->second;
            auto &col = table.columns[col_idx];
            seen[col_idx] = 1;

            // Handle explicit JSON null values separately
            if (type == JsonType::Null) {
                // Mark as null and push placeholders so vectors remain aligned
                col.null_mask.push_back(1);
                if (col.type == "int64") col.int_values.push_back(0);
                else if (col.type == "double") col.double_values.push_back(0.0);
                else if (col.type == "string") {
                    col.string_values.emplace_back();
                    col.string_slices.emplace_back(nullptr, 0);
                } else if (col.type == "boolean") col.boolean_values.push_back(0);
            } else {
                // Non-null
                col.null_mask.push_back(0);

                if (col.type == "int64") {
                    // Parse int directly from slice
                    col.int_values.push_back(FastParseInt(val_ptr, val_len));
                } else if (col.type == "double") {
                    col.double_values.push_back(FastParseDouble(val_ptr, val_len));
                } else if (col.type == "string") {
                    if (!has_escape) {
                        // Fast path: store slice pointer & len; materialize later if needed
                        col.string_slices.emplace_back(val_ptr, val_len);
                        // maintain placeholder in string_values for count consistency if needed
                        col.string_values.emplace_back();
                    } else {
                        // Need to unescape and copy now
                        std::string s(val_ptr, val_len);
                        // Basic unescape pass (handles common escapes), this is simplified
                        std::string out;
                        out.reserve(s.size());
                        for (size_t i = 0; i < s.size(); ++i) {
                            if (s[i] == '\\' && i + 1 < s.size()) {
                                ++i;
                                char esc = s[i];
                                switch (esc) {
                                    case '"': out.push_back('"'); break;
                                    case '\\': out.push_back('\\'); break;
                                    case '/': out.push_back('/'); break;
                                    case 'b': out.push_back('\b'); break;
                                    case 'f': out.push_back('\f'); break;
                                    case 'n': out.push_back('\n'); break;
                                    case 'r': out.push_back('\r'); break;
                                    case 't': out.push_back('\t'); break;
                                    default: out.push_back(esc); break;
                                }
                            } else {
                                out.push_back(s[i]);
                            }
                        }
                        col.string_values.push_back(std::move(out));
                        // maintain slice vector length parity
                        col.string_slices.emplace_back(nullptr, 0);
                    }
                } else if (col.type == "boolean") {
                    // compare first letter
                    if (val_len > 0 && val_ptr[0] == 't') col.boolean_values.push_back(1);
                    else col.boolean_values.push_back(0);
                }
            }
        }

        // For columns not seen add nulls/placeholder
        for (size_t i = 0; i < table.columns.size(); ++i) {
            if (!table.columns[i].success) continue;
            if (!seen[i]) {
                auto &col = table.columns[i];
                col.null_mask.push_back(1);
                if (col.type == "int64") col.int_values.push_back(0);
                else if (col.type == "double") col.double_values.push_back(0.0);
                else if (col.type == "string") {
                    col.string_values.emplace_back();
                    col.string_slices.emplace_back(nullptr, 0);
                } else if (col.type == "boolean") col.boolean_values.push_back(0);
            }
        }

        table.num_rows++;
    }

    // Materialize any string slices into string_values so the public API
    // (which expects vector<string>) remains consistent.
    for (size_t ci = 0; ci < table.columns.size(); ++ci) {
        auto &col = table.columns[ci];
        if (col.type != "string") continue;
        // Ensure vectors have same length
        size_t n = col.null_mask.size();
        // If string_values already has entries for escaped ones and empty placeholders
        // fill from string_slices where applicable
        for (size_t i = 0; i < n; ++i) {
            if (i < col.string_values.size() && !col.string_values[i].empty()) continue;
            if (i < col.string_slices.size() && col.string_slices[i].first != nullptr) {
                const char* ptr = col.string_slices[i].first;
                size_t len = col.string_slices[i].second;
                col.string_values[i].assign(ptr, len);
            } else {
                // leave empty string for nulls or placeholders
            }
        }
        // Clear slices to free any incidental references (not owning though)
        col.string_slices.clear();
    }
    
    table.success = true;
    return table;
}

JsonlTable ReadJsonl(const uint8_t* data, size_t size) {
    return ReadJsonl(data, size, {});
}
