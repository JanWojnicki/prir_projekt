#include "common/io.hpp"
#include <cuda_runtime.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
void check_cuda(cudaError_t code, const char* expression, const char* file, int line) {
    if (code != cudaSuccess)
        throw std::runtime_error(std::string(file) + ":" + std::to_string(line) +
            " " + expression + ": " + cudaGetErrorString(code));
}
#define CHECK_CUDA(expression) check_cuda((expression), #expression, __FILE__, __LINE__)
void cleanup_error(cudaError_t code, const char* operation) noexcept {
    if (code != cudaSuccess)
        std::cerr << "CUDA cleanup error: " << operation << ": "
                  << cudaGetErrorString(code) << '\n';
}
template<class T> class DeviceBuffer {
    T* pointer_ = nullptr;
public:
    explicit DeviceBuffer(std::size_t count) {
        if (count > std::numeric_limits<std::size_t>::max() / sizeof(T))
            throw std::overflow_error("Device allocation size overflow");
        if (count) CHECK_CUDA(cudaMalloc(reinterpret_cast<void**>(&pointer_), count * sizeof(T)));
    }
    ~DeviceBuffer() { if (pointer_) cleanup_error(cudaFree(pointer_), "cudaFree"); }
    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;
    T* data() const noexcept { return pointer_; }
    void release() {
        if (pointer_) { CHECK_CUDA(cudaFree(pointer_)); pointer_ = nullptr; }
    }
};
class Event {
    cudaEvent_t event_{};
public:
    Event() { CHECK_CUDA(cudaEventCreate(&event_)); }
    ~Event() { if (event_) cleanup_error(cudaEventDestroy(event_), "cudaEventDestroy"); }
    Event(const Event&) = delete;
    Event& operator=(const Event&) = delete;
    cudaEvent_t get() const noexcept { return event_; }
    void release() {
        if (event_) { CHECK_CUDA(cudaEventDestroy(event_)); event_ = nullptr; }
    }
};
struct Measurement { double wall_seconds = 0; double event_seconds = 0; };
template<class Function>
Measurement measure(Event& start, Event& stop, Function&& function) {
    CHECK_CUDA(cudaDeviceSynchronize());
    const auto begin = Clock::now();
    CHECK_CUDA(cudaEventRecord(start.get(), 0));
    function();
    CHECK_CUDA(cudaEventRecord(stop.get(), 0));
    CHECK_CUDA(cudaDeviceSynchronize());
    const auto end = Clock::now();
    CHECK_CUDA(cudaEventSynchronize(stop.get()));
    float milliseconds = 0;
    CHECK_CUDA(cudaEventElapsedTime(&milliseconds, start.get(), stop.get()));
    return {std::chrono::duration<double>(end - begin).count(),
            static_cast<double>(milliseconds) / 1000.0};
}
}

// Every block owns one window at a time. All threads take every barrier.
__global__ void histogram_entropy_kernel(const std::uint8_t* data,
    std::size_t window, std::size_t step, std::size_t count, double* d_entropy) {
    __shared__ unsigned int s_hist[256];
    __shared__ double s_terms[256];
    const unsigned int thread = threadIdx.x;
    for (std::size_t index = blockIdx.x; index < count;) {
        for (unsigned int bin = thread; bin < 256; bin += blockDim.x)
            s_hist[bin] = 0;
        __syncthreads();
        const std::size_t offset = index * step;
        for (std::size_t j = thread; j < window; j += blockDim.x)
            atomicAdd(&s_hist[data[offset + j]], 1U);
        __syncthreads();
        for (unsigned int bin = thread; bin < 256; bin += blockDim.x) {
            const unsigned int c = s_hist[bin];
            if (c == 0) s_terms[bin] = 0.0;
            else {
                const double p = static_cast<double>(c) / static_cast<double>(window);
                s_terms[bin] = -p * log2(p);
            }
        }
        __syncthreads();
        for (unsigned int stride = 128; stride > 0; stride >>= 1) {
            for (unsigned int bin = thread; bin < stride; bin += blockDim.x)
                s_terms[bin] += s_terms[bin + stride];
            __syncthreads();
        }
        if (thread == 0) d_entropy[index] = s_terms[0];
        __syncthreads();
        // Avoid overflow even when size_t is near its maximum.
        if (count - index <= static_cast<std::size_t>(gridDim.x)) break;
        index += gridDim.x;
    }
}

