"""Shared benchmark harness: wall time, CPU time and peak RSS.

Peak memory is sampled by a polling thread via ``psutil`` (Linux/Windows/
macOS). If psutil is missing, only wall/CPU times are reported.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:  # pragma: no cover - depends on the environment
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

_POLL_INTERVAL_S = 0.01


@dataclass
class BenchmarkResult:
    """One measured run."""

    name: str
    wall_seconds: float
    cpu_seconds: float
    peak_rss_mb: float | None
    extra: dict[str, Any] = field(default_factory=dict)


def timed(fn: Callable[[], Any], *, name: str) -> tuple[Any, BenchmarkResult]:
    """Run ``fn()``, sampling wall time, CPU time and peak RSS.

    Returns ``(fn_result, BenchmarkResult)``.
    """
    peak_mb = 0.0
    process = psutil.Process() if psutil is not None else None
    stop = threading.Event()

    def poll() -> None:
        nonlocal peak_mb
        while not stop.is_set():
            try:
                rss = process.memory_info().rss  # type: ignore[union-attr]
                peak_mb = max(peak_mb, rss / (1024.0 * 1024.0))
            except Exception:
                break
            time.sleep(_POLL_INTERVAL_S)

    thread = threading.Thread(target=poll, daemon=True)
    wall0 = time.perf_counter()
    cpu0 = time.process_time()
    thread.start()
    try:
        result = fn()
    finally:
        stop.set()
        thread.join()
    wall = time.perf_counter() - wall0
    cpu = time.process_time() - cpu0

    return result, BenchmarkResult(
        name=name,
        wall_seconds=wall,
        cpu_seconds=cpu,
        peak_rss_mb=(peak_mb if psutil is not None else None),
    )


def print_table(results: list[BenchmarkResult]) -> None:
    header = (
        f"{'case':<34} {'wall s':>9} {'cpu s':>9} {'peak RSS MB':>13}"
        f"  {'delay err (samples)':>21}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        rss = f"{r.peak_rss_mb:>13.1f}" if r.peak_rss_mb is not None else f"{'n/a':>13}"
        err = r.extra.get("delay_error_samples")
        err_s = f"{err:>21.3f}" if err is not None else f"{'n/a':>21}"
        print(f"{r.name:<34} {r.wall_seconds:>9.3f} {r.cpu_seconds:>9.3f} {rss}  {err_s}")


def to_dict(r: BenchmarkResult) -> dict[str, Any]:
    return {
        "name": r.name,
        "wall_seconds": round(r.wall_seconds, 4),
        "cpu_seconds": round(r.cpu_seconds, 4),
        "peak_rss_mb": (round(r.peak_rss_mb, 1) if r.peak_rss_mb is not None else None),
        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.extra.items()},
    }
