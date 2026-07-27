#include "solvita_ogc.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

using solvita::ogc::Json;

struct Event {
  int time;
  bool entry;
  int block;
  int bay;
  int x = 0;
  int y = 0;
  int orient = 0;
};

int main() {
  const Json problem = solvita::ogc::read_stdin();
  const auto &blocks = problem.at("blocks").as_array();
  const int bay_count = static_cast<int>(problem.at("bays").as_array().size());
  std::vector<int> available(bay_count, 0);
  std::vector<Event> events;

  // Run at most one block at a time in each bay.  This is deliberately
  // conservative: no two footprints overlap and every crane path is empty.
  for (int id = 0; id < static_cast<int>(blocks.size()); ++id) {
    const Json &block = blocks[id];
    const auto &preferences = block.at("bay_preferences").as_array();
    int bay = -1, orient = 0, x = 0, y = 0;
    double best_preference = -std::numeric_limits<double>::infinity();
    const auto &orientations = block.at("shape").as_array();
    for (int candidate_bay = 0; candidate_bay < bay_count; ++candidate_bay) {
      const Json &bay_data = problem.at("bays").at(candidate_bay);
      const double width = bay_data.at("width").number();
      const double height = bay_data.at("height").number();
      for (int oi = 0; oi < static_cast<int>(orientations.size()); ++oi) {
        const auto &layers = orientations[oi].at("layers").as_array();
        double min_x = 0, min_y = 0, max_x = 0, max_y = 0;
        for (const Json &layer : layers)
          for (const Json &vertex : layer.as_array()) {
            min_x = std::min(min_x, vertex.at(0).number());
            min_y = std::min(min_y, vertex.at(1).number());
            max_x = std::max(max_x, vertex.at(0).number());
            max_y = std::max(max_y, vertex.at(1).number());
          }
        const int candidate_x = static_cast<int>(std::ceil(-min_x));
        const int candidate_y = static_cast<int>(std::ceil(-min_y));
        if (candidate_x + max_x <= width + 1e-9 &&
            candidate_y + max_y <= height + 1e-9 &&
            preferences[candidate_bay].number() > best_preference) {
          bay = candidate_bay;
          orient = oi;
          x = candidate_x;
          y = candidate_y;
          best_preference = preferences[candidate_bay].number();
        }
      }
    }
    if (bay < 0) return 2;  // Invalid problem: no orientation fits any bay.
    const int release = block.at("release_time").integer();
    const int processing = block.at("processing_time").integer();
    const int start = std::max(release, available[bay]);
    const int finish = start + processing;
    available[bay] = finish;
    events.push_back({start, true, id, bay, x, y, orient});
    events.push_back({finish, false, id, bay});
  }
  std::sort(events.begin(), events.end(), [](const Event &a, const Event &b) {
    if (a.time != b.time) return a.time < b.time;
    if (a.entry != b.entry) return !a.entry;  // EXIT before ENTRY.
    return a.block < b.block;
  });

  std::cout << "{\"operations\":{";
  bool first_time = true;
  for (std::size_t i = 0; i < events.size();) {
    std::size_t j = i;
    if (!first_time) std::cout << ',';
    first_time = false;
    std::cout << '"' << events[i].time << "\":[";
    bool first_event = true;
    while (j < events.size() && events[j].time == events[i].time) {
      if (!first_event) std::cout << ',';
      first_event = false;
      const Event &e = events[j++];
      if (e.entry)
        std::cout << "{\"type\":\"ENTRY\",\"block_id\":" << e.block
                  << ",\"bay_id\":" << e.bay
                  << ",\"x\":" << e.x << ",\"y\":" << e.y
                  << ",\"orient_idx\":" << e.orient << '}';
      else
        std::cout << "{\"type\":\"EXIT\",\"block_id\":" << e.block
                  << ",\"bay_id\":" << e.bay << '}';
    }
    std::cout << ']';
    i = j;
  }
  std::cout << "}}\n";
}
