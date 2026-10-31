#!/usr/bin/env python3
"""Strict MPI/reference comparison across process counts (including p > windows) and modes."""
import argparse
import os
from pathlib import Path
import random
import shlex
import shutil
import subprocess
import tempfile
from verify_correctness import compare, load_csv, load_events_csv, verify_events_against_rows


def detect_mpi_flags(launcher):
    probe = subprocess.run([launcher, '--version'], capture_output=True, text=True)
    text = (probe.stdout + probe.stderr).lower()
    flags = []
    if 'open mpi' in text or 'openrte' in text or 'prrte' in text:
        flags.append('--oversubscribe')
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            flags.append('--allow-run-as-root')
    return flags


def run_ref(exe, source, output, window, step, threshold):
    command = [str(exe), '--input', str(source), '--output', str(output),
               '--window', str(window), '--step', str(step),
               '--threshold', str(threshold), '--mode', 'naive']
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'{command}:\n{result.stderr}')
    return load_csv(output)


def run_mpi(launcher, extra_flags, exe, ranks, source, output, events_out, window, step, threshold, mode):
    command = [launcher, *extra_flags, '-n', str(ranks),
               str(exe), '--input', str(source), '--output', str(output),
               '--events', str(events_out), '--window', str(window), '--step', str(step),
               '--threshold', str(threshold), '--mode', mode]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'{command}:\n{result.stderr}')
    return load_csv(output), load_events_csv(events_out), result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref-exe', type=Path, required=True)
    parser.add_argument('--mpi-exe', type=Path, required=True)
    parser.add_argument('--mpiexec', default='mpiexec')
    parser.add_argument('--mpi-extra', default='')
    args = parser.parse_args()
    launcher = shutil.which(args.mpiexec)
    if not launcher:
        raise RuntimeError(f'MPI launcher not found: {args.mpiexec}')
    extra_flags = detect_mpi_flags(launcher) + shlex.split(args.mpi_extra)
    ref, mpi = args.ref_exe.resolve(), args.mpi_exe.resolve()
    rng = random.Random(2026)
    fixtures = [b'', b'\x00' * 15, bytes(range(256)) * 3,
                b'\x00' * 256 + bytes(range(256)) + b'\x00' * 256]
    parameters = [(1, 1), (16, 4), (256, 256), (128, 257)]
    maximum = 0.0
    cases = 0
    with tempfile.TemporaryDirectory(prefix='c05_mpi_') as directory:
        root = Path(directory)
        source = root / 'fixture.bin'
        events_out = root / 'events.csv'
        for data in fixtures:
            source.write_bytes(data)
            for window, step in parameters:
                expected = run_ref(ref, source, root / 'ref.csv', window, step, 0.1)
                for ranks in (1, 2, 4, 7):
                    for mode in ('naive', 'incremental'):
                        actual, events, stderr = run_mpi(
                            launcher, extra_flags, mpi, ranks, source,
                            root / 'mpi.csv', events_out, window, step, 0.1, mode)
                        maximum = max(maximum, compare(expected, actual))
                        verify_events_against_rows(actual, events, window, step)
                        if f'mpi_ranks={ranks}' not in stderr:
                            raise AssertionError(f'missing mpi_ranks={ranks} in stderr')
                        cases += 1
        source.write_bytes(b'\x00\x00\x00\x01')
        expected = run_ref(ref, source, root / 'ref.csv', 2, 2, 1.0)
        actual, _, _ = run_mpi(launcher, extra_flags, mpi, 2, source,
                               root / 'mpi.csv', events_out, 2, 2, 1.0, 'naive')
        maximum = max(maximum, compare(expected, actual))
        if actual[1][3] != 1:
            raise AssertionError('Exact threshold boundary missing in MPI')
    print(f'PASS: {cases} MPI cases (ranks 1,2,3,4,7; naive+incremental) + exact threshold; max_error={maximum:.17g}')


if __name__ == '__main__':
    main()
