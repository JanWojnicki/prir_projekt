#include "common/compute.hpp"
#include "common/io.hpp"
#include <chrono>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <omp.h>
int main(int argc, char** argv) {
    try {
        const auto options = c05::parse_options(argc, argv);
        if (options.help) { c05::print_usage(argv[0]); return 0; }
        if (options.mode != "naive") throw std::invalid_argument("OpenMP supports --mode naive");
        if (options.threads) omp_set_num_threads(options.threads);
        using Clock = std::chrono::steady_clock;
        const auto total_start = Clock::now();
        const auto bytes = c05::read_binary(options.input);
        const auto layout = c05::window_layout(bytes.size(), options.window, options.step);
        if (layout.count > static_cast<std::size_t>(std::numeric_limits<std::ptrdiff_t>::max()))
            throw std::runtime_error("Too many windows for OpenMP loop");
        c05::Results results;
        results.entropy.resize(layout.count);
        const auto core_start = Clock::now();
        #pragma omp parallel
        {
            c05::Histogram histogram{};
            #pragma omp for schedule(static)
            for (std::ptrdiff_t i = 0; i < static_cast<std::ptrdiff_t>(layout.count); ++i) {
                histogram.fill(0);
                const auto offset = static_cast<std::size_t>(i) * options.step;
                for (std::size_t j = 0; j < options.window; ++j) ++histogram[bytes[offset + j]];
                results.entropy[static_cast<std::size_t>(i)] =
                    c05::shannon_entropy(histogram, options.window);
            }
        }
        const auto core_end = Clock::now();
        results.boundaries = c05::detect_boundaries(results.entropy, options.step, options.threshold);
        c05::write_csv(options.output, results.entropy, options.step, options.threshold);
        const auto total_end = Clock::now();
        c05::report_layout(bytes.size(), options);
        c05::report_timing("openmp", options, layout.count, results.boundaries.size(),
            std::chrono::duration<double>(core_end - core_start).count(),
            std::chrono::duration<double>(total_end - total_start).count());
        return 0;
    } catch (const std::exception& e) { std::cerr << "Error: " << e.what() << '\n'; return 1; }
}
