#!/usr/bin/env python3
"""Strict CUDA/reference comparison. Requires real CUDA hardware; no fallback."""
import argparse
from pathlib import Path
import random
import subprocess
import tempfile
from verify_correctness import compare, load_csv


def run(exe, source, output, window, step, threshold, threads=None):
    command = [str(exe), '--input', str(source), '--output', str(output),
               '--window', str(window), '--step', str(step),
               '--threshold', str(threshold), '--mode', 'naive']
    if threads is not None:
        command += ['--threads', str(threads)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'{command}:\n{result.stderr}')
    return load_csv(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref-exe', type=Path, required=True)
    parser.add_argument('--cuda-exe', type=Path, required=True)
    args = parser.parse_args()
    ref, gpu = args.ref_exe.resolve(), args.cuda_exe.resolve()
    rng = random.Random(2026)
    fixtures = [b'', b'\x00' * 513, bytes(range(256)) * 3,
                rng.randbytes(1027), b'\x00' * 256 + bytes(range(256)) + b'\x00' * 256]
    parameters = [(1, 1), (2, 1), (31, 7), (256, 256), (128, 257), (2048, 1)]
    maximum = 0.0
    cases = 0
    with tempfile.TemporaryDirectory(prefix='c05_cuda_') as directory:
        root = Path(directory)
        source = root / 'fixture.bin'
        for data in fixtures:
            source.write_bytes(data)
            for window, step in parameters:
                for threshold in (0.0, 0.1):
                    expected = run(ref, source, root / 'ref.csv', window, step, threshold)
                    for threads in (64, 128, 256, 512):
                        actual = run(gpu, source, root / 'gpu.csv', window, step, threshold, threads)
                        maximum = max(maximum, compare(expected, actual))
                        cases += 1
        # Exactly representable H=0 and H=1: inclusive threshold must fire.
        source.write_bytes(b'\x00\x00\x00\x01')
        expected = run(ref, source, root / 'ref.csv', 2, 2, 1.0)
        actual = run(gpu, source, root / 'gpu.csv', 2, 2, 1.0, 256)
        maximum = max(maximum, compare(expected, actual))
        if actual[1][3] != 1:
            raise AssertionError('Exact threshold boundary missing')
    print(f'PASS: {cases} CUDA cases + exact threshold; max_error={maximum:.17g}')


if __name__ == '__main__':
    main()
