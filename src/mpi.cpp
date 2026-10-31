// MPI backend. Rank 0 reads the file; window indices are split into contiguous blocks
// (sizes differ by <= 1). Every rank receives exactly the bytes covered by its windows,
// i.e. its block plus a W-S overlap ("halo") with the next block. Windows are owned by a
// single rank, so no result is produced twice at block borders; results are gathered by
// global window index (MPI_Gatherv displacements), which preserves global offsets.
#include "common/compute.hpp"
#include "common/io.hpp"
#include <algorithm>
#include <array>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>
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
        if (options.threads > 1) throw std::invalid_argument("MPI backend uses one thread per rank");
        check(MPI_Barrier(MPI_COMM_WORLD));
        const double total_start = MPI_Wtime();
        std::vector<std::uint8_t> bytes;
        if (rank == 0) bytes = c05::read_binary(options.input);
        const double read_end = MPI_Wtime();
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
        // Point-to-point distribution: halo regions overlap on the root, which
        // MPI_Scatterv does not permit (no root location may be read twice).
        const double distribute_start = MPI_Wtime();
        if (rank == 0) {
            if (!local.empty()) std::copy_n(bytes.data(), local.size(), local.data());
            std::vector<MPI_Request> requests;
            for (int destination = 1; destination < ranks; ++destination) {
                const auto d = static_cast<std::size_t>(destination);
                if (!byte_counts[d]) continue;
                requests.emplace_back();
                check(MPI_Isend(bytes.data() + byte_offsets[d], byte_counts[d], MPI_UINT8_T,
                                destination, 10, MPI_COMM_WORLD, &requests.back()));
            }
            if (!requests.empty())
                check(MPI_Waitall(static_cast<int>(requests.size()), requests.data(), MPI_STATUSES_IGNORE));
        } else if (byte_counts[r]) {
            check(MPI_Recv(local.data(), byte_counts[r], MPI_UINT8_T, 0, 10,
                           MPI_COMM_WORLD, MPI_STATUS_IGNORE));
        }
        std::vector<double> local_entropy(static_cast<std::size_t>(counts[r]));
        c05::Results results;
        if (rank == 0) results.entropy.resize(layout.count);
        check(MPI_Barrier(MPI_COMM_WORLD));
        const double core_start = MPI_Wtime();
        c05::compute_mode(options.mode, local, options.window, options.step, local_entropy);
        const double local_core = MPI_Wtime() - core_start;
        std::array<double, 2> core_minmax{-local_core, local_core}, reduced{};
        check(MPI_Reduce(core_minmax.data(), reduced.data(), 2, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD));
        const double gather_start = MPI_Wtime();
        check(MPI_Gatherv(local_entropy.data(), counts[r], MPI_DOUBLE, results.entropy.data(),
                         counts.data(), offsets.data(), MPI_DOUBLE, 0, MPI_COMM_WORLD));
        const double gather_end = MPI_Wtime();
        std::size_t events = 0;
        if (rank == 0) {
            results.boundaries = c05::detect_boundaries(results.entropy, options.step, options.threshold);
            c05::write_csv(options.output, results.entropy, options.step, options.threshold);
            events = c05::write_events_if_requested(options, results.boundaries, results.entropy);
        }
        check(MPI_Barrier(MPI_COMM_WORLD));
        const double local_total = MPI_Wtime() - total_start;
        double total = 0;
        check(MPI_Reduce(&local_total, &total, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD));
        if (rank == 0) {
            c05::report_layout(static_cast<std::size_t>(size), options);
            c05::report_timing("mpi", options, layout.count, results.boundaries.size(), events,
                               reduced[1], total);
            std::cerr << "mpi_ranks=" << ranks << " T_read_s=" << read_end - total_start
                      << " T_distribute_s=" << core_start - distribute_start
                      << " T_gather_s=" << gather_end - gather_start
                      << " T_core_min_rank_s=" << -reduced[0] << '\n';
        }
        check(MPI_Finalize()); return 0;
    } catch (const std::exception& e) {
        std::cerr << "rank=" << rank << " Error: " << e.what() << '\n';
        MPI_Abort(MPI_COMM_WORLD, 1); return 1;
    }
}
