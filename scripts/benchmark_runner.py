#!/usr/bin/env python3
"""C05 sequential benchmark driver. No fabricated measurements or silent skips."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shlex
import shutil
import subprocess
import sys

LABELS = ['Ref-Naive', 'Ref-Incremental', 'OMP', 'MPI', 'CUDA']
DATASETS = ['constant_bytes.bin', 'uniform_random.bin', 'mixed_segmented.bin']
FIELDS = ['timestamp', 'implementation', 'dataset', 'file_size_bytes', 'window_size',
          'step_size', 'threads_processes', 'run_id', 't_core_ms', 't_total_ms',
          'throughput_gbps', 'logical_throughput_gbps', 't_h2d_ms', 't_entropy_kernel_ms',
          't_boundary_kernel_ms', 't_d2h_ms', 't_postprocess_cpu_ms',
          't_h2d_event_ms', 't_d2h_event_ms', 'mpi_mode', 'threshold', 'windows', 'log_path']


def integers(text):
    try:
        values = [int(v) for v in text.split(',')]
    except ValueError as error:
        raise argparse.ArgumentTypeError('expected comma-separated positive integers') from error
    if not values or min(values) <= 0 or len(set(values)) != len(values):
        raise argparse.ArgumentTypeError('positive unique integers required')
    return values


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=root / 'build')
    parser.add_argument('--datasets', type=Path, default=root / 'datasets')
    parser.add_argument('--results', type=Path, default=root / 'results')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--windows', type=integers, default=[1024, 4096, 16384, 65536])
    parser.add_argument('--step-divisors', type=integers, default=[1, 4])
    parser.add_argument('--omp-threads', type=integers, default=[1, 2, 4, 8, 16])
    parser.add_argument('--mpi-processes', type=integers, default=[1, 2, 4, 8])
    parser.add_argument('--cuda-blocks', type=integers, default=[128, 256, 512])
    parser.add_argument('--implementations', default=','.join(LABELS))
    parser.add_argument('--threshold', type=float, default=0.1)
    parser.add_argument('--mpiexec', default='mpiexec')
    parser.add_argument('--mpi-extra', default='', help='shlex-parsed launcher arguments; no shell evaluation')
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--generate-datasets', action='store_true')
    parser.add_argument('--no-plots', action='store_true')
    parser.add_argument('--timeout', type=float, default=0, help='per process seconds; 0 means no timeout')
    args = parser.parse_args()
    implementations = args.implementations.split(',')
    if args.repeats < 5:
        parser.error('at least five measured repetitions required')
    if not math.isfinite(args.threshold) or args.threshold < 0:
        parser.error('threshold must be finite and nonnegative')
    if not math.isfinite(args.timeout) or args.timeout < 0:
        parser.error('timeout must be finite and nonnegative')
    if len(set(implementations)) != len(implementations) or any(i not in LABELS for i in implementations):
        parser.error('invalid or duplicate implementation')
    if any(v not in (64, 128, 256, 512, 1024) for v in args.cuda_blocks):
        parser.error('invalid CUDA threads per block')
    if any(w % d for w in args.windows for d in args.step_divisors):
        parser.error('each step divisor must divide every window size')
    args.build_dir = args.build_dir.resolve()
    args.datasets = args.datasets.resolve()
    args.results = args.results.resolve()
    if args.results.exists() and any(args.results.iterdir()):
        parser.error('results directory must be absent or empty; never mix benchmark sessions')
    if args.generate_datasets:
        subprocess.run([sys.executable, str(root / 'scripts/generate_datasets.py'),
                        '--output-dir', str(args.datasets)], check=True)
    for name in DATASETS:
        if not (args.datasets / name).is_file():
            parser.error(f'missing dataset: {args.datasets / name}; use --generate-datasets')
    if not (args.datasets / 'ground_truth_boundaries.json').is_file():
        parser.error('ground_truth_boundaries.json is required before benchmarking')
    binaries = {'Ref-Naive': 'entropy_ref', 'Ref-Incremental': 'entropy_ref',
                'OMP': 'entropy_omp', 'MPI': 'entropy_mpi', 'CUDA': 'entropy_cuda'}
    for implementation in implementations:
        path = args.build_dir / binaries[implementation]
        if not path.is_file() or not os.access(path, os.X_OK):
            parser.error(f'missing executable: {path}')
    launcher = shutil.which(args.mpiexec) if 'MPI' in implementations else None
    if 'MPI' in implementations and not launcher:
        parser.error('MPI launcher not found')
    if not args.no_plots:
        # Fail before measurements if plotting dependencies are missing.
        subprocess.run([sys.executable, '-c', 'import matplotlib,seaborn,pandas,numpy'], check=True)
    args.results.mkdir(parents=True, exist_ok=True)
    logs = args.results / 'logs'
    logs.mkdir()
    artifact = args.results / 'last_output.csv'
    env = os.environ.copy()
    env.update(OMP_DYNAMIC='FALSE', OMP_PROC_BIND='TRUE', OMP_PLACES='cores')
    configurations = []
    for name in DATASETS:
        for window in args.windows:
            for divisor in args.step_divisors:
                step = window // divisor
                for implementation in implementations:
                    values = (args.omp_threads if implementation == 'OMP' else
                              args.mpi_processes if implementation == 'MPI' else
                              args.cuda_blocks if implementation == 'CUDA' else [1])
                    for p in values:
                        configurations.append((implementation, name, window, step, p))
    random.Random(args.seed).shuffle(configurations)
    sizes = {name: (args.datasets / name).stat().st_size for name in DATASETS}
    if any(size < max(args.windows) for size in sizes.values()):
        parser.error('all datasets must contain at least one full window at largest W')
    metadata = {
        'created_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
        'cpu_count': os.cpu_count(), 'configuration_count': len(configurations),
        'repeats': args.repeats, 'warmups_per_configuration': 1,
        'warmup_scope': 'one discarded independent process; not in-context CUDA warm-up',
        'mpi_mode': 'local shared-memory; single host enforced with -host hostname',
        'throughput_gbps': 'file_size_bytes / T_core_seconds / 1e9 (input-normalized)',
        'logical_throughput_gbps': 'full_window_count * W / T_core_seconds / 1e9; not DRAM bandwidth',
        'core_definition': 'CPU histogram+entropy; CUDA T_entropy_kernel_event_s',
        'arguments': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        'environment': {k: env[k] for k in ('OMP_DYNAMIC', 'OMP_PROC_BIND', 'OMP_PLACES')},
        'datasets': {name: {'size_bytes': sizes[name], 'sha256': sha256(args.datasets / name)} for name in DATASETS},
        'status': 'running'}
    for tool, command in [('gpu', ['nvidia-smi']), ('mpi', [launcher, '--version'] if launcher else [])]:
        if command and shutil.which(command[0]):
            probe = subprocess.run(command, capture_output=True, text=True)
            metadata[tool] = probe.stdout + probe.stderr
    meta_path = args.results / 'metadata.json'
    meta_path.write_text(json.dumps(metadata, indent=2) + '\n')

    def execute(config, run_id, output):
        implementation, name, window, step, p = config
        command = [str(args.build_dir / binaries[implementation]), '--input', str(args.datasets / name),
                   '--window', str(window), '--step', str(step), '--threshold', str(args.threshold),
                   '--output', str(output), '--mode', 'incremental' if implementation == 'Ref-Incremental' else 'naive']
        if implementation in ('OMP', 'CUDA'):
            command += ['--threads', str(p)]
        if implementation == 'MPI':
            command = [launcher] + shlex.split(args.mpi_extra) + ['-host', platform.node(), '-n', str(p)] + command
        key = f'{implementation}_{Path(name).stem}_W{window}_S{step}_p{p}_r{run_id}'
        log = logs / (key + '.log')
        result = subprocess.run(command, env=env, capture_output=True, text=True,
                                timeout=args.timeout or None)
        log.write_text('COMMAND: ' + shlex.join(command) + '\nSTDOUT:\n' + result.stdout + '\nSTDERR:\n' + result.stderr)
        if result.returncode:
            raise RuntimeError(f'run failed ({result.returncode}): {log}')
        values = dict(re.findall(r'\b([A-Za-z0-9_]+)=([0-9.eE+\-]+)', result.stderr))
        for key in ('T_core_s', 'T_total_s', 'windows'):
            if key not in values:
                raise RuntimeError(f'missing {key}: {log}')
        core = float(values['T_entropy_kernel_event_s'] if implementation == 'CUDA' else values['T_core_s'])
        total = float(values['T_total_s'])
        windows = int(values['windows'])
        if windows != 1 + (sizes[name] - window) // step:
            raise RuntimeError(f'wrong full-window count: {log}')
        if not math.isfinite(core) or core <= 0 or not math.isfinite(total) or total <= 0:
            raise RuntimeError(f'invalid measured time: {log}')
        row = dict(timestamp=datetime.now(timezone.utc).isoformat(), implementation=implementation,
                   dataset=name, file_size_bytes=sizes[name], window_size=window, step_size=step,
                   threads_processes=p, run_id=run_id, t_core_ms=core * 1000, t_total_ms=total * 1000,
                   throughput_gbps=sizes[name] / core / 1e9,
                   logical_throughput_gbps=windows * window / core / 1e9,
                   mpi_mode='local shared-memory' if implementation == 'MPI' else '',
                   threshold=args.threshold, windows=windows, log_path=str(log.relative_to(args.results)))
        if implementation == 'CUDA':
            mapping = {'t_h2d_ms': 'T_H2D_wall_s', 't_entropy_kernel_ms': 'T_entropy_kernel_event_s',
                       't_boundary_kernel_ms': 'T_boundary_kernel_event_s', 't_d2h_ms': 'T_D2H_wall_s',
                       't_postprocess_cpu_ms': 'T_postprocess_cpu_s', 't_h2d_event_ms': 'T_H2D_event_s',
                       't_d2h_event_ms': 'T_D2H_event_s'}
            for field, key in mapping.items():
                if key not in values:
                    raise RuntimeError(f'CUDA step-3 timing field {key} missing: {log}')
                value = float(values[key]) * 1000
                if not math.isfinite(value) or value < 0:
                    raise RuntimeError(f'invalid {key}: {log}')
                row[field] = value
        return row

    try:
        with (args.results / 'raw_results.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for index, config in enumerate(configurations, 1):
                print(f'[{index}/{len(configurations)}] {config}', flush=True)
                execute(config, 0, artifact)  # warm-up is logged, never written to CSV
                for run_id in range(1, args.repeats + 1):
                    writer.writerow(execute(config, run_id, artifact))
                    stream.flush()
        # Separate untimed visualization run, with exactly the selected benchmark parameters.
        window = max(args.windows)
        step = window // max(args.step_divisors)
        implementation = 'Ref-Incremental' if 'Ref-Incremental' in implementations else implementations[0]
        p = (args.omp_threads[0] if implementation == 'OMP' else args.mpi_processes[0] if implementation == 'MPI'
             else args.cuda_blocks[0] if implementation == 'CUDA' else 1)
        execute((implementation, 'mixed_segmented.bin', window, step, p), 'segmentation', args.results / 'segmentation.csv')
        truth_path = args.datasets / 'ground_truth_boundaries.json'
        if not truth_path.is_file():
            raise FileNotFoundError(f'ground truth missing: {truth_path}; never infer boundaries from size')
        shutil.copyfile(truth_path, args.results / 'ground_truth_boundaries.json')
        (args.results / 'segmentation_metadata.json').write_text(json.dumps({
            'implementation': implementation, 'window_size': window, 'step_size': step,
            'threshold': args.threshold, 'file_size_bytes': sizes['mixed_segmented.bin']}, indent=2))
        artifact.unlink(missing_ok=True)
        metadata['status'] = 'measurements complete'
        meta_path.write_text(json.dumps(metadata, indent=2) + '\n')
        if not args.no_plots:
            command = [sys.executable, str(root / 'scripts/plot_results.py'), '--csv',
                       str(args.results / 'raw_results.csv'), '--output-dir', str(args.results / 'plots'),
                       '--window', str(max(args.windows)), '--step-divisor', str(max(args.step_divisors)),
                       '--omp-p', str(max(args.omp_threads)), '--mpi-p', str(max(args.mpi_processes)),
                       '--cuda-block', str(256 if 256 in args.cuda_blocks else args.cuda_blocks[0])]
            if set(implementations) != set(LABELS):
                command += ['--allow-partial']
            subprocess.run(command, check=True)
        metadata['status'] = 'complete'
        meta_path.write_text(json.dumps(metadata, indent=2) + '\n')
    except Exception as error:
        metadata.update(status='failed', error=str(error))
        meta_path.write_text(json.dumps(metadata, indent=2) + '\n')
        raise
    print(f'Complete: {args.results}')


if __name__ == '__main__':
    main()
