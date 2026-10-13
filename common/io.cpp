#include "common/io.hpp"
#include <charconv>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <set>
#include <stdexcept>
#include <system_error>
namespace c05 {
namespace {
std::size_t positive_size(std::string_view value, std::string_view name) {
    std::size_t result = 0;
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
    if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() || result == 0)
        throw std::invalid_argument(std::string(name) + " must be a positive integer");
    return result;
}
}
Options parse_options(int argc, char** argv) {
    Options o;
    std::set<std::string> seen;
    for (int i = 1; i < argc; ++i) {
        const std::string key = argv[i];
        if (key == "--help" || key == "-h") { o.help = true; return o; }
        if (key != "--input" && key != "--output" && key != "--window" &&
            key != "--step" && key != "--threshold" && key != "--threads" && key != "--mode")
            throw std::invalid_argument("Unknown option: " + key);
        if (!seen.insert(key).second) throw std::invalid_argument("Duplicate option: " + key);
        if (++i >= argc) throw std::invalid_argument("Missing value for " + key);
        const std::string value = argv[i];
        if (key == "--input") o.input = value;
        else if (key == "--output") o.output = value;
        else if (key == "--window") o.window = positive_size(value, key);
        else if (key == "--step") o.step = positive_size(value, key);
        else if (key == "--threads") {
            const auto n = positive_size(value, key);
            if (n > static_cast<std::size_t>(std::numeric_limits<int>::max()))
                throw std::invalid_argument("--threads exceeds INT_MAX");
            o.threads = static_cast<int>(n);
        } else if (key == "--mode") o.mode = value;
        else {
            const auto parsed = std::from_chars(value.data(), value.data() + value.size(), o.threshold);
            if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() ||
                !std::isfinite(o.threshold) || o.threshold < 0)
                throw std::invalid_argument("--threshold must be finite and nonnegative");
        }
    }
    for (const auto* key : {"--input", "--output", "--window", "--step", "--threshold"})
        if (!seen.contains(key)) throw std::invalid_argument(std::string("Required option: ") + key);
    if (o.input.empty() || o.output.empty()) throw std::invalid_argument("Paths must not be empty");
    if (o.window > std::numeric_limits<std::uint32_t>::max())
        throw std::invalid_argument("--window exceeds uint32_t histogram capacity");
    if (o.mode != "naive" && o.mode != "incremental")
        throw std::invalid_argument("--mode must be naive or incremental");
    if (std::filesystem::weakly_canonical(o.input) == std::filesystem::weakly_canonical(o.output))
        throw std::invalid_argument("Input and output paths must differ");
    if (std::filesystem::exists(o.output) && std::filesystem::equivalent(o.input, o.output))
        throw std::invalid_argument("Input and output refer to the same file");
    return o;
}
void print_usage(std::string_view executable) {
    std::cout << "Usage: " << executable
      << " --input FILE --window W --step S --threshold T --output CSV"
      << " [--threads N] [--mode naive|incremental]\n"
      << "Only complete windows. delta is signed; boundary iff abs(delta) >= T.\n"
      << "--mode selects the reference algorithm; parallel backends accept only naive.\n";
}
std::vector<std::uint8_t> read_binary(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    if (!in) throw std::runtime_error("Cannot open input: " + path.string());
    const auto end = in.tellg();
    if (end < 0) throw std::runtime_error("Cannot determine input size");
    const auto length = static_cast<std::uintmax_t>(end);
    if (length > std::numeric_limits<std::size_t>::max() ||
        length > static_cast<std::uintmax_t>(std::numeric_limits<std::streamsize>::max()))
        throw std::runtime_error("Input is too large for this process");
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(length));
    in.seekg(0);
    if (!in) throw std::runtime_error("Input seek failed");
    if (!bytes.empty()) {
        in.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
        if (!in || static_cast<std::size_t>(in.gcount()) != bytes.size())
            throw std::runtime_error("Short read or input changed while reading");
    }
    if (in.peek() != std::char_traits<char>::eof())
        throw std::runtime_error("Input grew while reading");
    if (in.bad()) throw std::runtime_error("Input read error");
    return bytes;
}
WindowLayout window_layout(std::size_t bytes, std::size_t window, std::size_t step) {
    if (window == 0 || step == 0) throw std::invalid_argument("W and S must be positive");
    if (bytes < window) return {0, bytes, 0};
    const auto count = 1 + (bytes - window) / step;
    const auto covered_end = (count - 1) * step + window;
    const auto gaps = step > window ? (count - 1) * (step - window) : 0;
    return {count, bytes - covered_end, gaps};
}
std::vector<Boundary> detect_boundaries(std::span<const double> entropy,
                                      std::size_t step, double threshold) {
    std::vector<Boundary> result;
    for (std::size_t i = 1; i < entropy.size(); ++i) {
        const double delta = entropy[i] - entropy[i - 1];
        if (std::abs(delta) >= threshold)
            result.push_back({i, i * step, entropy[i - 1], entropy[i], delta});
    }
    return result;
}
void write_csv(const std::filesystem::path& path, std::span<const double> entropy,
               std::size_t step, double threshold) {
    std::ofstream out(path, std::ios::trunc);
    if (!out) throw std::runtime_error("Cannot open output: " + path.string());
    out.imbue(std::locale::classic());
    out << "offset,entropy,delta,is_boundary\n" << std::setprecision(17);
    for (std::size_t i = 0; i < entropy.size(); ++i) {
        const double delta = i == 0 ? 0 : entropy[i] - entropy[i - 1];
        out << i * step << ',' << entropy[i] << ',' << delta << ','
            << (i != 0 && std::abs(delta) >= threshold ? 1 : 0) << '\n';
    }
    out.flush();
    if (!out) throw std::runtime_error("Output write failed");
    out.close();
    if (!out) throw std::runtime_error("Output close failed");
}
void report_layout(std::size_t bytes, const Options& options) {
    const auto layout = window_layout(bytes, options.window, options.step);
    std::cerr << "input_bytes=" << bytes << " windows=" << layout.count
              << " omitted_trailing_bytes=" << layout.trailing_bytes
              << " uncovered_gap_bytes=" << layout.uncovered_gap_bytes << '\n';
}
void report_timing(std::string_view backend, const Options& options,
                   std::size_t windows, std::size_t boundaries,
                   double core_seconds, double total_seconds) {
    std::cerr << std::setprecision(9) << "backend=" << backend << " mode=" << options.mode
              << " windows=" << windows << " boundaries=" << boundaries
              << " T_core_s=" << core_seconds << " T_total_s=" << total_seconds << '\n';
}
}
