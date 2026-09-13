"""Echo taps and synthetic reverb for test scenarios.

The reverb is a textbook Schroeder-style network (parallel feed-forward/back
combs + two series all-passes). It is *test-grade synthetic coloration*, not
an acoustic room simulator — do not use it to benchmark production reverb
robustness.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

from .delay import delay_samples


def add_echo(x: np.ndarray, taps: list[tuple[int, float]], dtype=np.float32) -> np.ndarray:
    """Add echo taps: ``taps`` is a list of ``(delay_samples, linear_gain)``."""
    y = np.asarray(x, dtype=np.float64)
    for delay, gain in taps:
        y = y + float(gain) * delay_samples(x, delay, dtype=np.float64)
    return y.astype(dtype)


def schroeder_reverb(
    x: np.ndarray,
    rt60_s: float = 1.0,
    sample_rate: int = 48_000,
    wet: float = 0.3,
    dtype=np.float32,
) -> np.ndarray:
    """Synthetic reverb: 4 parallel combs + 2 series all-passes (Schroeder)."""
    x = np.asarray(x, dtype=np.float64)
    comb_delays = (1557, 1617, 1491, 1422)
    gains = [10.0 ** (-3.0 * d / (sample_rate * rt60_s)) for d in comb_delays]

    wet_sig = np.zeros_like(x)
    for d, g in zip(comb_delays, gains):
        b = np.zeros(d + 1)
        b[0] = 1.0
        b[d] = g
        a = np.zeros(d + 1)
        a[0] = 1.0
        a[d] = -g
        wet_sig += lfilter(b, a, x)
    wet_sig /= len(comb_delays)

    for d, g in ((225, 0.5), (556, 0.5)):
        b = np.zeros(d + 1)
        b[0] = -g
        b[d] = 1.0
        a = np.zeros(d + 1)
        a[0] = 1.0
        a[d] = -g
        wet_sig = lfilter(b, a, wet_sig)

    return (x + float(wet) * wet_sig).astype(dtype)
