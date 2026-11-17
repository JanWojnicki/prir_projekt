// OpenMP backend. Windows are distributed among threads; every thread owns a private
// 256-bin histogram, so no shared counter is touched per byte and no atomics are needed.
#include "common/compute.hpp"
#include "common/io.hpp"
#include <chrono>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>
#include <omp.h>
int main(int argc, char** argv) {
    try {
        const auto options = c05::parse_options(argc, argv);
        if (options.help) { c05::print_usage(argv[0]); return 0; }
        if (options.threads) omp_set_num_threads(options.threads);
        using Clock = std::chrono::steady_clock;
        const auto total_start = Clock::now();
        const auto bytes = c05::read_binary(options.input);
        const auto layout = c05::window_layout(bytes.size(), options.window, options.step);
        if (layout.count > static_cast<std::size_t>(std::numeric_limits<std::ptrdiff_t>::max()))
            throw std::runtime_error("Too many windows for OpenMP loop");
        std::vector<double> entropy(layout.count);
        const std::span<const std::uint8_t> data(bytes);
        const std::span<double> output(entropy);
        int used_threads = 1;
        const auto core_start = Clock::now();
        if (options.mode == c05::Mode::Naive) {
            #pragma omp parallel
            {
                #pragma omp single
                used_threads = omp_get_num_threads();
                // window_entropy keeps its histogram on the calling thread's stack.
                #pragma omp for schedule(static)
                for (std::ptrdiff_t i = 0; i < static_cast<std::ptrdiff_t>(layout.count); ++i) {
                    const auto index = static_cast<std::size_t>(i);
                    output[index] = c05::window_entropy(data.subspan(index * options.step, options.window));
                }
            }
        } else {
            // Incremental: each thread takes one contiguous range of windows, builds the
            // histogram of its first window and then slides it. Ranges differ by <= 1 window.
            #pragma omp parallel
            {
                const auto threads = static_cast<std::size_t>(omp_get_num_threads());
                #pragma omp single
                used_threads = static_cast<int>(threads);
                const auto range = c05::block_range(layout.count, threads,
                                                    static_cast<std::size_t>(omp_get_thread_num()));
                if (range.count)
                    c05::compute_incremental(data.subspan(range.first * options.step), options.window,
                                             options.step, output.subspan(range.first, range.count));
            }
        }
        const auto core_end = Clock::now();
        const auto boundaries = c05::detect_boundaries(entropy, options.threshold);
        const auto events = c05::write_outputs(options, entropy, boundaries);
        const auto total_end = Clock::now();
        c05::report_layout(bytes.size(), options);
        c05::report_timing("openmp", options, layout.count, boundaries.size(), events,
            std::chrono::duration<double>(core_end - core_start).count(),
            std::chrono::duration<double>(total_end - total_start).count());
        std::cerr << "omp_threads=" << used_threads << '\n';
        return 0;
    } catch (const std::exception& e) { std::cerr << "Error: " << e.what() << '\n'; return 1; }
}
