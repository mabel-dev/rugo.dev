#include "jsonl_reader.hpp"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <unordered_set>

// Fast JSON parser optimized for JSON lines format
class JsonParser {
public:
    JsonParser(const uint8_t* data, size_t size) 
        : data_(reinterpret_cast<const char*>(data)), 
          size_(size), 
          pos_(0) {}

    // Parse a single JSON line and return key-value pairs
    bool ParseLine(std::unordered_map<std::string, std::pair<JsonType, std::string>>& result) {
        result.clear();
        
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
            std::string key;
            if (!ParseString(key)) {
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
            std::string value;
            if (!ParseValue(type, value)) {
                SkipToNextLine();
                return false;
            }
            
            result[key] = {type, value};
            
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
        while (pos_ < size_ && data_[pos_] != '\n') pos_++;
        if (pos_ < size_) pos_++;  // Skip newline
    }
    
    bool ParseString(std::string& result) {
        result.clear();
        
        if (pos_ >= size_ || data_[pos_] != '"') return false;
        pos_++;
        
        while (pos_ < size_) {
            char c = data_[pos_];
            
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
    
    bool ParseValue(JsonType& type, std::string& value) {
        if (pos_ >= size_) return false;
        
        char c = data_[pos_];
        
        // Null
        if (c == 'n' && pos_ + 3 < size_ && 
            data_[pos_+1] == 'u' && data_[pos_+2] == 'l' && data_[pos_+3] == 'l') {
            type = JsonType::Null;
            value = "";
            pos_ += 4;
            return true;
        }
        
        // Boolean true
        if (c == 't' && pos_ + 3 < size_ &&
            data_[pos_+1] == 'r' && data_[pos_+2] == 'u' && data_[pos_+3] == 'e') {
            type = JsonType::Boolean;
            value = "true";
            pos_ += 4;
            return true;
        }
        
        // Boolean false
        if (c == 'f' && pos_ + 4 < size_ &&
            data_[pos_+1] == 'a' && data_[pos_+2] == 'l' && 
            data_[pos_+3] == 's' && data_[pos_+4] == 'e') {
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

std::vector<ColumnSchema> GetJsonlSchema(const uint8_t* data, size_t size, size_t sample_size) {
    JsonParser parser(data, size);
    std::unordered_map<std::string, std::pair<JsonType, std::string>> row;
    std::unordered_map<std::string, JsonType> schema;
    std::vector<std::string> column_order;
    
    size_t lines_read = 0;
    
    while (lines_read < sample_size && parser.ParseLine(row)) {
        for (const auto& [key, value_pair] : row) {
            auto it = schema.find(key);
            if (it == schema.end()) {
                schema[key] = value_pair.first;
                column_order.push_back(key);
            } else {
                it->second = InferType(it->second, value_pair.first);
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
                    break;
                case JsonType::Double:
                    col.type = "double";
                    break;
                case JsonType::String:
                    col.type = "string";
                    break;
                case JsonType::Boolean:
                    col.type = "boolean";
                    break;
                default:
                    col.type = "string";
            }
        } else {
            // Column not found in schema, mark as unsuccessful
            col.success = false;
        }
    }
    
    // Parse all lines and populate columns
    JsonParser parser(data, size);
    std::unordered_map<std::string, std::pair<JsonType, std::string>> row;
    
    while (parser.ParseLine(row)) {
        for (size_t i = 0; i < table.column_names.size(); i++) {
            const auto& col_name = table.column_names[i];
            auto& col = table.columns[i];
            
            if (!col.success) continue;
            
            auto it = row.find(col_name);
            if (it == row.end() || it->second.first == JsonType::Null) {
                // Null value
                col.null_mask.push_back(1);
                
                // Add placeholder value
                if (col.type == "int64") {
                    col.int_values.push_back(0);
                } else if (col.type == "double") {
                    col.double_values.push_back(0.0);
                } else if (col.type == "string") {
                    col.string_values.push_back("");
                } else if (col.type == "boolean") {
                    col.boolean_values.push_back(0);
                }
            } else {
                // Non-null value
                col.null_mask.push_back(0);
                
                const auto& [type, value] = it->second;
                
                if (col.type == "int64") {
                    col.int_values.push_back(std::stoll(value));
                } else if (col.type == "double") {
                    col.double_values.push_back(std::stod(value));
                } else if (col.type == "string") {
                    col.string_values.push_back(value);
                } else if (col.type == "boolean") {
                    col.boolean_values.push_back(value == "true" ? 1 : 0);
                }
            }
        }
        table.num_rows++;
    }
    
    table.success = true;
    return table;
}

JsonlTable ReadJsonl(const uint8_t* data, size_t size) {
    return ReadJsonl(data, size, {});
}
