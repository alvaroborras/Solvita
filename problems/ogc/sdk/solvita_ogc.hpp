#pragma once

// Immutable public SDK for OGC candidates.  This intentionally implements only
// JSON parsing/serialization and the Solvita environment contract; scoring is
// trusted Python code and is never linked into candidate containers.
#include <cctype>
#include <cstdlib>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace solvita::ogc {

struct Json {
  using array = std::vector<Json>;
  using object = std::map<std::string, Json>;
  std::variant<std::nullptr_t, bool, double, std::string, array, object> value;

  Json() : value(nullptr) {}
  Json(double v) : value(v) {}
  Json(std::string v) : value(std::move(v)) {}
  Json(array v) : value(std::move(v)) {}
  Json(object v) : value(std::move(v)) {}

  const Json &at(const std::string &key) const {
    return std::get<object>(value).at(key);
  }
  const Json &at(std::size_t index) const {
    return std::get<array>(value).at(index);
  }
  const array &as_array() const { return std::get<array>(value); }
  const object &as_object() const { return std::get<object>(value); }
  double number() const { return std::get<double>(value); }
  int integer() const { return static_cast<int>(number()); }
};

class Parser {
 public:
  explicit Parser(std::string input) : input_(std::move(input)) {}
  Json parse() {
    Json result = parse_value();
    whitespace();
    if (position_ != input_.size()) fail("trailing input");
    return result;
  }

 private:
  std::string input_;
  std::size_t position_ = 0;

  [[noreturn]] void fail(const char *message) const {
    throw std::runtime_error(std::string("JSON ") + message + " at byte " +
                             std::to_string(position_));
  }
  void whitespace() {
    while (position_ < input_.size() &&
           std::isspace(static_cast<unsigned char>(input_[position_])))
      ++position_;
  }
  char take() {
    if (position_ >= input_.size()) fail("unexpected end");
    return input_[position_++];
  }
  bool consume(char expected) {
    whitespace();
    if (position_ < input_.size() && input_[position_] == expected) {
      ++position_;
      return true;
    }
    return false;
  }
  Json parse_value() {
    whitespace();
    if (position_ >= input_.size()) fail("missing value");
    const char c = input_[position_];
    if (c == '{') return parse_object();
    if (c == '[') return parse_array();
    if (c == '"') return Json(parse_string());
    if (c == 't') return literal("true", Json::object{{"$bool", Json(1.0)}});
    if (c == 'f') return literal("false", Json::object{{"$bool", Json(0.0)}});
    if (c == 'n') return literal("null", Json());
    return Json(parse_number());
  }
  Json literal(const char *word, Json value) {
    const std::string literal_value(word);
    if (input_.substr(position_, literal_value.size()) != literal_value)
      fail("invalid literal");
    position_ += literal_value.size();
    return value;
  }
  std::string parse_string() {
    if (take() != '"') fail("expected string");
    std::string result;
    while (position_ < input_.size()) {
      char c = take();
      if (c == '"') return result;
      if (c != '\\') {
        result.push_back(c);
        continue;
      }
      char escaped = take();
      switch (escaped) {
        case '"': case '\\': case '/': result.push_back(escaped); break;
        case 'b': result.push_back('\b'); break;
        case 'f': result.push_back('\f'); break;
        case 'n': result.push_back('\n'); break;
        case 'r': result.push_back('\r'); break;
        case 't': result.push_back('\t'); break;
        default: fail("unsupported escape");
      }
    }
    fail("unterminated string");
  }
  double parse_number() {
    whitespace();
    const char *begin = input_.c_str() + position_;
    char *end = nullptr;
    double value = std::strtod(begin, &end);
    if (end == begin) fail("invalid number");
    position_ = static_cast<std::size_t>(end - input_.c_str());
    return value;
  }
  Json parse_array() {
    take();
    Json::array result;
    if (consume(']')) return Json(std::move(result));
    do result.push_back(parse_value()); while (consume(','));
    if (!consume(']')) fail("expected ]");
    return Json(std::move(result));
  }
  Json parse_object() {
    take();
    Json::object result;
    if (consume('}')) return Json(std::move(result));
    do {
      whitespace();
      std::string key = parse_string();
      if (!consume(':')) fail("expected :");
      result.emplace(std::move(key), parse_value());
    } while (consume(','));
    if (!consume('}')) fail("expected }");
    return Json(std::move(result));
  }
};

inline Json read_stdin() {
  return Parser(std::string(std::istreambuf_iterator<char>(std::cin),
                            std::istreambuf_iterator<char>()))
      .parse();
}

inline long long seed() {
  const char *value = std::getenv("SOLVITA_SEED");
  return value ? std::strtoll(value, nullptr, 10) : 0;
}

inline long long time_limit_ms() {
  const char *value = std::getenv("SOLVITA_TIME_LIMIT_MS");
  return value ? std::strtoll(value, nullptr, 10) : 10000;
}

}  // namespace solvita::ogc
