"""Feature-extraction and coarse-matching benchmark.

Usage::

    python benchmarks/benchmark_features.py [--json]

Cases: envelope (60 s), spectral flux (60 s), constellation fingerprint
(60 s, chunked 30 s), fingerprint MATCH of a delayed 60 s pair. Reports
wall time, CPU time and peak RSS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.common import BenchmarkResult, print_table, timed, to_dict  # noqa: E402
from chronosync.features import (  # noqa: E402
    compute_fingerprint,
    envelope,
    match_fingerprints,
    spectral_flux,
)
from synthetic.delay import delay_samples  # noqa: E402
from synthetic.generators import speech_like  # noqa: E402

SR = 48_000


def run() -> list[BenchmarkResult]:
    n = 60 * SR
    x = speech_like(n, seed=0)
    y = delay_samples(x, 30_000)

    results: list[BenchmarkResult] = []

    _, bm = timed(lambda: envelope(x), name="envelope 60 s")
    bm.extra = {"mode": "feature", "frames": envelope(x).size}
    results.append(bm)

    _, bm = timed(lambda: spectral_flux(x, SR, chunk_seconds=30.0), name="spectral flux 60 s")
    bm.extra = {"mode": "feature", "frames": spectral_flux(x, SR, chunk_seconds=30.0).size}
    results.append(bm)

    _, bm = timed(
        lambda: compute_fingerprint(x, SR, chunk_seconds=30.0),
        name="fingerprint 60 s (chunked)",
    )
    bm.extra = {"mode": "feature", "hashes": compute_fingerprint(x, SR, chunk_seconds=30.0).hashes.shape[0]}
    results.append(bm)

    fp_a = compute_fingerprint(x, SR, chunk_seconds=30.0)
    fp_b = compute_fingerprint(y, SR, chunk_seconds=30.0)
    match, bm = timed(
        lambda: match_fingerprints(fp_a, fp_b, max_lag_seconds=120.0),
        name="fingerprint match 60 s pair",
    )
    bm.extra = {
        "mode": "match",
        "offset_error_samples": abs(match.offset_samples - 30_000),
        "votes": match.votes,
    }
    results.append(bm)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    results = run()
    if args.json:
        print(json.dumps([to_dict(r) for r in results], indent=2))
    else:
        print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
