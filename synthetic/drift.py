"""Synthetic clock drift, piecewise drift and discontinuities.

Convention (consistent with ADR-003): ``ppm > 0`` means the TARGET clock
runs faster. An event at global time ``tau`` is stamped at sample
``n_t = tau * sr * (1 + ppm*1e-6)`` in the target, so the target waveform is
the reference resampled by the factor ``(1 + ppm*1e-6)`` and the local offset
grows as ``d(n) = ppm*1e-6 * n`` (events appear progressively later in the
target).
"""

from __future__ import annotations

import numpy as np

from chronosync.io.resampler import resample_ratio


def drift_ppm(
    x: np.ndarray,
    ppm: float,
    sample_rate: int = 48_000,
    quality: str = "HQ",
    dtype=np.float32,
) -> np.ndarray:
    """Time-stretch ``x`` by ``(1 + ppm*1e-6)`` via high-quality resampling.

    For ``ppm > 0`` the output is longer (target clock ticks faster) and the
    local offset grows as ``d(n) = ppm*1e-6 * n``.
    """
    ratio = 1.0 + float(ppm) * 1e-6
    return resample_ratio(x, ratio, quality=quality).astype(dtype)


def piecewise_drift(
    x: np.ndarray,
    segments: list[tuple[float, float, float]],
    sample_rate: int = 48_000,
    fade_s: float = 0.005,
    dtype=np.float32,
) -> np.ndarray:
    """Piecewise drift: ``segments`` is a list of ``(start_s, end_s, ppm)``.

    Each segment keeps its NATURAL drifted length (a device whose clock runs
    ``ppm`` fast records ``(end_s - start_s) * (1 + ppm*1e-6)`` seconds of
    samples for that content span), joints get a tiny linear crossfade to
    avoid clicks.
    """
    sr = sample_rate
    parts = []
    for start_s, end_s, ppm in segments:
        seg = x[int(start_s * sr) : int(end_s * sr)].astype(np.float64)
        drifted = drift_ppm(seg, ppm, sample_rate, dtype=np.float64)
        parts.append(drifted)

    out = parts[0].astype(np.float64)
    fade = int(fade_s * sr)
    for nxt in parts[1:]:
        nxt = nxt.astype(np.float64)
        if fade > 0 and out.size > fade and nxt.size > fade:
            w = np.linspace(0.0, 1.0, fade)
            out = np.concatenate(
                [out[:-fade], out[-fade:] * (1.0 - w) + nxt[:fade] * w, nxt[fade:]]
            )
        else:
            out = np.concatenate([out, nxt])
    return out.astype(dtype)


def drop_samples(
    x: np.ndarray, start: int, n: int, dtype=np.float32
) -> np.ndarray:
    """Remove ``n`` samples at ``start`` (simulates a lost buffer).

    The output is ``n`` samples shorter; the joint is left as a hard cut
    (real dropouts click). Phase-4 detection tests rely on this.
    """
    x = np.asarray(x, dtype=np.float64)
    return np.concatenate([x[:start], x[start + n :]]).astype(dtype)


def insert_samples(
    x: np.ndarray, start: int, n: int, value: float = 0.0, dtype=np.float32
) -> np.ndarray:
    """Insert ``n`` samples (zeros by default) at ``start``.

    The output is ``n`` samples longer (simulates a duplicated/garbled
    buffer).
    """
    x = np.asarray(x, dtype=np.float64)
    return np.concatenate(
        [x[:start], np.full(n, float(value), dtype=np.float64), x[start:]]
    ).astype(dtype)
