"""Drift-estimation benchmark.

Usage::

    python benchmarks/benchmark_drift.py [--json]

Cases: full drift estimation (windowed GCC -> regression -> TimeMap) on a
60 s white-noise pair (+150 ppm) and on a 60 s speech-like pair (+120 ppm,
exercising the adaptive window shrink), plus a TimeMap correction render.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.common import BenchmarkResult, print_table, timed, to_dict  # noqa: E402
from chronosync.drift import DriftConfig, correct_track, estimate_drift  # noqa: E402
from synthetic.delay import delay_samples  # noqa: E402
from synthetic.drift import drift_ppm  # noqa: E402
from synthetic.generators import speech_like, white_noise  # noqa: E402

SR = 48_000

FAST = DriftConfig(
    window_samples=8_192,
    min_window_samples=8_192,
    min_windows=4,
    min_windows_per_segment=3,
)


def run() -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []

    ref = white_noise(60 * SR, seed=0)
    tgt = drift_ppm(delay_samples(ref, 1_000), 150.0)
    est, bm = timed(
        lambda: estimate_drift(ref, tgt, SR, coarse_offset_samples=1_000, config=FAST),
        name="drift estimate 60 s white noise",
    )
    bm.extra = {
        "mode": "estimate",
        "alpha_error_ppm": abs(est.model.alpha_ppm - 150.0),
        "windows": len(est.measurements),
        "classification": est.classification,
    }
    results.append(bm)

    ref2 = speech_like(60 * SR, seed=1)
    tgt2 = drift_ppm(delay_samples(ref2, 5_000), 120.0)
    est2, bm = timed(
        lambda: estimate_drift(ref2, tgt2, SR, coarse_offset_samples=5_000),
        name="drift estimate 60 s speech-like (adaptive)",
    )
    bm.extra = {
        "mode": "estimate",
        "alpha_error_ppm": abs(est2.model.alpha_ppm - 120.0),
        "windows": len(est2.measurements),
        "classification": est2.classification,
    }
    results.append(bm)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        _, bm = timed(
            lambda: correct_track(tgt, est.time_map, SR),
            name="time-map correction render 60 s",
        )
    bm.extra = {"mode": "render", "output_samples": len(correct_track(tgt, est.time_map, SR))}
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
