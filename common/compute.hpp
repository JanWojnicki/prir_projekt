#pragma once
#include <array>
#include <span>
#include "common/types.hpp"
namespace c05 {
using Histogram = std::array<std::uint32_t, 256>;
double shannon_entropy(const Histogram& histogram, std::size_t window);
double window_entropy(std::span<const std::uint8_t> bytes);
void compute_naive(std::span<const std::uint8_t> bytes, std::size_t window,
                   std::size_t step, std::span<double> output);
void compute_incremental(std::span<const std::uint8_t> bytes, std::size_t window,
                         std::size_t step, std::span<double> output);
int run_reference(int argc, char** argv);
}
