#!/usr/bin/env python3
"""Publication plots from measured C05 CSVs; no interpolation of missing backends."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

LABELS = [
    'Ref-Naive', 'Ref-Incremental',
    'OMP', 'OMP-Incremental',
    'MPI', 'MPI-Incremental',
    'CUDA', 'CUDA-Incremental',
]
KEYS = ['implementation', 'dataset', 'window_size', 'step_size', 'threads_processes']
DATASETS = ['constant_bytes.bin', 'uniform_random.bin', 'mixed_segmented.bin']


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


def line(ax, x, med, low, high, label, linestyle='-', marker='o'):
    med, low, high = map(np.asarray, (med, low, high))
    ax.errorbar(x, med, yerr=np.vstack((np.maximum(0, med - low), np.maximum(0, high - med))),
                marker=marker, linestyle=linestyle, capsize=3, label=label)


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
    parser.add_argument('--omp-p', type=int, default=12)
    parser.add_argument('--mpi-p', type=int, default=6)
    parser.add_argument('--cuda-block', type=int, default=256)
    args = parser.parse_args()
    if args.step_divisor <= 0 or args.window <= 0 or args.window % args.step_divisor:
        parser.error('positive W and divisor, W divisible by divisor required')
    data = load(args.csv)
    parent = args.csv.resolve().parent
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(context='paper', style='whitegrid', palette='colorblind', font_scale=1.1)
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

    # 1. Strong scaling S(p) and E(p) for OpenMP and MPI (both naive and incremental, core and total).
    scaling_candidates = ['OMP', 'OMP-Incremental', 'MPI', 'MPI-Incremental']
    available = [i for i in scaling_candidates if i in set(selected.implementation)]
    require({'OMP', 'MPI'}.issubset(set(available)), 'Both OMP and MPI are required for full scaling comparison')
    if require(bool(available), 'Brak OMP/MPI dla wybranego W/S i zbioru'):
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
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
                low.append(1.0 if p == 1 else base_min / t_max)
                high.append(1.0 if p == 1 else base_max / t_min)
            ls = '--' if implementation.endswith('Incremental') else '-'
            mk = 's' if implementation.startswith('MPI') else 'o'
            line(axes[0], xs, speed, low, high, implementation, linestyle=ls, marker=mk)
            line(axes[1], xs, np.array(speed) / xs, np.array(low) / xs, np.array(high) / xs,
                 implementation, linestyle=ls, marker=mk)
            maximum_p = max(maximum_p, max(xs))
        ideal = np.arange(1, maximum_p + 1)
        axes[0].plot(ideal, ideal, ':', color='gray', label='Idealne S(p)=p')
        axes[1].axhline(1.0, linestyle=':', color='gray', label='Idealne E(p)=1')
        axes[0].axvline(6, linestyle='-.', color='black', alpha=0.35, label='Rdzenie fizyczne (6)')
        axes[1].axvline(6, linestyle='-.', color='black', alpha=0.35)
        for ax, ylabel in zip(axes, ('Przyspieszenie S(p) = T(1)/T(p) [rdzeń]', 'Efektywność E(p) = S(p)/p')):
            ax.set(xlabel='Liczba wątków (OpenMP) / procesów (MPI) p', ylabel=ylabel)
            ax.legend(fontsize=8.5)
        fig.suptitle(f'{args.dataset}, W={args.window}, S={args.window // args.step_divisor} '
                     '(1 węzeł, 6 rdzeni / 12 wątków; MPI: lokalny shared-memory)')
        save(fig, args.output_dir, 'speedup_efficiency_omp_mpi')

    # 2. Throughput comparison across W for S=W/divisor and S=W.
    resources = {
        'Ref-Naive': 1, 'Ref-Incremental': 1,
        'OMP': args.omp_p, 'OMP-Incremental': args.omp_p,
        'MPI': args.mpi_p, 'MPI-Incremental': args.mpi_p,
        'CUDA': args.cuda_block, 'CUDA-Incremental': args.cuda_block,
    }
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)
    for ax_idx, div_val in enumerate(sorted(data.step_divisor.unique())):
        ax = axes[ax_idx] if len( data.step_divisor.unique() ) > 1 else axes[0]
        sub = data[(data.dataset == args.dataset) & (data.step_divisor == div_val)]
        for implementation in LABELS:
            if implementation not in set(sub.implementation):
                continue
            group = sub[(sub.implementation == implementation)
                        & (sub.threads_processes == resources[implementation])]
            if group.empty:
                continue
            xs, med, low, high = [], [], [], []
            for w, runs in group.groupby('window_size', sort=True):
                m, lo, hi = stats(runs, 'throughput_gbps')
                xs.append(w); med.append(m); low.append(lo); high.append(hi)
            ls = '--' if implementation.endswith('Incremental') else '-'
            line(ax, xs, med, low, high, f'{implementation} ({resources[implementation]})', linestyle=ls)
        ax.set(xscale='log', yscale='log', xlabel='Rozmiar okna W [B]',
               ylabel='Przepustowość wejściowa N/T_core [GB/s]',
               title=f'S = W/{int(div_val)} (zakładka {int(100*(1-1/div_val))}%)' if div_val > 1 else 'S = W (okna rozłączne)')
        ax.legend(fontsize=8)
    fig.suptitle(f'Porównanie przepustowości rdzenia obliczeń ({args.dataset}, mediana i rozrzut min–max)')
    save(fig, args.output_dir, 'throughput_comparison')

    # 3. 2-person scope: Naive vs Incremental speedup ratio across backends at S = W/step_divisor.
    sub_inc = data[(data.dataset == args.dataset) & (data.step_divisor == args.step_divisor)]
    pairs = [
        ('Reference (1 wątek)', 'Ref-Naive', 'Ref-Incremental', 1),
        (f'OpenMP ({args.omp_p} wątków)', 'OMP', 'OMP-Incremental', args.omp_p),
        (f'MPI ({args.mpi_p} procesów)', 'MPI', 'MPI-Incremental', args.mpi_p),
        (f'CUDA (blok {args.cuda_block})', 'CUDA', 'CUDA-Incremental', args.cuda_block),
    ]
    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    plotted_pairs = 0
    for label, naive_name, inc_name, res_p in pairs:
        g_n = sub_inc[(sub_inc.implementation == naive_name) & (sub_inc.threads_processes == res_p)]
        g_i = sub_inc[(sub_inc.implementation == inc_name) & (sub_inc.threads_processes == res_p)]
        if g_n.empty or g_i.empty:
            continue
        xs, ratios, lo_r, hi_r = [], [], [], []
        for w in sorted(set(g_n.window_size) & set(g_i.window_size)):
            tn, tn_min, tn_max = stats(g_n[g_n.window_size == w], 't_core_ms')
            ti, ti_min, ti_max = stats(g_i[g_i.window_size == w], 't_core_ms')
            xs.append(w)
            ratios.append(tn / ti)
            lo_r.append(tn_min / ti_max)
            hi_r.append(tn_max / ti_min)
        line(ax, xs, ratios, lo_r, hi_r, label)
        plotted_pairs += 1
    if plotted_pairs:
        ax.axhline(1.0, linestyle='--', color='gray', label='Brak przyspieszenia (1.0x)')
        ax.set(xscale='log', xlabel='Rozmiar okna W [B]',
               ylabel='Przyspieszenie T_core(naive) / T_core(incremental)',
               title=f'Wpływ przyrostowej aktualizacji histogramu (S = W/{args.step_divisor}, {args.dataset})')
        ax.legend()
        save(fig, args.output_dir, 'naive_vs_incremental_comparison')
    else:
        plt.close(fig)

    # 4. CUDA transfer & kernel breakdown vs window size W.
    cuda = data[(data.implementation == 'CUDA') & (data.threads_processes == args.cuda_block)
                & (data.step_divisor == args.step_divisor)]
    components = ['t_h2d_ms', 't_entropy_kernel_ms', 't_boundary_kernel_ms', 't_d2h_ms']
    if require(not cuda.empty, 'Brak rzeczywistych pomiarów CUDA; pominięto wykresy CUDA'):
        if set(components) - set(cuda.columns) or cuda[components].isna().any().any():
            raise ValueError('CUDA component measurements missing; cannot infer from T_total')
        group = cuda[cuda.dataset == args.dataset]
        if require(not group.empty, 'Brak CUDA dla wybranego zbioru'):
            summary = group.groupby('window_size')[components].median().sort_index()
            fig, ax = plt.subplots(figsize=(9, 5))
            bottom = np.zeros(len(summary))
            comp_labels = ['H2D Copy (wall)', 'Kernel entropii (events)', 'Kernel granic (events)', 'D2H Copy (wall)']
            for column, label in zip(components, comp_labels):
                values = summary[column].to_numpy()
                ax.bar(np.arange(len(summary)), values, bottom=bottom, label=label)
                bottom += values
            ax.set_xticks(np.arange(len(summary)), [str(w) for w in summary.index])
            ax.set(xlabel='Rozmiar okna W [B]', ylabel='Czas składowej [ms]',
                   title=f'Rozkład czasu faz GPU ({args.dataset}, blok={args.cuda_block}, S=W/{args.step_divisor})\n'
                         'Sumy median faz; transfery wall-clock obejmują narzut hosta i buforów pageable')
            ax.legend()
            save(fig, args.output_dir, 'cuda_transfer_breakdown')

        # 5. CUDA block size impact (threads per block = 64, 128, 256, 512, 1024).
        cuda_blocks_df = data[(data.implementation.isin(['CUDA', 'CUDA-Incremental']))
                              & (data.window_size == args.window)
                              & (data.step_size == args.window // args.step_divisor)]
        if cuda_blocks_df.threads_processes.nunique() > 1:
            fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
            for impl in ('CUDA', 'CUDA-Incremental'):
                for dname in DATASETS:
                    sub_b = cuda_blocks_df[(cuda_blocks_df.implementation == impl)
                                           & (cuda_blocks_df.dataset == dname)]
                    if sub_b.threads_processes.nunique() < 2:
                        continue
                    xs, med_t, lo_t, hi_t = [], [], [], []
                    med_g, lo_g, hi_g = [], [], []
                    for blk, runs in sub_b.groupby('threads_processes', sort=True):
                        mt, lt, ht = stats(runs, 't_entropy_kernel_ms')
                        mg, lg, hg = stats(runs, 'logical_throughput_gbps')
                        xs.append(blk)
                        med_t.append(mt); lo_t.append(lt); hi_t.append(ht)
                        med_g.append(mg); lo_g.append(lg); hi_g.append(hg)
                    ls = '--' if impl.endswith('Incremental') else '-'
                    short_d = dname.replace('.bin', '')
                    line(axes[0], xs, med_t, lo_t, hi_t, f'{impl} ({short_d})', linestyle=ls)
                    line(axes[1], xs, med_g, lo_g, hi_g, f'{impl} ({short_d})', linestyle=ls)
            axes[0].set(xscale='log', xticks=[64, 128, 256, 512, 1024],
                        xticklabels=['64', '128', '256', '512', '1024'],
                        xlabel='Liczba wątków w bloku CUDA', ylabel='Czas kernela entropii [ms]',
                        title=f'Czas kernela vs rozmiar bloku (W={args.window}, S={args.window // args.step_divisor})')
            axes[1].set(xscale='log', xticks=[64, 128, 256, 512, 1024],
                        xticklabels=['64', '128', '256', '512', '1024'],
                        xlabel='Liczba wątków w bloku CUDA', ylabel='Przepustowość logiczna K·W / T_kernel [GB/s]',
                        title='Przepustowość logiczna vs rozmiar bloku')
            axes[0].legend(fontsize=7.5)
            axes[1].legend(fontsize=7.5)
            save(fig, args.output_dir, 'cuda_block_size_impact')

        # 6. Atomic contention impact (constant vs uniform across W, plus k-symbol curve if available).
        names = ['constant_bytes.bin', 'uniform_random.bin']
        group = cuda[cuda.dataset.isin(names)]
        ksym_path = parent / 'atomic_contention_ksymbol.csv'
        if require(set(group.dataset) == set(names), 'Brak pary zero/random CUDA'):
            has_ksym = ksym_path.is_file()
            fig, axes = plt.subplots(1, 2 if has_ksym else 1, figsize=(12.5, 4.8) if has_ksym else (8.5, 5))
            ax0 = axes[0] if has_ksym else axes
            for impl in ('CUDA', 'CUDA-Incremental'):
                sub_i = data[(data.implementation == impl)
                             & (data.threads_processes == args.cuda_block)
                             & (data.step_divisor == args.step_divisor)
                             & (data.dataset.isin(names))]
                if sub_i.empty:
                    continue
                ls = '--' if impl.endswith('Incremental') else '-'
                for name in names:
                    xs, med, low, high = [], [], [], []
                    for w, runs in sub_i[sub_i.dataset == name].groupby('window_size', sort=True):
                        m, lo, hi = stats(runs, 'logical_throughput_gbps')
                        xs.append(w); med.append(m); low.append(lo); high.append(hi)
                    line(ax0, xs, med, low, high, f'{impl}: {name}', linestyle=ls)
            ax0.set(xscale='log', xlabel='Rozmiar okna W [B]',
                    ylabel='Przepustowość logiczna K·W / T_kernel [GB/s]',
                    title=f'Skrajne rozkłady (k=1 vs k=256), S=W/{args.step_divisor}')
            ax0.legend(fontsize=8)
            if has_ksym:
                kdf = pd.read_csv(ksym_path)
                ax1 = axes[1]
                for impl, g_impl in kdf.groupby('implementation'):
                    xs, med, low, high = [], [], [], []
                    for k, runs in g_impl.groupby('distinct_symbols_k', sort=True):
                        m, lo, hi = stats(runs, 'logical_throughput_gbps')
                        xs.append(k); med.append(m); low.append(lo); high.append(hi)
                    ls = '--' if str(impl).endswith('Incremental') else '-'
                    line(ax1, xs, med, low, high, str(impl), linestyle=ls)
                ax1.set(xscale='log', xticks=[1, 2, 4, 8, 16, 32, 64, 128, 256],
                        xticklabels=['1', '2', '4', '8', '16', '32', '64', '128', '256'],
                        xlabel='Liczba różnych bajtów w alfabecie k (koncentracja = 1/k)',
                        ylabel='Przepustowość logiczna K·W / T_kernel [GB/s]',
                        title=f'Wpływ koncentracji bajtów na kolizje atomic (W={args.window}, S={args.window // args.step_divisor})')
                ax1.legend()
            save(fig, args.output_dir, 'atomic_contention_impact')

    # 7. GPU and CPU scaling vs input data size (10..180 MB).
    ds_path = parent / 'gpu_datasize_scaling.csv'
    if ds_path.is_file():
        ds = pd.read_csv(ds_path)
        if not ds.empty:
            fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
            for impl in [i for i in LABELS if i in set(ds.implementation)]:
                sub_d = ds[ds.implementation == impl]
                xs, med_c, lo_c, hi_c = [], [], [], []
                med_t, lo_t, hi_t = [], [], []
                for mb, runs in sub_d.groupby('file_size_mb', sort=True):
                    mc, lc, hc = stats(runs, 'throughput_gbps')
                    mt, lt, ht = stats(runs, 't_total_ms')
                    xs.append(mb)
                    med_c.append(mc); lo_c.append(lc); hi_c.append(hc)
                    med_t.append(mt); lo_t.append(lt); hi_t.append(ht)
                ls = '--' if impl.endswith('Incremental') else '-'
                line(axes[0], xs, med_c, lo_c, hi_c, impl, linestyle=ls)
                line(axes[1], xs, med_t, lo_t, hi_t, impl, linestyle=ls)
            axes[0].set(xlabel='Rozmiar pliku wejściowego N [MB]',
                        ylabel='Przepustowość rdzenia N / T_core [GB/s]',
                        title='Przepustowość rdzenia vs rozmiar danych (W=65536, S=16384)')
            axes[1].set(xlabel='Rozmiar pliku wejściowego N [MB]',
                        ylabel='Całkowity czas przetwarzania T_total [ms]',
                        title='Czas całkowity (z I/O i transferami PCIe) vs rozmiar danych')
            axes[0].legend(fontsize=8)
            axes[1].legend(fontsize=8)
            save(fig, args.output_dir, 'gpu_datasize_scaling')

    # 8. Theoretical vs empirical entropy accuracy across window sizes W.
    acc_path = parent / 'entropy_accuracy_summary.csv'
    if acc_path.is_file():
        acc = pd.read_csv(acc_path)
        if not acc.empty:
            fig, ax = plt.subplots(figsize=(8.8, 4.8))
            for (dname, kind), grp in acc.groupby(['dataset', 'segment_kind']):
                if kind == 'zeros':
                    continue
                grp = grp.sort_values('window_size')
                ax.plot(grp.window_size, grp.mean_abs_error, marker='o',
                        label=f'{kind} (k={grp.distinct_symbols_k.iloc[0]}, emp. |ΔH|)')
                ax.plot(grp.window_size, np.abs(grp.miller_madow_bias), linestyle=':', alpha=0.7,
                        label=f'{kind} (teor. bias (k-1)/(2W ln 2))')
            ax.set(xscale='log', yscale='log', xlabel='Rozmiar okna W [B]',
                   ylabel='Średni błąd bezwzględny |H_emp - H_teor| [bit/bajt]',
                   title='Błąd estymacji entropii z próby skończonej względem entropii populacji')
            ax.legend(fontsize=7.5, ncol=2)
            save(fig, args.output_dir, 'entropy_error_analysis')

    # 9. Segmentation & boundary detection plot (mixed_segmented.bin + multi_segmented.bin if present).
    segmentation = parent / 'segmentation.csv'
    truth_file = parent / 'ground_truth_boundaries.json'
    meta_file = parent / 'segmentation_metadata.json'
    if require(segmentation.is_file() and truth_file.is_file() and meta_file.is_file(),
               'Brak danych segmentacji/ground-truth/metadanych'):
        series = pd.read_csv(segmentation)
        meta = json.loads(meta_file.read_text(encoding='utf-8'))
        truth = json.loads(truth_file.read_text(encoding='utf-8'))
        detected = series.loc[series.is_boundary == 1, 'offset'].to_numpy()
        ground = np.array(truth['boundaries'], dtype=np.int64)
        ev_file = parent / 'segmentation_events.csv'
        ev_est = pd.read_csv(ev_file)['estimated_offset'].to_numpy() if ev_file.is_file() else np.array([])

        multi_seg = parent / 'segmentation_multi.csv'
        multi_ev = parent / 'segmentation_multi_events.csv'
        has_multi = multi_seg.is_file() and 'files' in truth and 'multi_segmented.bin' in truth['files']

        fig, axes = plt.subplots(2 if has_multi else 1, 1, figsize=(11, 8.2 if has_multi else 4.8))
        ax0 = axes[0] if has_multi else axes
        stride = max(1, len(series) // 100000)
        view = series.iloc[::stride]
        ax0.plot(view.offset / 1e6, view.entropy, linewidth=1.2, label='Entropia okien H(x)')
        if len(detected):
            ax0.vlines(detected / 1e6, 0, 8, colors='orange', alpha=0.35, linewidth=0.8,
                       label=f'Okna z |ΔH| ≥ T (n={len(detected)})')
        if len(ev_est):
            ax0.vlines(ev_est / 1e6, 0, 8, colors='#D55E00', linestyle='-.', linewidth=1.2,
                       label=f'Scalone zdarzenia zmiany (n={len(ev_est)})')
        for index, boundary in enumerate(ground):
            ax0.axvline(boundary / 1e6, color='black', linestyle='--',
                        label='Granica ground-truth' if index == 0 else None)
        ax0.set(xlabel='Offset pliku [MB, 10⁶ B]', ylabel='Entropia [bit/bajt]', ylim=(-0.2, 8.3),
                title=f"mixed_segmented.bin (3 segmenty): W={meta['window_size']}, S={meta['step_size']}, próg={meta['threshold']}")
        ax0.legend(loc='upper right', fontsize=8.5)

        if has_multi:
            ax1 = axes[1]
            s2 = pd.read_csv(multi_seg)
            det2 = s2.loc[s2.is_boundary == 1, 'offset'].to_numpy()
            ev2 = pd.read_csv(multi_ev)['estimated_offset'].to_numpy() if multi_ev.is_file() else np.array([])
            gt2 = np.array(truth['files']['multi_segmented.bin']['boundaries'], dtype=np.int64)
            v2 = s2.iloc[::max(1, len(s2) // 100000)]
            ax1.plot(v2.offset / 1e6, v2.entropy, linewidth=1.2, label='Entropia okien H(x)')
            if len(det2):
                ax1.vlines(det2 / 1e6, 0, 8, colors='orange', alpha=0.35, linewidth=0.8,
                           label=f'Okna z |ΔH| ≥ T (n={len(det2)})')
            if len(ev2):
                ax1.vlines(ev2 / 1e6, 0, 8, colors='#D55E00', linestyle='-.', linewidth=1.2,
                           label=f'Scalone zdarzenia zmiany (n={len(ev2)})')
            for index, boundary in enumerate(gt2):
                ax1.axvline(boundary / 1e6, color='black', linestyle='--',
                            label='Granica ground-truth' if index == 0 else None)
            ax1.set(xlabel='Offset pliku [MB, 10⁶ B]', ylabel='Entropia [bit/bajt]', ylim=(-0.2, 8.3),
                    title=f"multi_segmented.bin (5 segmentów: k=1, 4, 23, 256, 16): W={meta['window_size']}, S={meta['step_size']}, próg={meta['threshold']}")
            ax1.legend(loc='upper right', fontsize=8.5)

        save(fig, args.output_dir, 'segmentation_accuracy')
        distances = [{
            'ground_truth_offset': int(g),
            'nearest_raw_window_distance_bytes': int(np.min(np.abs(detected - g))) if len(detected) else None,
            'nearest_merged_event_distance_bytes': int(np.min(np.abs(ev_est - g))) if len(ev_est) else None,
        } for g in ground]
        (args.output_dir / 'segmentation_diagnostics.json').write_text(json.dumps({
            'detected_raw_windows': int(len(detected)),
            'detected_merged_events': int(len(ev_est)),
            'ground_truth_count': int(len(ground)),
            'nearest_distances': distances,
            'note': 'Merged events collapse consecutive flagged windows overlapping one transition.'
        }, indent=2), encoding='utf-8')

    (args.output_dir / 'plot_manifest.json').write_text(json.dumps({
        'source_csv': str(args.csv.resolve()),
        'selection': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        'warnings': notices, 'png_dpi': 300, 'pdf': 'vector graphics',
        'speedup': 'ratio of medians; min-max conservative envelope; baseline same backend p=1'}, indent=2),
        encoding='utf-8')
    for message in notices:
        print('WARNING:', message)
    print('Plots saved:', args.output_dir)


if __name__ == '__main__':
    main()
