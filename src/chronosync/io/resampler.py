"""High-quality sample-rate conversion (ADR-002).

Default engine: SoXR (polyphase, band-limited). If the ``soxr`` package is
not installed we fall back to ``scipy.signal.resample_poly`` (polyphase FIR
via FFT) and emit a warning: it is lower quality than SoXR.

``numpy.interp`` is explicitly FORBIDDEN as an audio resampling method
(ADR-002); it is linear interpolation, not a band-limited resampler.
"""

from __future__ import annotations

import warnings

import numpy as np


def resample(
    data: np.ndarray,
    src_rate: int | float,
    dst_rate: int | float,
    quality: str = "HQ",
) -> np.ndarray:
    """Resample ``data`` along its last axis from ``src_rate`` to ``dst_rate``.

    Args:
        data: array of shape ``(..., n_samples)``.
        src_rate: source sample rate in Hz.
        dst_rate: target sample rate in Hz.
        quality: SoXR quality ("QQ", "LQ", "MQ", "HQ", "VHQ"); ignored in the
            scipy fallback.

    Returns:
        float32 array with ``round(n * dst_rate / src_rate)`` samples.
    """
    if src_rate == dst_rate:
        return np.asarray(data, dtype=np.float32)

    try:
        import soxr
    except ImportError:  # pragma: no cover - exercised only without soxr
        warnings.warn(
            "soxr is not installed; falling back to scipy.signal.resample_poly "
            "(lower quality). Install `soxr` for high-quality resampling.",
            stacklevel=2,
        )
        from scipy.signal import resample_poly

        ratio = float(dst_rate) / float(src_rate)
        up, down = _best_rational(ratio)
        arr = np.asarray(data, dtype=np.float64)
        return resample_poly(arr, up, down, axis=-1).astype(np.float32)

    arr = np.asarray(data, dtype=np.float32)
    return soxr.resample(arr, float(src_rate), float(dst_rate), quality=quality).astype(
        np.float32
    )


def _best_rational(ratio: float, max_denominator: int = 100_000) -> tuple[int, int]:
    """Approximate ``ratio`` as up/down with a bounded denominator."""
    from fractions import Fraction

    frac = Fraction(ratio).limit_denominator(max_denominator)
    return frac.numerator, frac.denominator


def resample_ratio(data: np.ndarray, ratio: float, quality: str = "HQ") -> np.ndarray:
    """Resample by an arbitrary (possibly irrational) ``ratio`` via SoXR.

    Used by the synthetic drift generator; ``ratio = 1 + ppm * 1e-6``.
    """
    try:
        import soxr
    except ImportError:  # pragma: no cover - exercised only without soxr
        up, down = _best_rational(float(ratio))
        from scipy.signal import resample_poly

        arr = np.asarray(data, dtype=np.float64)
        return resample_poly(arr, up, down, axis=-1).astype(np.float32)
    arr = np.asarray(data, dtype=np.float32)
    return soxr.resample(
        arr, 1.0, float(ratio), quality=quality
    ).astype(np.float32)
