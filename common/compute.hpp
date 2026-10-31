#pragma once
#include <array>
#include <span>
#include "common/types.hpp"
namespace c05 {
using Histogram = std::array<std::uint32_t, 256>;
// Shannon entropy in bits/byte; bins with zero probability are skipped.
double shannon_entropy(const Histogram& histogram, std::size_t window);
double window_entropy(std::span<const std::uint8_t> bytes);
// Both functions treat bytes[0] as the start of window 0 and fill output.size() windows.
// The caller guarantees bytes.size() >= (output.size()-1)*step + window.
void compute_naive(std::span<const std::uint8_t> bytes, std::size_t window,
                   std::size_t step, std::span<double> output);
// Sliding histogram: for S < W the update removes S leaving bytes and adds S entering
// bytes; for S >= W windows do not overlap and the histogram is rebuilt.
void compute_incremental(std::span<const std::uint8_t> bytes, std::size_t window,
                         std::size_t step, std::span<double> output);
// Dispatches on Options::mode ("naive" or "incremental").
void compute_mode(const std::string& mode, std::span<const std::uint8_t> bytes,
                  std::size_t window, std::size_t step, std::span<double> output);
}
