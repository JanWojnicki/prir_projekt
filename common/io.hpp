#pragma once
#include "common/types.hpp"
#include <span>
#include <string_view>
namespace c05 {
Options parse_options(int argc, char** argv);
void print_usage(std::string_view executable);
std::vector<std::uint8_t> read_binary(const std::filesystem::path& path);
WindowLayout window_layout(std::size_t bytes, std::size_t window, std::size_t step);
std::vector<Boundary> detect_boundaries(std::span<const double> entropy,
                                      std::size_t step, double threshold);
// Merges runs of consecutive flagged windows into single change events.
std::vector<BoundaryEvent> merge_boundaries(std::span<const Boundary> boundaries,
                                            std::span<const double> entropy,
                                            std::size_t window, std::size_t step);
void write_csv(const std::filesystem::path& path, std::span<const double> entropy,
               std::size_t step, double threshold);
void write_events_csv(const std::filesystem::path& path, std::span<const BoundaryEvent> events);
// Writes the optional events file (if requested); returns the number of merged events.
std::size_t write_events_if_requested(const Options& options, std::span<const Boundary> boundaries,
                                      std::span<const double> entropy);
void report_layout(std::size_t bytes, const Options& options);
void report_timing(std::string_view backend, const Options& options,
                   std::size_t windows, std::size_t boundaries, std::size_t events,
                   double core_seconds, double total_seconds);
}
