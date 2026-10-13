#include "common/compute.hpp"
#include "common/io.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <mpi.h>
namespace {
void check(int status) {
    if (status != MPI_SUCCESS) {
        char text[MPI_MAX_ERROR_STRING]; int length = 0;
        MPI_Error_string(status, text, &length);
        throw std::runtime_error(std::string(text, static_cast<std::size_t>(length)));
    }
}
int mpi_count(std::size_t value) {
    if (value > static_cast<std::size_t>(std::numeric_limits<int>::max()))
        throw std::runtime_error("MPI count/displacement exceeds INT_MAX; use smaller input");
    return static_cast<int>(value);
}
}
int main(int argc, char** argv) {
    if (MPI_Init(&argc, &argv) != MPI_SUCCESS) return 1;
    int rank = 0, ranks = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &ranks);
    MPI_Comm_set_errhandler(MPI_COMM_WORLD, MPI_ERRORS_RETURN);
    try {
        const auto options = c05::parse_options(argc, argv);
        if (options.help) {
            if (rank == 0) c05::print_usage(argv[0]);
            check(MPI_Finalize()); return 0;
        }
        if (options.mode != "naive") throw std::invalid_argument("MPI supports --mode naive");
        if (options.threads > 1) throw std::invalid_argument("MPI backend uses one thread per rank");
        check(MPI_Barrier(MPI_COMM_WORLD));
        const double total_start = MPI_Wtime();
        std::vector<std::uint8_t> bytes;
        if (rank == 0) bytes = c05::read_binary(options.input);
        std::uint64_t size = bytes.size();
        check(MPI_Bcast(&size, 1, MPI_UINT64_T, 0, MPI_COMM_WORLD));
        if (size > std::numeric_limits<std::size_t>::max()) throw std::runtime_error("Input too large");
        const auto layout = c05::window_layout(static_cast<std::size_t>(size), options.window, options.step);
        const auto processes = static_cast<std::size_t>(ranks);
        std::vector<int> byte_counts(processes), byte_offsets(processes);
        std::vector<int> counts(processes), offsets(processes);
        for (std::size_t r = 0; r < processes; ++r) {
            const auto first = (layout.count / processes) * r + std::min(r, layout.count % processes);
            const auto count = layout.count / processes + (r < layout.count % processes ? 1 : 0);
            counts[r] = mpi_count(count);
            offsets[r] = mpi_count(first);
            byte_counts[r] = mpi_count(count == 0 ? 0 : (count - 1) * options.step + options.window);
            byte_offsets[r] = count == 0 ? 0 : mpi_count(first * options.step);
        }
        const auto r = static_cast<std::size_t>(rank);
        std::vector<std::uint8_t> local(static_cast<std::size_t>(byte_counts[r]));
        // Point-to-point distribution permits overlapping halo reads on the root.
        if (rank == 0) {
            if (!local.empty()) std::copy_n(bytes.data(), local.size(), local.data());
            for (int destination = 1; destination < ranks; ++destination) {
                const auto d = static_cast<std::size_t>(destination);
                if (byte_counts[d])
                    check(MPI_Send(bytes.data() + byte_offsets[d], byte_counts[d], MPI_UINT8_T,
                                   destination, 10, MPI_COMM_WORLD));
            }
        } else if (byte_counts[r]) {
            check(MPI_Recv(local.data(), byte_counts[r], MPI_UINT8_T, 0, 10,
                           MPI_COMM_WORLD, MPI_STATUS_IGNORE));
        }
        std::vector<double> local_entropy(static_cast<std::size_t>(counts[r]));
        c05::Results results;
        if (rank == 0) results.entropy.resize(layout.count);
        check(MPI_Barrier(MPI_COMM_WORLD));
        const double core_start = MPI_Wtime();
        for (std::size_t i = 0; i < local_entropy.size(); ++i)
            local_entropy[i] = c05::window_entropy(
                std::span<const std::uint8_t>(local).subspan(i * options.step, options.window));
        const double local_core = MPI_Wtime() - core_start;
        double core = 0;
        check(MPI_Reduce(&local_core, &core, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD));
        check(MPI_Gatherv(local_entropy.data(), counts[r], MPI_DOUBLE, results.entropy.data(),
                         counts.data(), offsets.data(), MPI_DOUBLE, 0, MPI_COMM_WORLD));
        if (rank == 0) {
            results.boundaries = c05::detect_boundaries(results.entropy, options.step, options.threshold);
            c05::write_csv(options.output, results.entropy, options.step, options.threshold);
        }
        check(MPI_Barrier(MPI_COMM_WORLD));
        const double local_total = MPI_Wtime() - total_start;
        double total = 0;
        check(MPI_Reduce(&local_total, &total, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD));
        if (rank == 0) {
            c05::report_layout(static_cast<std::size_t>(size), options);
            c05::report_timing("mpi", options, layout.count, results.boundaries.size(), core, total);
        }
        check(MPI_Finalize()); return 0;
    } catch (const std::exception& e) {
        std::cerr << "rank=" << rank << " Error: " << e.what() << '\n';
        MPI_Abort(MPI_COMM_WORLD, 1); return 1;
    }
}
