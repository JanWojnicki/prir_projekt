#!/usr/bin/env python3
"""Strict MPI/reference comparison across process counts (including p > windows) and modes."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from verify_correctness import compare, load_events_csv, run, verify_events_against_rows

RANKS = (1, 2, 4, 7)


def detect_mpi_flags(launcher):
    probe = subprocess.run([launcher, '--version'], capture_output=True, text=True)
    text = (probe.stdout + probe.stderr).lower()
    flags = []
    if 'open mpi' in text or 'openrte' in text or 'prrte' in text:
        flags.append('--oversubscribe')
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            flags.append('--allow-run-as-root')
    return flags


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

    def mpi_launcher(ranks):
        return (launcher, *extra_flags, '-n', str(ranks))

    fixtures = [b'', b'\x00' * 15, bytes(range(256)) * 3,
                b'\x00' * 256 + bytes(range(256)) + b'\x00' * 256]
    parameters = [(1, 1), (16, 4), (256, 256), (128, 257)]
    maximum = 0.0
    cases = 0
    with tempfile.TemporaryDirectory(prefix='c05_mpi_') as directory:
        root = Path(directory)
        source = root / 'fixture.bin'
        events_out = root / 'events.csv'
        events_args = ('--events', str(events_out))
        for data in fixtures:
            source.write_bytes(data)
            for window, step in parameters:
                expected, _ = run(ref, source, root / 'ref.csv', window, step, 0.1, 'naive')
                for ranks in RANKS:
                    for mode in ('naive', 'incremental'):
                        actual, stderr = run(mpi, source, root / 'mpi.csv', window, step, 0.1, mode,
                                             events_args, launcher=mpi_launcher(ranks))
                        maximum = max(maximum, compare(expected, actual))
                        verify_events_against_rows(actual, load_events_csv(events_out), window, step)
                        if f'mpi_ranks={ranks}' not in stderr:
                            raise AssertionError(f'missing mpi_ranks={ranks} in stderr')
                        cases += 1
        source.write_bytes(b'\x00\x00\x00\x01')
        expected, _ = run(ref, source, root / 'ref.csv', 2, 2, 1.0, 'naive')
        actual, _ = run(mpi, source, root / 'mpi.csv', 2, 2, 1.0, 'naive',
                        events_args, launcher=mpi_launcher(2))
        maximum = max(maximum, compare(expected, actual))
        if actual[1][3] != 1:
            raise AssertionError('Exact threshold boundary missing in MPI')
    ranks_text = ','.join(map(str, RANKS))
    print(f'PASS: {cases} MPI cases (ranks {ranks_text}; naive+incremental) + exact threshold; '
          f'max_error={maximum:.17g}')


if __name__ == '__main__':
    main()
