#include "common/compute.hpp"
#include "common/io.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>
namespace c05 {
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
int run_reference(int argc, char** argv) {
    try {
        const auto options = parse_options(argc, argv);
        if (options.help) { print_usage(argv[0]); return 0; }
        if (options.threads > 1) throw std::invalid_argument("Reference is single-threaded");
        using Clock = std::chrono::steady_clock;
        const auto total_start = Clock::now();
        const auto bytes = read_binary(options.input);
        const auto layout = window_layout(bytes.size(), options.window, options.step);
        Results results;
        results.entropy.resize(layout.count);
        const auto core_start = Clock::now();
        if (options.mode == "naive")
            compute_naive(bytes, options.window, options.step, results.entropy);
        else compute_incremental(bytes, options.window, options.step, results.entropy);
        const auto core_end = Clock::now();
        results.boundaries = detect_boundaries(results.entropy, options.step, options.threshold);
        write_csv(options.output, results.entropy, options.step, options.threshold);
        const auto total_end = Clock::now();
        report_layout(bytes.size(), options);
        report_timing("reference", options, layout.count, results.boundaries.size(),
            std::chrono::duration<double>(core_end - core_start).count(),
            std::chrono::duration<double>(total_end - total_start).count());
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';
        return 1;
    }
}
}
int main(int argc, char** argv) {
    return c05::run_reference(argc, argv);
}
