#pragma once
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>
namespace c05 {
struct Boundary {
    std::size_t window_index;
    std::size_t byte_offset;
    double entropy_prev;
    double entropy_curr;
    double delta;
};
struct Options {
    std::filesystem::path input;
    std::filesystem::path output;
    std::size_t window = 0;
    std::size_t step = 0;
    double threshold = 0;
    int threads = 0;
    std::string mode = "naive";
    bool help = false;
};
struct WindowLayout {
    std::size_t count;
    std::size_t trailing_bytes;
    std::size_t uncovered_gap_bytes;
};
struct Results {
    std::vector<double> entropy;
    std::vector<Boundary> boundaries;
};
}