__global__ void boundary_flags_kernel(const double* d_entropy,
    std::size_t count, double threshold, std::uint8_t* d_flags) {
    std::size_t index = static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    const std::size_t stride = static_cast<std::size_t>(gridDim.x) * blockDim.x;
    while (index < count) {
        d_flags[index] = static_cast<std::uint8_t>(index != 0 &&
            fabs(d_entropy[index] - d_entropy[index - 1]) >= threshold);
        if (count - index <= stride) break;
        index += stride;
    }
}

namespace {
void write_gpu_csv(const std::filesystem::path& path,
    const std::vector<double>& entropy, const std::vector<std::uint8_t>& flags,
    std::size_t step) {
    if (entropy.size() != flags.size()) throw std::logic_error("Result sizes differ");
    std::ofstream output(path, std::ios::trunc);
    if (!output) throw std::runtime_error("Cannot open output: " + path.string());
    output.imbue(std::locale::classic());
    output << "offset,entropy,delta,is_boundary\n" << std::setprecision(17);
    for (std::size_t i = 0; i < entropy.size(); ++i) {
        const double delta = i == 0 ? 0.0 : entropy[i] - entropy[i - 1];
        output << i * step << ',' << entropy[i] << ',' << delta << ','
               << static_cast<unsigned int>(flags[i]) << '\n';
    }
    output.flush();
    if (!output) throw std::runtime_error("CSV write failed");
    output.close();
    if (!output) throw std::runtime_error("CSV close failed");
}
unsigned int grid_size(std::size_t desired, const cudaDeviceProp& device) {
    return static_cast<unsigned int>(std::min<std::size_t>(desired,
        static_cast<std::size_t>(device.maxGridSize[0])));
}
}

