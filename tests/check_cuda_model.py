#!/usr/bin/env python3
"""Host model of CUDA reduction and grid-stride indexing, not a GPU test."""
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
    print(f'PASS: {cases} host reduction models; grid-stride unique coverage. NOT GPU validation.')


if __name__ == '__main__':
    main()
