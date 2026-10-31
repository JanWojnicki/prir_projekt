#include "common/compute.hpp"
#include <cmath>
#include <stdexcept>
namespace c05 {
double shannon_entropy(const Histogram& histogram, std::size_t window) {
    double entropy = 0;
    const double denominator = static_cast<double>(window);
    for (const auto count : histogram) {
        if (count != 0) {
            const double p = static_cast<double>(count) / denominator;
            entropy -= p * std::log2(p);
        }
    }
    return entropy;
}
double window_entropy(std::span<const std::uint8_t> bytes) {
    Histogram histogram{};
    for (const auto byte : bytes) ++histogram[byte];
    return shannon_entropy(histogram, bytes.size());
}
void compute_naive(std::span<const std::uint8_t> bytes, std::size_t window,
                   std::size_t step, std::span<double> output) {
    for (std::size_t i = 0; i < output.size(); ++i)
        output[i] = window_entropy(bytes.subspan(i * step, window));
}
void compute_incremental(std::span<const std::uint8_t> bytes, std::size_t window,
                         std::size_t step, std::span<double> output) {
    if (output.empty()) return;
    Histogram histogram{};
    for (std::size_t j = 0; j < window; ++j) ++histogram[bytes[j]];
    output[0] = shannon_entropy(histogram, window);
    for (std::size_t i = 1; i < output.size(); ++i) {
        const auto old_start = (i - 1) * step;
        const auto new_start = i * step;
        if (step < window) {
            for (std::size_t j = 0; j < step; ++j) {
                --histogram[bytes[old_start + j]];
                ++histogram[bytes[old_start + window + j]];
            }
        } else {
            histogram.fill(0);
            for (std::size_t j = 0; j < window; ++j) ++histogram[bytes[new_start + j]];
        }
        output[i] = shannon_entropy(histogram, window);
    }
}
void compute_mode(const std::string& mode, std::span<const std::uint8_t> bytes,
                  std::size_t window, std::size_t step, std::span<double> output) {
    if (mode == "naive") compute_naive(bytes, window, step, output);
    else if (mode == "incremental") compute_incremental(bytes, window, step, output);
    else throw std::invalid_argument("Unknown mode: " + mode);
}
}
