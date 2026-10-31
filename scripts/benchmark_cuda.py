#!/usr/bin/env python3
"""Repeated end-to-end runs; report medians of entropy-kernel event measurements."""
import argparse
import json
from pathlib import Path
import re
import statistics
import subprocess
import tempfile


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--datasets', type=Path, default=Path('datasets'))
    parser.add_argument('--window', type=positive, default=65536)
    parser.add_argument('--step', type=positive, default=65536)
    parser.add_argument('--threads', type=int, choices=(64, 128, 256, 512, 1024), default=256)
    parser.add_argument('--mode', choices=('naive', 'incremental', 'both'), default='both')
    parser.add_argument('--repeats', type=positive, default=5)
    parser.add_argument('--output', type=Path, default=Path('cuda_benchmark.json'))
    args = parser.parse_args()
    modes = ('naive', 'incremental') if args.mode == 'both' else (args.mode,)
    report = {'window': args.window, 'step': args.step, 'threads': args.threads,
              'modes': list(modes), 'repeats': args.repeats, 'results': [],
              'method': 'Separate processes, one discarded run per dataset/mode; no in-process warm-up.',
              'throughput': 'Logical window bytes / histogram+entropy kernel time; not DRAM bandwidth.'}
    with tempfile.TemporaryDirectory(prefix='c05_cuda_bench_') as directory:
        for name in ('constant_bytes.bin', 'uniform_random.bin', 'mixed_segmented.bin'):
            source = args.datasets / name
            if not source.is_file():
                raise FileNotFoundError(source)
            for mode in modes:
                times, rates = [], []
                for repeat in range(args.repeats + 1):
                    command = [str(args.exe.resolve()), '--input', str(source.resolve()),
                               '--window', str(args.window), '--step', str(args.step),
                               '--threshold', '0.1', '--threads', str(args.threads),
                               '--mode', mode,
                               '--output', str(Path(directory) / 'result.csv')]
                    result = subprocess.run(command, capture_output=True, text=True, check=True)
                    values = dict(re.findall(r'\b([A-Za-z0-9_]+)=([0-9.eE+\-]+)', result.stderr))
                    if int(values['windows']) == 0:
                        raise ValueError(f'No complete windows in {source}')
                    if repeat:
                        times.append(float(values['T_entropy_kernel_event_s']))
                        rates.append(float(values['logical_histogram_GBps']))
                report['results'].append({'file': name, 'mode': mode, 'size_bytes': source.stat().st_size,
                    'entropy_kernel_seconds': times, 'logical_GBps': rates,
                    'median_entropy_kernel_seconds': statistics.median(times),
                    'median_logical_GBps': statistics.median(rates)})
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