int main(int argc, char** argv) {
    try {
        const auto options = c05::parse_options(argc, argv);
        if (options.help) {
            c05::print_usage(argv[0]);
            std::cout << "CUDA: --mode naive; --threads means threads per block, "
                         "one of 64,128,256,512,1024 (default 256).\n";
            return 0;
        }
        if (options.mode != "naive")
            throw std::invalid_argument("CUDA requires --mode naive (shared atomic histogram)");
        const int threads = options.threads == 0 ? 256 : options.threads;
        if (threads < 64 || threads > 1024 || (threads & (threads - 1)) != 0)
            throw std::invalid_argument("--threads must be 64,128,256,512 or 1024");
        const auto total_start = Clock::now();
        const auto read_start = Clock::now();
        const auto bytes = c05::read_binary(options.input);
        const double read_seconds = std::chrono::duration<double>(Clock::now() - read_start).count();
        const auto layout = c05::window_layout(bytes.size(), options.window, options.step);
        std::vector<double> entropy(layout.count);
        std::vector<std::uint8_t> flags(layout.count);
        std::vector<c05::Boundary> boundaries;
        Measurement h2d, kernel, detection, d2h;
        double setup_seconds = 0, cleanup_seconds = 0;
        std::string device_name = "not used (no complete windows)";
        if (layout.count != 0) {
            const auto setup_start = Clock::now();
            int device_id = 0;
            CHECK_CUDA(cudaGetDevice(&device_id));
            cudaDeviceProp device{};
            CHECK_CUDA(cudaGetDeviceProperties(&device, device_id));
            if (threads > device.maxThreadsPerBlock)
                throw std::invalid_argument("Threads exceed device limit");
            if (device.maxGridSize[0] <= 0) throw std::runtime_error("Invalid CUDA grid limit");
            device_name = device.name;
            DeviceBuffer<std::uint8_t> d_bytes(bytes.size());
            DeviceBuffer<double> d_entropy(layout.count);
            DeviceBuffer<std::uint8_t> d_flags(layout.count);
            Event eventStart, eventStop;
            CHECK_CUDA(cudaDeviceSynchronize());
            setup_seconds = std::chrono::duration<double>(Clock::now() - setup_start).count();
            h2d = measure(eventStart, eventStop, [&] {
                CHECK_CUDA(cudaMemcpy(d_bytes.data(), bytes.data(), bytes.size(), cudaMemcpyHostToDevice));
            });
            const auto histogram_blocks = grid_size(layout.count, device);
            kernel = measure(eventStart, eventStop, [&] {
                histogram_entropy_kernel<<<histogram_blocks, threads>>>(d_bytes.data(),
                    options.window, options.step, layout.count, d_entropy.data());
                CHECK_CUDA(cudaGetLastError());
            });
            const std::size_t boundary_blocks_needed = 1 + (layout.count - 1) / 256;
            const auto boundary_blocks = grid_size(boundary_blocks_needed, device);
            detection = measure(eventStart, eventStop, [&] {
                boundary_flags_kernel<<<boundary_blocks, 256>>>(d_entropy.data(),
                    layout.count, options.threshold, d_flags.data());
                CHECK_CUDA(cudaGetLastError());
            });
            d2h = measure(eventStart, eventStop, [&] {
                CHECK_CUDA(cudaMemcpy(entropy.data(), d_entropy.data(),
                    entropy.size() * sizeof(double), cudaMemcpyDeviceToHost));
                CHECK_CUDA(cudaMemcpy(flags.data(), d_flags.data(),
                    flags.size() * sizeof(std::uint8_t), cudaMemcpyDeviceToHost));
            });
            const auto cleanup_start = Clock::now();
            eventStop.release(); eventStart.release();
            d_flags.release(); d_entropy.release(); d_bytes.release();
            CHECK_CUDA(cudaDeviceSynchronize());
            cleanup_seconds = std::chrono::duration<double>(Clock::now() - cleanup_start).count();
        }
        const auto post_start = Clock::now();
        for (std::size_t i = 0; i < entropy.size(); ++i) {
            if (!std::isfinite(entropy[i]) || entropy[i] < -1e-6 || entropy[i] > 8.0 + 1e-6)
                throw std::runtime_error("Invalid GPU entropy at window " + std::to_string(i));
            const double delta = i == 0 ? 0.0 : entropy[i] - entropy[i - 1];
            const auto expected = static_cast<std::uint8_t>(i != 0 && std::abs(delta) >= options.threshold);
            if (flags[i] != expected)
                throw std::runtime_error("GPU boundary flag differs from CPU check at window " + std::to_string(i));
            if (flags[i]) boundaries.push_back({i, i * options.step, entropy[i - 1], entropy[i], delta});
        }
        const double post_seconds = std::chrono::duration<double>(Clock::now() - post_start).count();
        const auto write_start = Clock::now();
        write_gpu_csv(options.output, entropy, flags, options.step);
        const auto total_end = Clock::now();
        const double write_seconds = std::chrono::duration<double>(total_end - write_start).count();
        const double total_seconds = std::chrono::duration<double>(total_end - total_start).count();
        c05::report_layout(bytes.size(), options);
        // Preserve step-1 core semantics: histogram and entropy only.
        c05::report_timing("cuda", options, layout.count, boundaries.size(),
                          kernel.event_seconds, total_seconds);
        const long double logical_bytes = static_cast<long double>(layout.count) * options.window;
        const double logical_gbps = kernel.event_seconds > 0
            ? static_cast<double>(logical_bytes / kernel.event_seconds / 1.0e9L) : 0.0;
        std::cerr << std::setprecision(12)
            << "device=\"" << device_name << "\" threads_per_block=" << threads << '\n'
            << "T_gpu_compute_s=" << kernel.event_seconds + detection.event_seconds << '\n'
            << "T_read_s=" << read_seconds << " T_setup_s=" << setup_seconds
            << " T_cleanup_s=" << cleanup_seconds << '\n'
            << "T_H2D_wall_s=" << h2d.wall_seconds << " T_H2D_event_s=" << h2d.event_seconds << '\n'
            << "T_entropy_kernel_wall_s=" << kernel.wall_seconds
            << " T_entropy_kernel_event_s=" << kernel.event_seconds << '\n'
            << "T_boundary_kernel_wall_s=" << detection.wall_seconds
            << " T_boundary_kernel_event_s=" << detection.event_seconds << '\n'
            << "T_D2H_wall_s=" << d2h.wall_seconds << " T_D2H_event_s=" << d2h.event_seconds << '\n'
            << "T_postprocess_cpu_s=" << post_seconds << " T_write_csv_s=" << write_seconds << '\n'
            << "logical_window_bytes=" << logical_bytes << " logical_histogram_GBps=" << logical_gbps << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
