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
import tempfile

LABELS = [
    'Ref-Naive', 'Ref-Incremental',
    'OMP', 'OMP-Incremental',
    'MPI', 'MPI-Incremental',
    'CUDA', 'CUDA-Incremental',
]
DATASETS = ['constant_bytes.bin', 'uniform_random.bin', 'mixed_segmented.bin']
FIELDS = [
    'timestamp', 'implementation', 'mode', 'dataset', 'file_size_bytes',
    'window_size', 'step_size', 'threads_processes', 'run_id',
    't_core_ms', 't_total_ms', 'throughput_gbps', 'logical_throughput_gbps',
    't_h2d_ms', 't_entropy_kernel_ms', 't_boundary_kernel_ms', 't_d2h_ms',
    't_postprocess_cpu_ms', 't_h2d_event_ms', 't_d2h_event_ms',
    'mpi_mode', 'threshold', 'windows', 'boundaries', 'events', 'log_path'
]
BINARIES = {
    'Ref-Naive': 'entropy_ref',
    'Ref-Incremental': 'entropy_ref',
    'OMP': 'entropy_omp',
    'OMP-Incremental': 'entropy_omp',
    'MPI': 'entropy_mpi',
    'MPI-Incremental': 'entropy_mpi',
    'CUDA': 'entropy_cuda',
    'CUDA-Incremental': 'entropy_cuda',
}


def impl_mode(implementation):
    return 'incremental' if implementation.endswith('Incremental') else 'naive'


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


def detect_mpi_flags(launcher):
    if not launcher:
        return []
    probe = subprocess.run([launcher, '--version'], capture_output=True, text=True)
    text = (probe.stdout + probe.stderr).lower()
    flags = []
    if 'open mpi' in text or 'openrte' in text or 'prrte' in text:
        flags.append('--oversubscribe')
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            flags.append('--allow-run-as-root')
    return flags


