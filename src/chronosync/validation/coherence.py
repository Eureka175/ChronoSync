"""Coherence validation (Phase 7).

Magnitude-squared coherence (MSC) via Welch's averaged periodogram.
NOTE: low MSC is NOT equivalent to polarity inversion (see polarity.py).
"""

from __future__ import annotations

import numpy as np
from scipy import signal


def mean_coherence(
    x: np.ndarray,
    y: np.ndarray,
    sample_rate: float = 48_000,
    fmin: float = 80.0,
    fmax: float = 8_000.0,
    nperseg: int = 4_096,
) -> float:
    """Mean magnitude-squared coherence over ``[fmin, fmax]``.

    Returns 0.0 for empty/silent inputs (documented).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    common = min(x.size, y.size)
    if common < nperseg:
        return 0.0
    if not np.any(x[:common]) or not np.any(y[:common]):
        return 0.0
    freqs, cxy = signal.coherence(
        x[:common], y[:common], fs=sample_rate, nperseg=nperseg,
        noverlap=nperseg // 2,
    )
    band = (freqs >= fmin) & (freqs <= fmax)
    if not np.any(band):
        return 0.0
    return float(np.mean(cxy[band]))
