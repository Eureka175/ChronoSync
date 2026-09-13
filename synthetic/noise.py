"""Additive noise helpers."""

from __future__ import annotations

import numpy as np


def gaussian_noise(
    n: int, sigma: float = 1.0, seed: int = 0, dtype=np.float32
) -> np.ndarray:
    """White Gaussian noise with standard deviation ``sigma``."""
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) * float(sigma)).astype(dtype)


def additive_gaussian(
    x: np.ndarray, snr_db: float, seed: int = 0, dtype=np.float32
) -> np.ndarray:
    """Add white Gaussian noise at ``snr_db`` relative to the RMS of ``x``.

    ``snr_db = 20 * log10(rms(x) / sigma_noise)``.
    """
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=np.float64)
    rms = float(np.sqrt(np.mean(x * x)))
    if rms <= 0.0:
        return x.astype(dtype)
    sigma = rms * 10.0 ** (-float(snr_db) / 20.0)
    return (x + rng.standard_normal(x.shape) * sigma).astype(dtype)
