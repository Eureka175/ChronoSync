"""GCC-PHAT benchmark.

Usage::

    python benchmarks/benchmark_gcc.py            # 10 s and 60 s cases
    python benchmarks/benchmark_gcc.py --long     # + 10 min / 1 h (windowed)
    python benchmarks/benchmark_gcc.py --json

Full-file single-shot GCC is O(N log N) with several complex128 FFT buffers
(~16 bytes/sample each), so beyond a few minutes it is intentionally
replaced by *windowed* GCC — the mode the drift estimator will use. The
10 min / 1 h rows therefore report windowed throughput (windows per second),
not single-shot latency, and have no delay-error column.

Every case reports wall time, CPU time and peak RSS so accuracy / runtime /
memory can be compared after each core-algorithm change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.common import BenchmarkResult, print_table, timed, to_dict  # noqa: E402
from chronosync.fine.gcc_phat import gcc_phat  # noqa: E402
from synthetic.delay import delay_samples  # noqa: E402
from synthetic.drift import drift_ppm  # noqa: E402
from synthetic.generators import white_noise  # noqa: E402

SR = 48_000
WINDOW = 65_536  # windowed-mode GCC window (samples)
DELAY = 12_345
PPM = 100.0  # realistic mild drift for the windowed (drift-estimator) cases


def _pair(duration_s: float, ppm: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    n = int(duration_s * SR)
    ref = white_noise(n, seed=0)
    tgt = delay_samples(ref, DELAY)
    if ppm:
        tgt = drift_ppm(tgt, ppm)
    return ref, tgt


def _full_file_case(duration_s: float) -> BenchmarkResult:
    # Pure integer delay (no drift): the reported error is the pure
    # estimation error of GCC-PHAT + sub-sample refinement.
    ref, tgt = _pair(duration_s)
    result, bm = timed(
        lambda: gcc_phat(ref, tgt, SR), name=f"full-file GCC {duration_s:g} s"
    )
    bm.extra = {
        "mode": "full-file",
        "duration_s": duration_s,
        "nfft": next_fast_len_display(len(ref) + len(tgt) - 1),
        "delay_error_samples": abs(result.delay_samples - DELAY),
    }
    return bm


def next_fast_len_display(n: int) -> int:
    from scipy import fft

    return int(fft.next_fast_len(n, real=True))


def _windowed_case(duration_s: float) -> BenchmarkResult:
    """Windowed GCC throughput over a drifted pair (drift-estimator mode)."""
    n = int(duration_s * SR)
    ref = white_noise(n, seed=0)
    tgt = drift_ppm(delay_samples(ref, 500), ppm=PPM)
    stride = WINDOW // 2
    starts = list(range(0, min(len(ref), len(tgt)) - WINDOW, stride))
    n_windows = len(starts)

    def run_windows() -> None:
        for s in starts:
            gcc_phat(ref[s : s + WINDOW], tgt[s : s + WINDOW], SR)

    _, bm = timed(run_windows, name=f"windowed GCC {duration_s:g} s")
    bm.extra = {
        "mode": "windowed",
        "duration_s": duration_s,
        "window_samples": WINDOW,
        "windows": n_windows,
        "windows_per_second": n_windows / bm.wall_seconds,
    }
    return bm


def run(long: bool = False) -> list[BenchmarkResult]:
    cases: list[BenchmarkResult] = [
        _full_file_case(10.0),
        _full_file_case(60.0),
    ]
    if long:
        cases.append(_windowed_case(600.0))
        cases.append(_windowed_case(3_600.0))
    return cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--long", action="store_true", help="add 10 min / 1 h windowed cases"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    results = run(long=args.long)
    if args.json:
        print(json.dumps([to_dict(r) for r in results], indent=2))
    else:
        print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
