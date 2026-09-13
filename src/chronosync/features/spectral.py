"""Spectral features: spectral flux and transient detection (Layer 1).

``spectral_flux`` is computed via ``scipy.signal.stft`` in bounded chunks so
long signals do not materialize a full time-frequency matrix.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

DEFAULT_CHUNK_SECONDS = 30.0


@dataclass
class SpectralConfig:
    """Spectral-feature parameters (all configurable, documented)."""

    frame_samples: int = 1024  # STFT window (~21 ms @ 48 kHz)
    hop_samples: int = 512  # 50% overlap
    window: str = "hann"
    flux_smooth_samples: int = 3  # moving-average half-width for flux smoothing
    min_flux: float = 0.05  # transient peak threshold (fraction of max flux)
    min_separation_seconds: float = 0.05  # min distance between transients


def _flux_of_chunk(x: np.ndarray, sr: float, cfg: SpectralConfig) -> np.ndarray:
    _, _, zxx = signal.stft(
        x,
        fs=sr,
        nperseg=cfg.frame_samples,
        noverlap=cfg.frame_samples - cfg.hop_samples,
        window=cfg.window,
        boundary=None,
        padded=False,
    )
    mag = np.abs(zxx)
    flux = np.clip(np.diff(mag, axis=1), 0.0, None).sum(axis=0)
    return flux.astype(np.float64)


def spectral_flux(
    x: np.ndarray,
    sample_rate: float,
    config: SpectralConfig | None = None,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
) -> np.ndarray:
    """Half-wave-rectified spectral flux, one value per frame boundary.

    ``flux[i]`` corresponds to time ``(i + 1) * hop / sr``. Normalized so the
    maximum is 1.0 (empty input yields an empty array).
    """
    cfg = config if config is not None else SpectralConfig()
    x = np.asarray(x, dtype=np.float64)
    if x.size < cfg.frame_samples or not np.any(x):
        return np.zeros(0, dtype=np.float32)

    chunk_len = int(chunk_seconds * sample_rate)
    # Align chunk boundaries to the STFT hop and overlap by two hops so the
    # chunked flux is EXACTLY the single-shot flux (the boundary frame is
    # computed by the earlier chunk; consecutive flux arrays never overlap).
    chunk_len = (chunk_len // cfg.hop_samples) * cfg.hop_samples
    if chunk_len < cfg.frame_samples:
        chunk_len = cfg.frame_samples
    overlap = 2 * cfg.hop_samples

    parts = []
    start = 0
    while start < x.size:
        end = min(start + chunk_len + overlap, x.size)
        parts.append(_flux_of_chunk(x[start:end], sample_rate, cfg))
        start = end - overlap
        if end >= x.size:
            break

    flux = np.concatenate(parts)
    if flux.size == 0:
        return np.zeros(0, dtype=np.float32)
    peak = float(np.max(flux))
    if peak > 0.0:
        flux = flux / peak
    return flux.astype(np.float32)


def transient_map(
    x: np.ndarray,
    sample_rate: float,
    config: SpectralConfig | None = None,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
) -> tuple[np.ndarray, np.ndarray]:
    """Detect transients from the spectral flux.

    Returns ``(times_seconds, strengths)`` (float32). Strengths are the
    smoothed flux values at the detected peaks, in [0, 1].
    """
    cfg = config if config is not None else SpectralConfig()
    flux = spectral_flux(x, sample_rate, cfg, chunk_seconds=chunk_seconds)
    if flux.size == 0:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)

    if cfg.flux_smooth_samples > 0:
        k = cfg.flux_smooth_samples
        kernel = np.ones(2 * k + 1) / (2 * k + 1)
        smoothed = np.convolve(flux, kernel, mode="same")
    else:
        smoothed = flux

    distance = max(1, int(cfg.min_separation_seconds * sample_rate / cfg.hop_samples))
    indices, props = signal.find_peaks(
        smoothed, height=cfg.min_flux, distance=distance
    )
    if indices.size == 0:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)
    times = (indices + 1).astype(np.float64) * cfg.hop_samples / sample_rate
    return times.astype(np.float32), smoothed[indices].astype(np.float32)
