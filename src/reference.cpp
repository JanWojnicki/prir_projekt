// Sequential reference: one thread, naive or incremental histogram.
#include "common/compute.hpp"
#include "common/io.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <vector>
int main(int argc, char** argv) {
    try {
        const auto options = c05::parse_options(argc, argv);
        if (options.help) { c05::print_usage(argv[0]); return 0; }
        if (options.threads > 1) throw std::invalid_argument("Reference is single-threaded");
        using Clock = std::chrono::steady_clock;
        const auto total_start = Clock::now();
        const auto bytes = c05::read_binary(options.input);
        const auto layout = c05::window_layout(bytes.size(), options.window, options.step);
        std::vector<double> entropy(layout.count);
        const auto core_start = Clock::now();
        c05::compute_mode(options.mode, bytes, options.window, options.step, entropy);
        const auto core_end = Clock::now();
        const auto boundaries = c05::detect_boundaries(entropy, options.threshold);
        const auto events = c05::write_outputs(options, entropy, boundaries);
        const auto total_end = Clock::now();
        c05::report_layout(bytes.size(), options);
        c05::report_timing("reference", options, layout.count, boundaries.size(), events,
            std::chrono::duration<double>(core_end - core_start).count(),
            std::chrono::duration<double>(total_end - total_start).count());
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << '\n';
        return 1;
    }
}
