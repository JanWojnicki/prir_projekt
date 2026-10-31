#!/usr/bin/env python3
"""Compare naive/incremental CSVs, or execute reference and OpenMP edge-case tests."""
import argparse
from collections import Counter
import csv
import math
from pathlib import Path
import random
import subprocess
import tempfile

EPS = 1e-6


def load_csv(path):
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['offset', 'entropy', 'delta', 'is_boundary']:
            raise AssertionError(f'invalid CSV header: {path}')
        rows = []
        for row in reader:
            offset = int(row['offset'])
            h, delta = float(row['entropy']), float(row['delta'])
            flag = int(row['is_boundary'])
            if offset < 0 or not math.isfinite(h) or not math.isfinite(delta) or flag not in (0, 1):
                raise AssertionError(f'invalid CSV value: {row}')
            if h < -EPS or h > 8 + EPS:
                raise AssertionError(f'entropy out of range: {h}')
            if rows and offset <= rows[-1][0]:
                raise AssertionError('offsets must be strictly increasing')
            rows.append((offset, h, delta, flag))
        return rows


def load_events_csv(path):
    expected_fields = [
        'event', 'first_window', 'last_window', 'region_start', 'region_end',
        'estimated_offset', 'peak_window', 'peak_delta',
        'entropy_before', 'entropy_after', 'net_delta'
    ]
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != expected_fields:
            raise AssertionError(f'invalid events CSV header: {path}')
        events = []
        for idx, row in enumerate(reader):
            ev = int(row['event'])
            fw, lw = int(row['first_window']), int(row['last_window'])
            rs, re_ = int(row['region_start']), int(row['region_end'])
            est = int(row['estimated_offset'])
            pw = int(row['peak_window'])
            pdelta = float(row['peak_delta'])
            hb, ha, net = float(row['entropy_before']), float(row['entropy_after']), float(row['net_delta'])
            if ev != idx or fw <= 0 or lw < fw or not (fw <= pw <= lw):
                raise AssertionError(f'invalid event indices: {row}')
            if rs < 0 or re_ <= rs or est != rs + (re_ - rs) // 2:
                raise AssertionError(f'invalid event region: {row}')
            if abs((ha - hb) - net) >= EPS:
                raise AssertionError(f'inconsistent net_delta: {row}')
            events.append((ev, fw, lw, rs, re_, est, pw, pdelta, hb, ha, net))
        return events


def verify_events_against_rows(rows, events, window, step):
    flagged = [i for i, r in enumerate(rows) if r[3] == 1]
    runs = []
    for idx in flagged:
        if runs and idx == runs[-1][-1] + 1:
            runs[-1].append(idx)
        else:
            runs.append([idx])
    if len(runs) != len(events):
        raise AssertionError(f'event count mismatch: {len(runs)} != {len(events)}')
    for run_indices, ev in zip(runs, events):
        _, fw, lw, rs, re_, est, pw, pdelta, hb, ha, _ = ev
        if fw != run_indices[0] or lw != run_indices[-1]:
            raise AssertionError(f'event window bounds mismatch: {ev} vs {run_indices}')
        if rs != (fw - 1) * step or re_ != lw * step + window:
            raise AssertionError(f'event byte region mismatch: {ev}')
        if abs(hb - rows[fw - 1][1]) >= EPS or abs(ha - rows[lw][1]) >= EPS:
            raise AssertionError(f'event before/after entropy mismatch: {ev}')
        if abs(pdelta - rows[pw][2]) >= EPS:
            raise AssertionError(f'event peak_delta mismatch: {ev}')


def compare(a, b):
    if len(a) != len(b):
        raise AssertionError(f'window count mismatch: {len(a)} != {len(b)}')
    maximum = 0.0
    for index, (left, right) in enumerate(zip(a, b)):
        if left[0] != right[0] or left[3] != right[3]:
            raise AssertionError(f'offset/boundary mismatch at window {index}')
        error = abs(left[1] - right[1])
        maximum = max(maximum, error)
        if error >= EPS or abs(left[2] - right[2]) >= EPS:
            raise AssertionError(f'numeric mismatch at window {index}: {left} vs {right}')
    return maximum


def oracle(data, window, step, threshold):
    result = []
    for offset in range(0, max(0, len(data) - window + 1), step):
        counts = Counter(data[offset:offset + window])
        h = -sum((c / window) * math.log2(c / window) for c in counts.values())
        delta = h - result[-1][1] if result else 0.0
        boundary = int(bool(result) and abs(delta) >= threshold)
        result.append((offset, h, delta, boundary))
    return result


def run(exe, data_path, output, window, step, threshold, mode, extra=()):
    command = [str(exe), '--input', str(data_path), '--window', str(window),
               '--step', str(step), '--threshold', str(threshold), '--output', str(output),
               '--mode', mode, *extra]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if completed.returncode:
        raise AssertionError(f'command failed: {command}\n{completed.stderr}')
    return load_csv(output), completed.stderr


