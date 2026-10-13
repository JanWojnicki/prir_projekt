#include "common/compute.hpp"
#include "common/io.hpp"
#include <chrono>
#include <cmath>
#include <iostream>
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
}
