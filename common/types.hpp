#pragma once
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>
namespace c05 {
// One window whose signed entropy delta to the previous window satisfies |delta| >= T.
struct Boundary {
    std::size_t window_index;
    std::size_t byte_offset;
    double entropy_prev;
    double entropy_curr;
    double delta;
};
// A maximal run of consecutive flagged windows, reported as one entropy change.
struct BoundaryEvent {
    std::size_t first_window;     // first flagged window index
    std::size_t last_window;      // last flagged window index
    std::size_t region_start;     // start of window first_window-1 (last stable window)
    std::size_t region_end;       // end (exclusive) of window last_window
    std::size_t estimated_offset; // midpoint of [region_start, region_end)
    std::size_t peak_window;      // flagged window with the largest |delta|
    double peak_delta;
    double entropy_before;        // entropy of window first_window-1
    double entropy_after;         // entropy of window last_window
};
struct Options {
    std::filesystem::path input;
    std::filesystem::path output;
    std::filesystem::path events; // optional list of merged changes
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