def suite(exe, omp_exe=None):
    rng = random.Random(817)
    fixtures = [b'', b'\x00', b'\xaa' * 1025, bytes(range(256)) * 4,
                rng.randbytes(2049), b'\x00' * 256 + bytes(range(256)) + b'\xaa' * 256]
    settings = [(1, 1), (2, 1), (17, 1), (64, 7), (256, 256), (17, 31),
                (4096, 1), (128, 10_000)]
    maximum = 0.0
    cases = 0
    with tempfile.TemporaryDirectory(prefix='c05_test_') as directory:
        root = Path(directory)
        source = root / 'input.bin'
        events_path = root / 'events.csv'
        for data in fixtures:
            source.write_bytes(data)
            for window, step in settings:
                for threshold in (0.0, 0.1, 8.0):
                    a, stderr = run(exe, source, root / 'naive.csv', window, step, threshold,
                                    'naive', ('--events', str(events_path)))
                    b, _ = run(exe, source, root / 'inc.csv', window, step, threshold, 'incremental')
                    maximum = max(maximum, compare(a, b))
                    compare(a, oracle(data, window, step, threshold))
                    events = load_events_csv(events_path)
                    verify_events_against_rows(a, events, window, step)
                    count = 0 if len(data) < window else 1 + (len(data) - window) // step
                    trailing = len(data) if count == 0 else len(data) - ((count - 1) * step + window)
                    gaps = (count - 1) * max(0, step - window) if count else 0
                    if f'omitted_trailing_bytes={trailing}' not in stderr:
                        raise AssertionError('incorrect trailing-byte report')
                    if f'uncovered_gap_bytes={gaps}' not in stderr:
                        raise AssertionError('incorrect gap-byte report')
                    if f'events={len(events)}' not in stderr:
                        raise AssertionError('incorrect events report')
                    if 'T_core_s=' not in stderr or 'T_total_s=' not in stderr:
                        raise AssertionError('missing timing report')
                    if omp_exe:
                        for omp_mode in ('naive', 'incremental'):
                            for threads in ('1', '2', '4'):
                                c, _ = run(omp_exe, source, root / 'omp.csv', window, step,
                                           threshold, omp_mode,
                                           ('--threads', threads, '--events', str(events_path)))
                                maximum = max(maximum, compare(a, c))
                                verify_events_against_rows(c, load_events_csv(events_path), window, step)
                    cases += 1
        source.write_bytes(b'\x00\x00\x00\x01')
        a, _ = run(exe, source, root / 'exact.csv', 2, 2, 1.0, 'naive')
        if [row[3] for row in a] != [0, 1]:
            raise AssertionError('inclusive threshold comparison failed')
        valid = [str(exe), '--input', str(source), '--window', '2', '--step', '1',
                 '--threshold', '0.1', '--output', str(root / 'invalid.csv')]
        for key, value in [('--window', '0'), ('--step', '0'), ('--threshold', '-1'),
                           ('--threshold', 'nan'), ('--window', '4294967296'),
                           ('--mode', 'unknown'), ('--threads', '2')]:
            command = valid.copy()
            if key in command:
                command[command.index(key) + 1] = value
            else:
                command.extend([key, value])
            if subprocess.run(command, capture_output=True, timeout=120).returncode == 0:
                raise AssertionError(f'invalid CLI accepted: {key} {value}')
        same_file = valid.copy()
        same_file[same_file.index('--output') + 1] = str(source)
        if subprocess.run(same_file, capture_output=True, timeout=120).returncode == 0:
            raise AssertionError('input overwrite was accepted')
        if source.read_bytes() != b'\x00\x00\x00\x01':
            raise AssertionError('input was modified')
    print(f'PASS: {cases} fixture cases + exact threshold + events + CLI checks; max_error={maximum:.17g}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path)
    parser.add_argument('--omp-exe', type=Path)
    parser.add_argument('--ref-csv', type=Path)
    parser.add_argument('--inc-csv', type=Path)
    args = parser.parse_args()
    if args.exe:
        if args.ref_csv or args.inc_csv:
            parser.error('use --exe or CSV comparison, not both')
        suite(args.exe.resolve(), args.omp_exe.resolve() if args.omp_exe else None)
    elif args.ref_csv and args.inc_csv and not args.omp_exe:
        maximum = compare(load_csv(args.ref_csv), load_csv(args.inc_csv))
        print(f'PASS: max_error={maximum:.17g}; identical offsets and boundaries')
    else:
        parser.error('provide --exe [--omp-exe] or both --ref-csv and --inc-csv')


if __name__ == '__main__':
    main()
