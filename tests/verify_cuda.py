#!/usr/bin/env python3
"""Strict CUDA/reference comparison. Requires real CUDA hardware; no fallback."""
import argparse
from pathlib import Path
import random
import subprocess
import tempfile
from verify_correctness import compare, load_csv, load_events_csv, verify_events_against_rows


def run(exe, source, output, window, step, threshold, mode='naive', threads=None, events_out=None):
    command = [str(exe), '--input', str(source), '--output', str(output),
               '--window', str(window), '--step', str(step),
               '--threshold', str(threshold), '--mode', mode]
    if threads is not None:
        command += ['--threads', str(threads)]
    if events_out is not None:
        command += ['--events', str(events_out)]
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
    parameters = [(1, 1), (31, 7), (256, 256), (128, 257), (2048, 1)]
    maximum = 0.0
    cases = 0
    with tempfile.TemporaryDirectory(prefix='c05_cuda_') as directory:
        root = Path(directory)
        source = root / 'fixture.bin'
        events_out = root / 'events.csv'
        for data in fixtures:
            source.write_bytes(data)
            for window, step in parameters:
                expected = run(ref, source, root / 'ref.csv', window, step, 0.1)
                for mode in ('naive', 'incremental'):
                    for threads in (64, 256):
                        actual = run(gpu, source, root / 'gpu.csv', window, step,
                                     0.1, mode, threads, events_out)
                        maximum = max(maximum, compare(expected, actual))
                        verify_events_against_rows(actual, load_events_csv(events_out), window, step)
                        cases += 1
        # Test all valid block sizes (64, 128, 256, 512, 1024) and threshold=0.0 on mixed data.
        source.write_bytes(b'\x00' * 256 + bytes(range(256)) + rng.randbytes(1024))
        expected0 = run(ref, source, root / 'ref0.csv', 64, 16, 0.0)
        for mode in ('naive', 'incremental'):
            for threads in (64, 128, 256, 512, 1024):
                actual0 = run(gpu, source, root / 'gpu0.csv', 64, 16, 0.0, mode, threads, events_out)
                maximum = max(maximum, compare(expected0, actual0))
                verify_events_against_rows(actual0, load_events_csv(events_out), 64, 16)
                cases += 1
        # Exactly representable H=0 and H=1: inclusive threshold must fire.
        source.write_bytes(b'\x00\x00\x00\x01')
        expected = run(ref, source, root / 'ref.csv', 2, 2, 1.0)
        for mode in ('naive', 'incremental'):
            actual = run(gpu, source, root / 'gpu.csv', 2, 2, 1.0, mode, 256)
            maximum = max(maximum, compare(expected, actual))
            if actual[1][3] != 1:
                raise AssertionError(f'Exact threshold boundary missing ({mode})')
    print(f'PASS: {cases} CUDA cases (naive+incremental, blocks 64..1024) + exact threshold; max_error={maximum:.17g}')


if __name__ == '__main__':
    main()
