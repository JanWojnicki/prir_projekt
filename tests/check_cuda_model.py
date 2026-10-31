#!/usr/bin/env python3
"""Host model of CUDA reduction, grid-stride indexing, and sliding shared-histogram updates."""
import math
import random


def main():
    rng = random.Random(2026)
    cases = 0
    for threads in (64, 128, 256, 512, 1024):
        for _ in range(100):
            histogram = [rng.randrange(1000) for _ in range(256)]
            window = sum(histogram)
            original = [-(c / window) * math.log2(c / window) if c else 0.0
                        for c in histogram]
            terms = original.copy()
            stride = 128
            while stride:
                # Snapshot models the barrier between successive reduction stages.
                before = terms.copy()
                for thread in range(threads):
                    for index in range(thread, stride, threads):
                        terms[index] = before[index] + before[index + stride]
                stride //= 2
            assert abs(terms[0] - math.fsum(original)) < 1e-12
            cases += 1
    for count in (0, 1, 2, 255, 256, 257, 1027):
        for blocks in (1, 2, 3, 17):
            owners = []
            for block in range(blocks):
                index = block
                while index < count:
                    owners.append(index)
                    if count - index <= blocks:
                        break
                    index += blocks
            assert sorted(owners) == list(range(count))
            flags = []
            for block in range(blocks):
                for thread in range(256):
                    index = block * 256 + thread
                    stride = blocks * 256
                    while index < count:
                        flags.append(index)
                        if count - index <= stride:
                            break
                        index += stride
            assert sorted(flags) == list(range(count))
    # Verify chunked incremental shared-histogram model (32-bit unsigned modular arithmetic).
    data = rng.randbytes(4096)
    for window, step, per_block in [(64, 16, 7), (128, 32, 13), (64, 64, 5), (32, 48, 4)]:
        count = 1 + (len(data) - window) // step
        chunks = (count + per_block - 1) // per_block
        got = [None] * count
        for chunk in range(chunks):
            first = chunk * per_block
            last = min(count, first + per_block)
            hist = [0] * 256
            for b in data[first * step:first * step + window]:
                hist[b] = (hist[b] + 1) & 0xFFFFFFFF
            got[first] = tuple(hist)
            for i in range(first + 1, last):
                old_start = (i - 1) * step
                if step < window:
                    # Simulate arbitrary interleaving of atomicSub and atomicAdd mod 2^32.
                    ops = [(data[old_start + j], -1) for j in range(step)] + \
                          [(data[old_start + window + j], +1) for j in range(step)]
                    rng.shuffle(ops)
                    for b, delta in ops:
                        hist[b] = (hist[b] + delta) & 0xFFFFFFFF
                else:
                    hist = [0] * 256
                    for b in data[i * step:i * step + window]:
                        hist[b] = (hist[b] + 1) & 0xFFFFFFFF
                got[i] = tuple(hist)
        for i in range(count):
            expected = [0] * 256
            for b in data[i * step:i * step + window]:
                expected[b] += 1
            assert list(got[i]) == expected
    print(f'PASS: {cases} host reduction models + incremental chunking + grid-stride coverage.')


if __name__ == '__main__':
    main()
