#!/usr/bin/env python3
"""Standalone CLI visualization: plot entropy vs byte offset and highlight boundary transitions."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True, help='per-window CSV produced by entropy_*')
    parser.add_argument('--events', type=Path, help='optional merged boundary events CSV (--events)')
    parser.add_argument('--ground-truth', type=Path, help='optional ground_truth_boundaries.json')
    parser.add_argument('--file-key', default=None, help='file name key inside ground_truth_boundaries.json')
    parser.add_argument('--output', type=Path, required=True, help='output plot file (.png or .pdf)')
    parser.add_argument('--title', default=None)
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    required = {'offset', 'entropy', 'delta', 'is_boundary'}
    if not required.issubset(df.columns) or df.empty:
        raise ValueError(f'invalid or empty entropy CSV: {args.csv}')

    fig, ax = plt.subplots(figsize=(11, 4.6))
    stride = max(1, len(df) // 100_000)
    view = df.iloc[::stride]
    ax.plot(view['offset'] / 1e6, view['entropy'], linewidth=1.2, color='#0072B2', label='Entropia Shannona H(x)')

    flagged = df.loc[df['is_boundary'] == 1, 'offset'].to_numpy()
    if len(flagged):
        ax.vlines(flagged / 1e6, 0, 8, colors='#E69F00', alpha=0.35, linewidth=0.8,
                  label=f'Okna z |ΔH| ≥ T (n={len(flagged)})')

    if args.events and args.events.is_file():
        ev = pd.read_csv(args.events)
        if not ev.empty and 'estimated_offset' in ev.columns:
            est = ev['estimated_offset'].to_numpy()
            ax.vlines(est / 1e6, 0, 8, colors='#D55E00', linestyle='-.', linewidth=1.3,
                      label=f'Scalone zdarzenia zmiany (n={len(est)})')

    if args.ground_truth and args.ground_truth.is_file():
        truth = json.loads(args.ground_truth.read_text(encoding='utf-8'))
        if args.file_key and 'files' in truth and args.file_key in truth['files']:
            bounds = np.asarray(truth['files'][args.file_key]['boundaries'], dtype=float)
        else:
            bounds = np.asarray(truth.get('boundaries', []), dtype=float)
        for idx, b in enumerate(bounds):
            ax.axvline(b / 1e6, color='black', linestyle='--', linewidth=1.1,
                       label='Granica rzeczywista (ground-truth)' if idx == 0 else None)

    ax.set_xlabel('Pozycja w pliku [MB, $10^6$ B]')
    ax.set_ylabel('Entropia [bit / bajt]')
    ax.set_ylim(-0.25, 8.35)
    ax.grid(True, alpha=0.3)
    ax.set_title(args.title or f'Profil entropii: {args.csv.name}')
    ax.legend(loc='best')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved entropy plot: {args.output}')


if __name__ == '__main__':
    main()
