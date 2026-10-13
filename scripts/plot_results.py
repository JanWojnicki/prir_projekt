#!/usr/bin/env python3
"""Publication plots from measured C05 CSV; no interpolation of missing backends."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

LABELS = ['Ref-Naive', 'Ref-Incremental', 'OMP', 'MPI', 'CUDA']
KEYS = ['implementation', 'dataset', 'window_size', 'step_size', 'threads_processes']


def load(path):
    data = pd.read_csv(path)
    required = KEYS + ['file_size_bytes', 'run_id', 't_core_ms', 't_total_ms', 'throughput_gbps']
    missing = set(required) - set(data.columns)
    if missing:
        raise ValueError(f'missing columns: {sorted(missing)}')
    if data.empty or data[required].isna().any().any():
        raise ValueError('empty CSV or missing required values')
    if not set(data.implementation).issubset(LABELS):
        raise ValueError('unknown implementation')
    for column in required[2:]:
        if column in ('implementation', 'dataset'):
            continue
        data[column] = pd.to_numeric(data[column], errors='raise')
        if not np.isfinite(data[column]).all() or (data[column] <= 0).any():
            raise ValueError(f'invalid numeric column {column}')
    for column in ('window_size', 'step_size', 'threads_processes', 'file_size_bytes', 'run_id'):
        if (data[column] % 1 != 0).any():
            raise ValueError(f'noninteger {column}')
    if data.duplicated(KEYS + ['run_id']).any():
        raise ValueError('duplicate configuration/run_id; mixed sessions?')
    for key, group in data.groupby(KEYS):
        if len(group) < 5 or set(group.run_id) != set(range(1, len(group) + 1)):
            raise ValueError(f'at least five contiguous measured runs required: {key}')
    if not np.allclose(data.throughput_gbps,
                       data.file_size_bytes / (data.t_core_ms / 1000) / 1e9, rtol=1e-6):
        raise ValueError('throughput definition mismatch')
    data['step_divisor'] = data.window_size / data.step_size
    return data


def stats(group, column):
    values = group[column].to_numpy(dtype=float)
    return float(np.median(values)), float(np.min(values)), float(np.max(values))


def line(ax, x, med, low, high, label):
    med, low, high = map(np.asarray, (med, low, high))
    ax.errorbar(x, med, yerr=np.vstack((np.maximum(0, med - low), np.maximum(0, high - med))),
                marker='o', capsize=3, label=label)


def save(fig, directory, name):
    fig.savefig(directory / (name + '.png'), dpi=300, bbox_inches='tight')
    fig.savefig(directory / (name + '.pdf'), dpi=300, bbox_inches='tight')
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=Path('results/raw_results.csv'))
    parser.add_argument('--output-dir', type=Path, default=Path('results/plots'))
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--dataset', default='mixed_segmented.bin')
    parser.add_argument('--window', type=int, default=65536)
    parser.add_argument('--step-divisor', type=int, default=4)
    parser.add_argument('--omp-p', type=int, default=16)
    parser.add_argument('--mpi-p', type=int, default=8)
    parser.add_argument('--cuda-block', type=int, default=256)
    args = parser.parse_args()
    if args.step_divisor <= 0 or args.window <= 0 or args.window % args.step_divisor:
        parser.error('positive W and divisor, W divisible by divisor required')
    data = load(args.csv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(context='paper', style='whitegrid', palette='colorblind', font_scale=1.15)
    plt.rcParams.update({'pdf.fonttype': 42, 'ps.fonttype': 42, 'figure.constrained_layout.use': True})
    notices = []
    def require(condition, message):
        if condition:
            return True
        if not args.allow_partial:
            raise ValueError(message)
        notices.append(message)
        return False
    selected = data[(data.dataset == args.dataset) & (data.window_size == args.window)
                    & (data.step_size == args.window // args.step_divisor)]
    # 1: strong scaling at a fixed dataset, W and S. Reference is backend p=1.
    available = [i for i in ('OMP', 'MPI') if i in set(selected.implementation)]
    require(set(available) == {'OMP', 'MPI'}, 'Both OMP and MPI are required for full scaling comparison')
    if require(bool(available), 'Brak OMP/MPI dla wybranego W/S i zbioru'):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
        maximum_p = 1
        for implementation in available:
            group = selected[selected.implementation == implementation]
            baseline = group[group.threads_processes == 1]
            if not require(not baseline.empty, f'Brak p=1 dla {implementation}'):
                continue
            base, base_min, base_max = stats(baseline, 't_core_ms')
            xs, speed, low, high = [], [], [], []
            for p, runs in group.groupby('threads_processes', sort=True):
                t, t_min, t_max = stats(runs, 't_core_ms')
                xs.append(p)
                speed.append(base / t)
                # Conservative min-max ratio envelope, not a confidence interval.
                low.append(1.0 if p == 1 else base_min / t_max)
                high.append(1.0 if p == 1 else base_max / t_min)
            line(axes[0], xs, speed, low, high, implementation)
            line(axes[1], xs, np.array(speed) / xs, np.array(low) / xs, np.array(high) / xs, implementation)
            maximum_p = max(maximum_p, max(xs))
        ideal = np.arange(1, maximum_p + 1)
        axes[0].plot(ideal, ideal, '--', color='gray', label='Idealne S(p)=p')
        axes[1].axhline(1, linestyle='--', color='gray', label='Idealne E(p)=1')
        for ax, ylabel in zip(axes, ('Przyspieszenie S(p)', 'Efektywność E(p)')):
            ax.set(xlabel='Liczba wątków / procesów p', ylabel=ylabel)
            ax.legend()
        fig.suptitle(f'{args.dataset}, W={args.window}, S={args.window // args.step_divisor}\n'
                     'Mediana; zakres min–max ilorazów. MPI: lokalny shared-memory')
        save(fig, args.output_dir, 'speedup_efficiency_omp_mpi')
    # 2: compare fixed resource counts; never choose fastest p separately for each W.
    resources = {'Ref-Naive': 1, 'Ref-Incremental': 1, 'OMP': args.omp_p,
                 'MPI': args.mpi_p, 'CUDA': args.cuda_block}
    throughput = data[(data.dataset == args.dataset) & (data.step_divisor == args.step_divisor)]
    fig, ax = plt.subplots(figsize=(8.5, 5))
    plotted = 0
    for implementation in LABELS:
        group = throughput[(throughput.implementation == implementation)
                           & (throughput.threads_processes == resources[implementation])]
        if not require(not group.empty, f'Brak {implementation} p/blok={resources[implementation]} w porównaniu'):
            continue
        xs, med, low, high = [], [], [], []
        for w, runs in group.groupby('window_size', sort=True):
            m, lo, hi = stats(runs, 'throughput_gbps')
            xs.append(w); med.append(m); low.append(lo); high.append(hi)
        line(ax, xs, med, low, high, f'{implementation} ({resources[implementation]})')
        plotted += 1
    if plotted:
        ax.set(xscale='log', xlabel='Rozmiar okna W [bajty]', ylabel='Przepustowość wejściowa N/T_core [GB/s]',
               title=f'{args.dataset}, S=W/{args.step_divisor}; mediana i min–max')
        ax.legend()
        save(fig, args.output_dir, 'throughput_comparison')
    else:
        plt.close(fig)
    cuda = data[(data.implementation == 'CUDA') & (data.threads_processes == args.cuda_block)
                & (data.step_divisor == args.step_divisor)]
    # 3: component medians are not necessarily a median total; transfer wall time includes staging.
    components = ['t_h2d_ms', 't_entropy_kernel_ms', 't_boundary_kernel_ms', 't_d2h_ms']
    if require(not cuda.empty, 'Brak rzeczywistych pomiarów CUDA; pominięto wykresy CUDA'):
        if set(components) - set(cuda.columns) or cuda[components].isna().any().any():
            raise ValueError('CUDA component measurements missing; cannot infer from T_total')
        if (cuda[components] < 0).any().any() or not np.isfinite(cuda[components]).all().all():
            raise ValueError('invalid CUDA component times')
        group = cuda[cuda.dataset == args.dataset]
        if require(not group.empty, 'Brak CUDA dla wybranego zbioru'):
            summary = group.groupby('window_size')[components].median().sort_index()
            fig, ax = plt.subplots(figsize=(9, 5))
            bottom = np.zeros(len(summary))
            labels = ['H2D Copy (wall)', 'Kernel Compute (events)', 'Kernel granic (events)', 'D2H Copy (wall)']
            for column, label in zip(components, labels):
                values = summary[column].to_numpy()
                ax.bar(np.arange(len(summary)), values, bottom=bottom, label=label)
                bottom += values
            ax.set_xticks(np.arange(len(summary)), [str(w) for w in summary.index])
            ax.set(xlabel='Rozmiar okna W [bajty]', ylabel='Czas składowej [ms]',
                   title=f'{args.dataset}, blok={args.cuda_block}, S=W/{args.step_divisor}\n'
                         'Sumy median faz; transfery obejmują narzut hosta, nie tylko PCIe')
            ax.legend()
            save(fig, args.output_dir, 'cuda_transfer_breakdown')
        # 4: matched W/S/block and sizes. Plot logical work throughput, not N/T.
        names = ['constant_bytes.bin', 'uniform_random.bin']
        group = cuda[cuda.dataset.isin(names)]
        if require(set(group.dataset) == set(names), 'Brak pary zero/random CUDA'):
            if 'logical_throughput_gbps' not in group:
                raise ValueError('logical_throughput_gbps required for atomic comparison')
            if not np.isfinite(group.logical_throughput_gbps).all() or (group.logical_throughput_gbps <= 0).any():
                raise ValueError('invalid logical CUDA throughput')
            for w, runs in group.groupby('window_size'):
                if set(runs.dataset) != set(names) or runs.file_size_bytes.nunique() != 1:
                    raise ValueError(f'zero/random must have matched sizes and W/S/block: W={w}')
            fig, ax = plt.subplots(figsize=(8.5, 5))
            for name in names:
                xs, med, low, high = [], [], [], []
                for w, runs in group[group.dataset == name].groupby('window_size', sort=True):
                    m, lo, hi = stats(runs, 'logical_throughput_gbps')
                    xs.append(w); med.append(m); low.append(lo); high.append(hi)
                line(ax, xs, med, low, high, name)
            ax.set(xscale='log', xlabel='Rozmiar okna W [bajty]', ylabel='Logiczne bajty okien / czas kernela [GB/s]',
                   title=f'Wpływ rozkładu danych; blok={args.cuda_block}, S=W/{args.step_divisor}\n'
                         'Histogram + log2 + redukcja: nie izolowany koszt atomicAdd')
            ax.legend()
            save(fig, args.output_dir, 'atomic_contention_impact')
    # 5: actual entropy CSV and explicit truth; never infer ground truth from file length.
    parent = args.csv.resolve().parent
    segmentation = parent / 'segmentation.csv'
    truth_file = parent / 'ground_truth_boundaries.json'
    meta_file = parent / 'segmentation_metadata.json'
    if require(segmentation.is_file() and truth_file.is_file() and meta_file.is_file(), 'Brak danych segmentacji/ground-truth/metadanych'):
        series = pd.read_csv(segmentation)
        if set(['offset', 'entropy', 'delta', 'is_boundary']) - set(series.columns) or series.empty:
            raise ValueError('invalid segmentation CSV')
        if not np.isfinite(series[['offset', 'entropy', 'delta']]).all().all():
            raise ValueError('nonfinite segmentation values')
        if not series.is_boundary.isin([0, 1]).all() or (series.offset.diff().dropna() <= 0).any():
            raise ValueError('invalid flags or offsets')
        meta = json.loads(meta_file.read_text())
        truth = json.loads(truth_file.read_text())
        if truth.get('file') != 'mixed_segmented.bin' or truth['size_bytes'] != meta['file_size_bytes']:
            raise ValueError('ground truth does not match segmentation file')
        expected = np.arange(len(series), dtype=np.int64) * meta['step_size']
        if not np.array_equal(series.offset.to_numpy(), expected):
            raise ValueError('segmentation offsets inconsistent with metadata')
        detected = series.loc[series.is_boundary == 1, 'offset'].to_numpy()
        ground = np.array(truth['boundaries'], dtype=np.int64)
        if (ground <= 0).any() or (ground >= truth['size_bytes']).any():
            raise ValueError('invalid ground truth offsets')
        fig, ax = plt.subplots(figsize=(11, 4.8))
        # Downsample only the entropy line; all detected boundaries remain visible.
        stride = max(1, len(series) // 100000)
        view = series.iloc[::stride]
        ax.plot(view.offset / 1e6, view.entropy, linewidth=1.2, label='Entropia okien')
        if len(detected):
            ax.vlines(detected / 1e6, 0, 8, colors='orange', alpha=0.35, linewidth=0.7, label='Wykryte granice')
        for index, boundary in enumerate(ground):
            ax.axvline(boundary / 1e6, color='black', linestyle='--', label='Ground-truth' if index == 0 else None)
        ax.set(xlabel='Offset pliku [MB, 10⁶ bajtów]', ylabel='Entropia [bit/bajt]', ylim=(-0.2, 8.3),
               title=f"mixed_segmented.bin: W={meta['window_size']}, S={meta['step_size']}, próg={meta['threshold']}\n"
                     f'Wykryto {len(detected)} granic; ground-truth: {len(ground)}')
        ax.legend()
        save(fig, args.output_dir, 'segmentation_accuracy')
        # Distances are descriptive, not precision/recall without a matching tolerance.
        distances = [{'ground_truth_offset': int(g), 'nearest_detected_distance_bytes':
                      int(np.min(np.abs(detected - g))) if len(detected) else None} for g in ground]
        (args.output_dir / 'segmentation_diagnostics.json').write_text(json.dumps({
            'detected_count': len(detected), 'ground_truth_count': len(ground),
            'nearest_distances': distances, 'note': 'No precision/recall claimed; sliding windows shift/smooth transitions.'}, indent=2))
    (args.output_dir / 'plot_manifest.json').write_text(json.dumps({
        'source_csv': str(args.csv.resolve()), 'selection': vars(args) | {'csv': str(args.csv), 'output_dir': str(args.output_dir)},
        'warnings': notices, 'png_dpi': 300, 'pdf': 'vector graphics',
        'speedup': 'ratio of medians; min-max conservative envelope; baseline same backend p=1'}, indent=2))
    for message in notices:
        print('WARNING:', message)
    print('Plots saved:', args.output_dir)


if __name__ == '__main__':
    main()
