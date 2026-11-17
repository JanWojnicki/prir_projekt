#pragma once
#include "common/types.hpp"
#include <span>
#include <string_view>
#include <vector>
namespace c05 {
Options parse_options(int argc, char** argv);
void print_usage(std::string_view executable);
std::vector<std::uint8_t> read_binary(const std::filesystem::path& path);
WindowLayout window_layout(std::size_t bytes, std::size_t window, std::size_t step);
// Splits `count` windows into `parts` contiguous ranges whose sizes differ by <= 1
// and returns the range of part `index` (used by OpenMP threads and MPI ranks).
WindowRange block_range(std::size_t count, std::size_t parts, std::size_t index);
// The only place where the threshold is applied: window i >= 1 is flagged iff
// |H[i] - H[i-1]| >= threshold. Boundaries are returned in increasing window order.
std::vector<Boundary> detect_boundaries(std::span<const double> entropy, double threshold);
// Merges runs of consecutive flagged windows into single change events.
std::vector<BoundaryEvent> merge_boundaries(std::span<const Boundary> boundaries,
                                            std::span<const double> entropy,
                                            std::size_t window, std::size_t step);
void write_csv(const std::filesystem::path& path, std::span<const double> entropy,
               std::size_t step, std::span<const Boundary> boundaries);
void write_events_csv(const std::filesystem::path& path, std::span<const BoundaryEvent> events);
// Writes --output and, if requested, --events. Returns the number of merged events.
std::size_t write_outputs(const Options& options, std::span<const double> entropy,
                          std::span<const Boundary> boundaries);
void report_layout(std::size_t bytes, const Options& options);
void report_timing(std::string_view backend, const Options& options,
                   std::size_t windows, std::size_t boundaries, std::size_t events,
                   double core_seconds, double total_seconds);
}