def host_hardware_info():
    info = {
        'platform': platform.platform(),
        'node': platform.node(),
        'logical_cpus': os.cpu_count(),
    }
    cpuinfo = Path('/proc/cpuinfo')
    if cpuinfo.is_file():
        text = cpuinfo.read_text(encoding='utf-8', errors='ignore')
        models = re.findall(r'^model name\s*:\s*(.+)$', text, re.M)
        cores = re.findall(r'^cpu cores\s*:\s*(\d+)$', text, re.M)
        if models:
            info['cpu_model'] = models[0].strip()
        if cores:
            info['physical_cores_per_socket'] = int(cores[0])
    meminfo = Path('/proc/meminfo')
    if meminfo.is_file():
        text = meminfo.read_text(encoding='utf-8', errors='ignore')
        m = re.search(r'^MemTotal:\s*(\d+)\s*kB', text, re.M)
        if m:
            info['ram_total_gb'] = round(int(m.group(1)) / (1024 * 1024), 2)
    return info


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=root / 'build')
    parser.add_argument('--datasets', type=Path, default=root / 'datasets')
    parser.add_argument('--results', type=Path, default=root / 'results')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--windows', type=integers, default=[1024, 4096, 16384, 65536])
    parser.add_argument('--step-divisors', type=integers, default=[1, 4])
    parser.add_argument('--omp-threads', type=integers, default=[1, 2, 4, 6, 8, 12])
    parser.add_argument('--mpi-processes', type=integers, default=[1, 2, 4, 6, 8])
    parser.add_argument('--cuda-blocks', type=integers, default=[64, 128, 256, 512, 1024])
    parser.add_argument('--implementations', default=','.join(LABELS))
    parser.add_argument('--threshold', type=float, default=0.1)
    parser.add_argument('--mpiexec', default='mpiexec')
    parser.add_argument('--mpi-extra', default='', help='shlex-parsed launcher arguments; no shell evaluation')
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--generate-datasets', action='store_true')
    parser.add_argument('--full-grid', action='store_true',
                        help='run every thread/process/block count on every W and dataset')
    parser.add_argument('--skip-supplementary', action='store_true')
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
    for implementation in implementations:
        path = args.build_dir / BINARIES[implementation]
        if not path.is_file() or not os.access(path, os.X_OK):
            parser.error(f'missing executable: {path}')
    has_mpi = any(i in ('MPI', 'MPI-Incremental') for i in implementations)
    launcher = shutil.which(args.mpiexec) if has_mpi else None
    if has_mpi and not launcher:
        parser.error('MPI launcher not found')
    mpi_auto_flags = detect_mpi_flags(launcher) + shlex.split(args.mpi_extra)
    if not args.no_plots:
        subprocess.run([sys.executable, '-c', 'import matplotlib,seaborn,pandas,numpy'], check=True)
    args.results.mkdir(parents=True, exist_ok=True)
    logs = args.results / 'logs'
    logs.mkdir()
    artifact = args.results / 'last_output.csv'
    env = os.environ.copy()
    env.update(OMP_DYNAMIC='FALSE', OMP_PROC_BIND='TRUE', OMP_PLACES='cores')

    max_w = max(args.windows)
    max_div = max(args.step_divisors)
    canon_omp = max(args.omp_threads)
    canon_mpi = 6 if 6 in args.mpi_processes else max(args.mpi_processes)
    canon_cuda = 256 if 256 in args.cuda_blocks else args.cuda_blocks[0]

    config_set = set()
    if args.full_grid:
        for name in DATASETS:
            for window in args.windows:
                for divisor in args.step_divisors:
                    step = window // divisor
                    for implementation in implementations:
                        values = (args.omp_threads if implementation.startswith('OMP') else
                                  args.mpi_processes if implementation.startswith('MPI') else
                                  args.cuda_blocks if implementation.startswith('CUDA') else [1])
                        for p in values:
                            config_set.add((implementation, name, window, step, p))
    else:
        # 1. Full (W, S) sweep on mixed_segmented.bin for all implementations at canonical resources.
        for window in args.windows:
            for divisor in args.step_divisors:
                step = window // divisor
                for implementation in implementations:
                    p = (canon_omp if implementation.startswith('OMP') else
                         canon_mpi if implementation.startswith('MPI') else
                         canon_cuda if implementation.startswith('CUDA') else 1)
                    config_set.add((implementation, 'mixed_segmented.bin', window, step, p))
        # 2. Strong scaling on mixed_segmented.bin at W=max_w, S=max_w//max_div for OMP and MPI.
        step_ref = max_w // max_div
        for implementation in implementations:
            if implementation.startswith('OMP'):
                for p in args.omp_threads:
                    config_set.add((implementation, 'mixed_segmented.bin', max_w, step_ref, p))
            elif implementation.startswith('MPI'):
                for p in args.mpi_processes:
                    config_set.add((implementation, 'mixed_segmented.bin', max_w, step_ref, p))
        # 3. CUDA & CUDA-Incremental across all W on constant_bytes.bin and uniform_random.bin (at S=W//max_div),
        #    plus all implementations on constant_bytes.bin and uniform_random.bin at W=max_w, S=max_w//max_div.
        for name in ('constant_bytes.bin', 'uniform_random.bin'):
            for window in args.windows:
                step = window // max_div
                for implementation in implementations:
                    if implementation.startswith('CUDA') or window == max_w:
                        p = (canon_omp if implementation.startswith('OMP') else
                             canon_mpi if implementation.startswith('MPI') else
                             canon_cuda if implementation.startswith('CUDA') else 1)
                        config_set.add((implementation, name, window, step, p))
        # 4. CUDA block-size sweep across all datasets at W=max_w, S=max_w//max_div.
        for name in DATASETS:
            for implementation in implementations:
                if implementation.startswith('CUDA'):
                    for blk in args.cuda_blocks:
                        config_set.add((implementation, name, max_w, step_ref, blk))
    configurations = sorted(config_set)
    random.Random(args.seed).shuffle(configurations)

    sizes = {name: (args.datasets / name).stat().st_size for name in DATASETS}
    if any(size < max_w for size in sizes.values()):
        parser.error('all datasets must contain at least one full window at largest W')
    hw = host_hardware_info()
    metadata = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'platform': hw['platform'],
        'hardware': hw,
        'cpu_count': os.cpu_count(),
        'configuration_count': len(configurations),
        'repeats': args.repeats,
        'warmups_per_configuration': 1,
        'warmup_scope': 'one discarded independent process; not in-context CUDA warm-up',
        'mpi_mode': f'local shared-memory (single host: {platform.node()})',
        'canonical_resources': {'omp_p': canon_omp, 'mpi_p': canon_mpi, 'cuda_block': canon_cuda},
        'throughput_gbps': 'file_size_bytes / T_core_seconds / 1e9 (input-normalized)',
        'logical_throughput_gbps': 'full_window_count * W / T_core_seconds / 1e9; not DRAM bandwidth',
        'core_definition': 'CPU histogram+entropy; CUDA T_entropy_kernel_event_s',
        'arguments': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        'environment': {k: env[k] for k in ('OMP_DYNAMIC', 'OMP_PROC_BIND', 'OMP_PLACES')},
        'datasets': {name: {'size_bytes': sizes[name], 'sha256': sha256(args.datasets / name)} for name in DATASETS},
        'status': 'running',
    }
    for tool, command in [
        ('gpu', ['nvidia-smi']),
        ('mpi', [launcher, '--version'] if launcher else []),
        ('cxx_compiler', ['g++', '--version']),
        ('cuda_compiler', ['nvcc', '--version']),
    ]:
        if command and shutil.which(command[0]):
            probe = subprocess.run(command, capture_output=True, text=True)
            metadata[tool] = probe.stdout + probe.stderr
    meta_path = args.results / 'metadata.json'
    meta_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')

    def run_binary(implementation, input_path, window, step, p, output_path,
                   events_path=None, log_tag=None):
        mode = impl_mode(implementation)
        command = [
            str(args.build_dir / BINARIES[implementation]),
            '--input', str(input_path),
            '--window', str(window),
            '--step', str(step),
            '--threshold', str(args.threshold),
            '--output', str(output_path),
            '--mode', mode,
        ]
        if events_path is not None:
            command += ['--events', str(events_path)]
        if implementation.startswith('OMP') or implementation.startswith('CUDA'):
            command += ['--threads', str(p)]
        if implementation.startswith('MPI'):
            command = [launcher, *mpi_auto_flags, '-n', str(p), *command]
        result = subprocess.run(command, env=env, capture_output=True, text=True,
                                timeout=args.timeout or None)
        log_file = None
        if log_tag:
            log_file = logs / (log_tag + '.log')
            log_file.write_text(
                'COMMAND: ' + shlex.join(command) + '\nSTDOUT:\n' +
                result.stdout + '\nSTDERR:\n' + result.stderr,
                encoding='utf-8')
        if result.returncode:
            raise RuntimeError(f'run failed ({result.returncode}): {log_file or command}\n{result.stderr}')
        values = dict(re.findall(r'\b([A-Za-z0-9_]+)=([0-9.eE+\-]+)', result.stderr))
        return values, log_file

    def execute(config, run_id, output):
        implementation, name, window, step, p = config
        key = f'{implementation}_{Path(name).stem}_W{window}_S{step}_p{p}_r{run_id}'
        values, log = run_binary(implementation, args.datasets / name, window, step, p, output, log_tag=key)
        for req_key in ('T_core_s', 'T_total_s', 'windows'):
            if req_key not in values:
                raise RuntimeError(f'missing {req_key}: {log}')
        is_cuda = implementation.startswith('CUDA')
        core = float(values['T_entropy_kernel_event_s'] if is_cuda else values['T_core_s'])
        total = float(values['T_total_s'])
        windows = int(values['windows'])
        boundaries = int(values.get('boundaries', 0))
        events_cnt = int(values.get('events', 0))
        if windows != 1 + (sizes[name] - window) // step:
            raise RuntimeError(f'wrong full-window count: {log}')
        if not math.isfinite(core) or core <= 0 or not math.isfinite(total) or total <= 0:
            raise RuntimeError(f'invalid measured time: {log}')
        row = dict(
            timestamp=datetime.now(timezone.utc).isoformat(),
            implementation=implementation,
            mode=impl_mode(implementation),
            dataset=name,
            file_size_bytes=sizes[name],
            window_size=window,
            step_size=step,
            threads_processes=p,
            run_id=run_id,
            t_core_ms=core * 1000,
            t_total_ms=total * 1000,
            throughput_gbps=sizes[name] / core / 1e9,
            logical_throughput_gbps=windows * window / core / 1e9,
            mpi_mode='local shared-memory' if implementation.startswith('MPI') else '',
            threshold=args.threshold,
            windows=windows,
            boundaries=boundaries,
            events=events_cnt,
            log_path=str(log.relative_to(args.results)),
        )
        if is_cuda:
            mapping = {
                't_h2d_ms': 'T_H2D_wall_s',
                't_entropy_kernel_ms': 'T_entropy_kernel_event_s',
                't_boundary_kernel_ms': 'T_boundary_kernel_event_s',
                't_d2h_ms': 'T_D2H_wall_s',
                't_postprocess_cpu_ms': 'T_postprocess_cpu_s',
                't_h2d_event_ms': 'T_H2D_event_s',
                't_d2h_event_ms': 'T_D2H_event_s',
            }
            for field, k in mapping.items():
                if k not in values:
                    raise RuntimeError(f'CUDA timing field {k} missing: {log}')
                value = float(values[k]) * 1000
                if not math.isfinite(value) or value < 0:
                    raise RuntimeError(f'invalid {k}: {log}')
                row[field] = value
        return row

    def run_supplementary_studies():
        print('Running supplementary studies (data size scaling, k-symbol atomics, accuracy, localization)...', flush=True)
        has_cuda = any(i.startswith('CUDA') for i in implementations)
        # 1. Data size scaling study (10, 25, 50, 100, 180 MB) at W=65536, S=16384.
        if has_cuda:
            size_mbs = [10, 25, 50, 100, 180]
            ds_impls = [i for i in ('Ref-Naive', 'Ref-Incremental', 'OMP', 'OMP-Incremental', 'CUDA', 'CUDA-Incremental')
                        if i in implementations]
            ds_fields = [
                'implementation', 'mode', 'file_size_mb', 'file_size_bytes',
                'window_size', 'step_size', 'threads_processes', 'run_id',
                't_core_ms', 't_total_ms', 'throughput_gbps', 'logical_throughput_gbps',
                't_h2d_ms', 't_entropy_kernel_ms', 't_boundary_kernel_ms', 't_d2h_ms'
            ]
            with tempfile.TemporaryDirectory(prefix='c05_ds_') as tmpdir:
                tmp = Path(tmpdir)
                big_path = tmp / 'scaling_source.bin'
                rng = random.Random(args.seed + 100)
                with big_path.open('wb') as out:
                    for _ in range(max(size_mbs)):
                        out.write(rng.randbytes(1_000_000))
                with (args.results / 'gpu_datasize_scaling.csv').open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=ds_fields)
                    writer.writeheader()
                    for mb in size_mbs:
                        sub_path = tmp / f'random_{mb}MB.bin'
                        with big_path.open('rb') as src, sub_path.open('wb') as dst:
                            shutil.copyfileobj(src, dst, length=1024 * 1024)
                            dst.truncate(mb * 1_000_000)
                        nbytes = mb * 1_000_000
                        w, s = 65536, 16384
                        for impl in ds_impls:
                            p = (canon_omp if impl.startswith('OMP') else
                                 canon_cuda if impl.startswith('CUDA') else 1)
                            for r in range(args.repeats + 1):
                                vals, _ = run_binary(impl, sub_path, w, s, p, tmp / 'out.csv')
                                if r == 0:
                                    continue
                                is_c = impl.startswith('CUDA')
                                core = float(vals['T_entropy_kernel_event_s'] if is_c else vals['T_core_s'])
                                total = float(vals['T_total_s'])
                                wins = int(vals['windows'])
                                row = {
                                    'implementation': impl, 'mode': impl_mode(impl),
                                    'file_size_mb': mb, 'file_size_bytes': nbytes,
                                    'window_size': w, 'step_size': s, 'threads_processes': p, 'run_id': r,
                                    't_core_ms': core * 1000, 't_total_ms': total * 1000,
                                    'throughput_gbps': nbytes / core / 1e9,
                                    'logical_throughput_gbps': wins * w / core / 1e9,
                                    't_h2d_ms': float(vals['T_H2D_wall_s']) * 1000 if is_c else '',
                                    't_entropy_kernel_ms': float(vals['T_entropy_kernel_event_s']) * 1000 if is_c else '',
                                    't_boundary_kernel_ms': float(vals['T_boundary_kernel_event_s']) * 1000 if is_c else '',
                                    't_d2h_ms': float(vals['T_D2H_wall_s']) * 1000 if is_c else '',
                                }
                                writer.writerow(row)

            # 2. Atomic contention k-symbol study (k = 1, 2, 4, 8, 16, 32, 64, 128, 256) on 50 MB.
            ks = [1, 2, 4, 8, 16, 32, 64, 128, 256]
            cuda_impls = [i for i in ('CUDA', 'CUDA-Incremental') if i in implementations]
            ac_fields = [
                'implementation', 'mode', 'distinct_symbols_k', 'theoretical_entropy_bits',
                'file_size_bytes', 'window_size', 'step_size', 'threads_per_block', 'run_id',
                't_entropy_kernel_ms', 'logical_throughput_gbps', 'throughput_gbps'
            ]
            with tempfile.TemporaryDirectory(prefix='c05_ksym_') as tmpdir:
                tmp = Path(tmpdir)
                nbytes = 50_000_000
                w, s = 65536, 16384
                raw_random = random.Random(args.seed + 200).randbytes(1_000_000)
                with (args.results / 'atomic_contention_ksymbol.csv').open('w', newline='', encoding='utf-8') as stream:
                    writer = csv.DictWriter(stream, fieldnames=ac_fields)
                    writer.writeheader()
                    for k in ks:
                        kpath = tmp / f'ksym_{k}.bin'
                        table = bytes(i % k for i in range(256))
                        chunk = raw_random.translate(table)
                        with kpath.open('wb') as out:
                            for _ in range(50):
                                out.write(chunk)
                        for impl in cuda_impls:
                            for r in range(args.repeats + 1):
                                vals, _ = run_binary(impl, kpath, w, s, canon_cuda, tmp / 'out.csv')
                                if r == 0:
                                    continue
                                core = float(vals['T_entropy_kernel_event_s'])
                                wins = int(vals['windows'])
                                writer.writerow({
                                    'implementation': impl,
                                    'mode': impl_mode(impl),
                                    'distinct_symbols_k': k,
                                    'theoretical_entropy_bits': math.log2(k),
                                    'file_size_bytes': nbytes,
                                    'window_size': w,
                                    'step_size': s,
                                    'threads_per_block': canon_cuda,
                                    'run_id': r,
                                    't_entropy_kernel_ms': core * 1000,
                                    'logical_throughput_gbps': wins * w / core / 1e9,
                                    'throughput_gbps': nbytes / core / 1e9,
                                })

        # 3 & 4. Theoretical entropy accuracy, numerical cross-backend accuracy, and boundary localization.
        truth = json.loads((args.datasets / 'ground_truth_boundaries.json').read_text(encoding='utf-8'))
        seg_files = ['mixed_segmented.bin']
        if (args.datasets / 'multi_segmented.bin').is_file():
            seg_files.append('multi_segmented.bin')

        acc_fields = [
            'dataset', 'segment_kind', 'distinct_symbols_k', 'window_size', 'step_size',
            'interior_windows', 'theoretical_entropy', 'miller_madow_bias',
            'mean_empirical_entropy', 'mean_signed_error', 'mean_abs_error', 'max_abs_error'
        ]
        loc_fields = [
            'dataset', 'window_size', 'step_size', 'threshold',
            'ground_truth_boundaries', 'raw_flagged_windows', 'merged_events',
            'matched_events', 'false_positive_events',
            'mean_raw_distance_bytes', 'max_raw_distance_bytes',
            'mean_event_distance_bytes', 'max_event_distance_bytes',
            'max_event_distance_over_step'
        ]
        num_fields = [
            'implementation', 'mode', 'window_size', 'step_size',
            'max_abs_diff_vs_ref_naive', 'mean_abs_diff_vs_ref_naive', 'identical_boundary_flags'
        ]
        k_map = {
            'zeros': 1, 'ksymbol_4': 4, 'ksymbol_16': 16,
            'synthetic_ascii': 23, 'biased_random': 252, 'uniform_256': 256
        }
        with tempfile.TemporaryDirectory(prefix='c05_acc_') as tmpdir:
            tmp = Path(tmpdir)
            ref_impl = 'Ref-Incremental' if 'Ref-Incremental' in implementations else implementations[0]
            with (args.results / 'entropy_accuracy_summary.csv').open('w', newline='', encoding='utf-8') as acc_f, \
                 (args.results / 'boundary_localization_summary.csv').open('w', newline='', encoding='utf-8') as loc_f:
                acc_w = csv.DictWriter(acc_f, fieldnames=acc_fields)
                loc_w = csv.DictWriter(loc_f, fieldnames=loc_fields)
                acc_w.writeheader()
                loc_w.writeheader()
                for sfile in seg_files:
                    finfo = truth.get('files', {}).get(sfile, truth)
                    true_bounds = finfo['boundaries']
                    segments = finfo['segments']
                    for w in args.windows:
                        for div in args.step_divisors:
                            s = w // div
                            out_csv = tmp / f'{sfile}_W{w}_S{s}.csv'
                            ev_csv = tmp / f'{sfile}_W{w}_S{s}_events.csv'
                            run_binary(ref_impl, args.datasets / sfile, w, s, 1, out_csv, events_path=ev_csv)
                            # Save canonical W=max_w, S=max_w//max_div segmentation CSVs to results/.
                            if w == max_w and div == max_div:
                                if sfile == 'mixed_segmented.bin':
                                    shutil.copyfile(out_csv, args.results / 'segmentation.csv')
                                    shutil.copyfile(ev_csv, args.results / 'segmentation_events.csv')
                                elif sfile == 'multi_segmented.bin':
                                    shutil.copyfile(out_csv, args.results / 'segmentation_multi.csv')
                                    shutil.copyfile(ev_csv, args.results / 'segmentation_multi_events.csv')

                            rows = []
                            with out_csv.open(newline='', encoding='utf-8') as f:
                                for r in csv.DictReader(f):
                                    rows.append((int(r['offset']), float(r['entropy']), int(r['is_boundary'])))
                            ev_rows = []
                            with ev_csv.open(newline='', encoding='utf-8') as f:
                                for r in csv.DictReader(f):
                                    ev_rows.append((int(r['region_start']), int(r['region_end']), int(r['estimated_offset'])))

                            # Interior window accuracy per segment (windows strictly inside [start, end_exclusive]).
                            if div == 1:
                                for seg in segments:
                                    st, en = seg['start'], seg['end_exclusive']
                                    ht = float(seg['population_entropy_bits_per_byte'])
                                    kind = seg['kind']
                                    k_sym = k_map.get(kind, 256)
                                    mm_bias = -(k_sym - 1) / (2.0 * w * math.log(2.0)) if k_sym > 1 else 0.0
                                    interior = [h for off, h, _ in rows if off >= st and off + w <= en]
                                    if interior:
                                        signed_errs = [h - ht for h in interior]
                                        abs_errs = [abs(e) for e in signed_errs]
                                        acc_w.writerow({
                                            'dataset': sfile, 'segment_kind': kind,
                                            'distinct_symbols_k': k_sym,
                                            'window_size': w, 'step_size': s,
                                            'interior_windows': len(interior),
                                            'theoretical_entropy': ht,
                                            'miller_madow_bias': mm_bias,
                                            'mean_empirical_entropy': sum(interior) / len(interior),
                                            'mean_signed_error': sum(signed_errs) / len(signed_errs),
                                            'mean_abs_error': sum(abs_errs) / len(abs_errs),
                                            'max_abs_error': max(abs_errs),
                                        })

                            # Boundary localization metrics.
                            flagged_offs = [off for off, _, fl in rows if fl == 1]
                            est_offs = [est for _, _, est in ev_rows]
                            raw_dists = [min(abs(off - b) for off in flagged_offs) for b in true_bounds] if flagged_offs else []
                            ev_dists = [min(abs(est - b) for est in est_offs) for b in true_bounds] if est_offs else []
                            matched = sum(1 for rs, re_, _ in ev_rows if any(rs <= b <= re_ for b in true_bounds))
                            fp = len(ev_rows) - matched
                            loc_w.writerow({
                                'dataset': sfile, 'window_size': w, 'step_size': s, 'threshold': args.threshold,
                                'ground_truth_boundaries': len(true_bounds),
                                'raw_flagged_windows': len(flagged_offs),
                                'merged_events': len(ev_rows),
                                'matched_events': matched,
                                'false_positive_events': fp,
                                'mean_raw_distance_bytes': sum(raw_dists) / len(raw_dists) if raw_dists else '',
                                'max_raw_distance_bytes': max(raw_dists) if raw_dists else '',
                                'mean_event_distance_bytes': sum(ev_dists) / len(ev_dists) if ev_dists else '',
                                'max_event_distance_bytes': max(ev_dists) if ev_dists else '',
                                'max_event_distance_over_step': (max(ev_dists) / s) if ev_dists else '',
                            })

            # Cross-backend numerical comparison on mixed_segmented.bin at W=max_w, S=max_w//max_div.
            w, s = max_w, max_w // max_div
            ref_csv = tmp / 'ref_naive.csv'
            run_binary('Ref-Naive', args.datasets / 'mixed_segmented.bin', w, s, 1, ref_csv)
            with ref_csv.open(newline='', encoding='utf-8') as f:
                ref_data = [(float(r['entropy']), int(r['is_boundary'])) for r in csv.DictReader(f)]
            with (args.results / 'backend_numerical_error.csv').open('w', newline='', encoding='utf-8') as num_f:
                num_w = csv.DictWriter(num_f, fieldnames=num_fields)
                num_w.writeheader()
                for impl in implementations:
                    p = (canon_omp if impl.startswith('OMP') else
                         canon_mpi if impl.startswith('MPI') else
                         canon_cuda if impl.startswith('CUDA') else 1)
                    out_c = tmp / f'num_{impl}.csv'
                    run_binary(impl, args.datasets / 'mixed_segmented.bin', w, s, p, out_c)
                    with out_c.open(newline='', encoding='utf-8') as f:
                        cur = [(float(r['entropy']), int(r['is_boundary'])) for r in csv.DictReader(f)]
                    diffs = [abs(a[0] - b[0]) for a, b in zip(ref_data, cur)]
                    same_flags = all(a[1] == b[1] for a, b in zip(ref_data, cur))
                    num_w.writerow({
                        'implementation': impl, 'mode': impl_mode(impl),
                        'window_size': w, 'step_size': s,
                        'max_abs_diff_vs_ref_naive': max(diffs) if diffs else 0.0,
                        'mean_abs_diff_vs_ref_naive': sum(diffs) / len(diffs) if diffs else 0.0,
                        'identical_boundary_flags': same_flags,
                    })

    try:
        with (args.results / 'raw_results.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            for index, config in enumerate(configurations, 1):
                print(f'[{index}/{len(configurations)}] {config}', flush=True)
                execute(config, 0, artifact)  # warm-up is logged, never written to CSV
                for run_id in range(1, args.repeats + 1):
                    writer.writerow(execute(config, run_id, artifact))
                    stream.flush()

        if not args.skip_supplementary:
            run_supplementary_studies()

        # Ensure segmentation.csv exists even if --skip-supplementary was used.
        window = max_w
        step = window // max_div
        implementation = 'Ref-Incremental' if 'Ref-Incremental' in implementations else implementations[0]
        p = (canon_omp if implementation.startswith('OMP') else
             canon_mpi if implementation.startswith('MPI') else
             canon_cuda if implementation.startswith('CUDA') else 1)
        if not (args.results / 'segmentation.csv').is_file():
            run_binary(implementation, args.datasets / 'mixed_segmented.bin', window, step, p,
                       args.results / 'segmentation.csv',
                       events_path=args.results / 'segmentation_events.csv',
                       log_tag='segmentation_run')
        truth_path = args.datasets / 'ground_truth_boundaries.json'
        shutil.copyfile(truth_path, args.results / 'ground_truth_boundaries.json')
        (args.results / 'segmentation_metadata.json').write_text(json.dumps({
            'implementation': implementation, 'window_size': window, 'step_size': step,
            'threshold': args.threshold, 'file_size_bytes': sizes['mixed_segmented.bin']}, indent=2),
            encoding='utf-8')
        artifact.unlink(missing_ok=True)
        metadata['status'] = 'measurements complete'
        meta_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        if not args.no_plots:
            command = [
                sys.executable, str(root / 'scripts/plot_results.py'),
                '--csv', str(args.results / 'raw_results.csv'),
                '--output-dir', str(args.results / 'plots'),
                '--window', str(max_w),
                '--step-divisor', str(max_div),
                '--omp-p', str(canon_omp),
                '--mpi-p', str(canon_mpi),
                '--cuda-block', str(canon_cuda),
            ]
            if not ({'Ref-Naive', 'OMP', 'MPI', 'CUDA'}.issubset(set(implementations))):
                command += ['--allow-partial']
            subprocess.run(command, check=True)
        metadata['status'] = 'complete'
        meta_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    except Exception as error:
        metadata.update(status='failed', error=str(error))
        meta_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        raise
    print(f'Complete: {args.results}')


if __name__ == '__main__':
    main()
