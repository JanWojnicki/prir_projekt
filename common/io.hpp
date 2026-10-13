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
void write_csv(const std::filesystem::path& path, std::span<const double> entropy,
               std::size_t step, double threshold);
void report_layout(std::size_t bytes, const Options& options);
void report_timing(std::string_view backend, const Options& options,
                   std::size_t windows, std::size_t boundaries,
                   double core_seconds, double total_seconds);
}
