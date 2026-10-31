#!/usr/bin/env python3
"""Generate deterministic synthetic entropy fixtures. MB means 1,000,000 bytes."""
import argparse
import hashlib
import json
import math
import random
from pathlib import Path


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('value must be positive')
    return number


def write_segment(out, size, kind, rng, chunk_size, digest):
    alphabet = b'abcdefghijklmnopqrstu \n'
    translation = bytes(0 if 1 <= i <= 4 else i for i in range(256))
    remaining = size
    while remaining:
        n = min(remaining, chunk_size)
        if kind == 'constant':
            block = b'\x00' * n
        elif kind == 'uniform':
            block = rng.randbytes(n)
        elif kind == 'ascii':
            block = bytes(rng.choices(alphabet, k=n))
        elif kind == 'high_entropy':
            block = rng.randbytes(n).translate(translation)
        elif kind.startswith('ksymbol_'):
            k = int(kind.split('_')[1])
            mask = bytes(i % k for i in range(256))
            block = rng.randbytes(n).translate(mask)
        else:
            raise ValueError(f'unknown segment kind: {kind}')
        out.write(block)
        digest.update(block)
        remaining -= n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('datasets'))
    parser.add_argument('--constant-mb', type=positive, default=100)
    parser.add_argument('--random-mb', type=positive, default=100)
    parser.add_argument('--segment-mb', type=positive, default=50)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--chunk-bytes', type=positive, default=1_000_000)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    segment = args.segment_mb * 1_000_000
    m = 1_000_000
    specs = [
        ('constant_bytes.bin', [(args.constant_mb * m, 'constant')]),
        ('uniform_random.bin', [(args.random_mb * m, 'uniform')]),
        ('mixed_segmented.bin', [(segment, 'ascii'), (segment, 'high_entropy'),
                                 (segment, 'constant')]),
        ('multi_segmented.bin', [
            (20 * (segment // 50), 'constant'),
            (30 * (segment // 50), 'ksymbol_4'),
            (40 * (segment // 50), 'ascii'),
            (30 * (segment // 50), 'uniform'),
            (30 * (segment // 50), 'ksymbol_16'),
        ]),
    ]
    manifest = {}
    for index, (name, segments) in enumerate(specs):
        rng = random.Random(args.seed + index)
        digest = hashlib.sha256()
        path = args.output_dir / name
        with path.open('wb') as out:
            for size, kind in segments:
                write_segment(out, size, kind, rng, args.chunk_bytes, digest)
        expected_size = sum(size for size, _ in segments)
        if path.stat().st_size != expected_size:
            raise RuntimeError(f'incorrect generated size: {path}')
        manifest[name] = {'size_bytes': expected_size, 'sha256': digest.hexdigest()}
        print(f'{name}: {expected_size} bytes, sha256={digest.hexdigest()}')
    high_h = -(5 / 256) * math.log2(5 / 256) - 251 * (1 / 256) * math.log2(1 / 256)
    scale = segment // 50
    multi_bounds = [20 * scale, 50 * scale, 90 * scale, 120 * scale]
    truth = {
        'file': 'mixed_segmented.bin', 'size_bytes': 3 * segment,
        'unit': 'byte', 'offset_convention': 'zero-based start of next segment',
        'boundaries': [segment, 2 * segment],
        'segments': [
            {'start': 0, 'end_exclusive': segment, 'kind': 'synthetic_ascii',
             'population_entropy_bits_per_byte': math.log2(23)},
            {'start': segment, 'end_exclusive': 2 * segment, 'kind': 'biased_random',
             'population_entropy_bits_per_byte': high_h},
            {'start': 2 * segment, 'end_exclusive': 3 * segment, 'kind': 'zeros',
             'population_entropy_bits_per_byte': 0.0},
        ],
        'files': {
            'mixed_segmented.bin': {
                'size_bytes': 3 * segment,
                'boundaries': [segment, 2 * segment],
                'segments': [
                    {'start': 0, 'end_exclusive': segment, 'kind': 'synthetic_ascii',
                     'population_entropy_bits_per_byte': math.log2(23)},
                    {'start': segment, 'end_exclusive': 2 * segment, 'kind': 'biased_random',
                     'population_entropy_bits_per_byte': high_h},
                    {'start': 2 * segment, 'end_exclusive': 3 * segment, 'kind': 'zeros',
                     'population_entropy_bits_per_byte': 0.0},
                ],
            },
            'multi_segmented.bin': {
                'size_bytes': 150 * scale,
                'boundaries': multi_bounds,
                'segments': [
                    {'start': 0, 'end_exclusive': multi_bounds[0], 'kind': 'zeros',
                     'population_entropy_bits_per_byte': 0.0},
                    {'start': multi_bounds[0], 'end_exclusive': multi_bounds[1], 'kind': 'ksymbol_4',
                     'population_entropy_bits_per_byte': 2.0},
                    {'start': multi_bounds[1], 'end_exclusive': multi_bounds[2], 'kind': 'synthetic_ascii',
                     'population_entropy_bits_per_byte': math.log2(23)},
                    {'start': multi_bounds[2], 'end_exclusive': multi_bounds[3], 'kind': 'uniform_256',
                     'population_entropy_bits_per_byte': 8.0},
                    {'start': multi_bounds[3], 'end_exclusive': 150 * scale, 'kind': 'ksymbol_16',
                     'population_entropy_bits_per_byte': 4.0},
                ],
            },
        },
        'seed': args.seed, 'chunk_bytes': args.chunk_bytes,
        'notes': ['Synthetic ASCII, not natural-language prose.',
                  'High-entropy segment is biased random, not a compressed stream.',
                  'Window entropy depends on W and sampling; boundary detection is not guaranteed.',
                  'Reproducibility requires the same Python random implementation and chunk size.'],
    }
    (args.output_dir / 'ground_truth_boundaries.json').write_text(
        json.dumps(truth, indent=2) + '\n', encoding='utf-8')
    (args.output_dir / 'dataset_manifest.json').write_text(
        json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
