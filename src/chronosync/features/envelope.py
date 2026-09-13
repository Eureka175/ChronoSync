"""Energy envelope extraction (Layer 1).

RMS energy per frame. Block-wise vectorized computation so that multi-hour
signals never materialize a ``(n_frames, frame_samples)`` index matrix at once.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: Max frames per vectorized block (~32 MB of index matrix).
_BLOCK_FRAMES = 4096


@dataclass
class EnvelopeConfig:
    """Envelope extraction parameters (all configurable, documented)."""

    frame_samples: int = 1024  # ~21 ms @ 48 kHz
    hop_samples: int = 512  # 50% overlap


def envelope(x: np.ndarray, config: EnvelopeConfig | None = None) -> np.ndarray:
    """RMS energy envelope, one value per frame (float32).

    ``len(result) = 1 + (n - frame) // hop`` for ``n >= frame``; shorter
    signals yield a single frame. Input is 1-D mono audio (any float dtype).
    """
    cfg = config if config is not None else EnvelopeConfig()
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return np.zeros(0, dtype=np.float32)
    if x.size < cfg.frame_samples:
        rms = float(np.sqrt(np.mean(x * x)))
        return np.array([rms], dtype=np.float32)

    n_frames = 1 + (x.size - cfg.frame_samples) // cfg.hop_samples
    out = np.empty(n_frames, dtype=np.float32)
    frame_idx = np.arange(cfg.frame_samples)
    for start_frame in range(0, n_frames, _BLOCK_FRAMES):
        stop_frame = min(start_frame + _BLOCK_FRAMES, n_frames)
        frames = np.arange(start_frame, stop_frame)
        starts = frames * cfg.hop_samples
        idx = starts[:, None] + frame_idx  # (nf, frame) — bounded block
        block = x[idx]
        out[start_frame:stop_frame] = np.sqrt(np.mean(block * block, axis=1))
    return out


def envelope_rate(sample_rate: float, config: EnvelopeConfig | None = None) -> float:
    """Envelope frames per second."""
    cfg = config if config is not None else EnvelopeConfig()
    return float(sample_rate) / cfg.hop_samples


def decimate_envelope(
    env: np.ndarray, env_rate: float, target_rate: float = 100.0
) -> tuple[np.ndarray, float]:
    """Block-mean decimation of an envelope to ``target_rate``.

    Coarse-layer internal only (the envelope is already a smoothed, decimated
    energy signal — this is NOT audio resampling and does not require a
    band-limited resampler; ADR-002 forbids np.interp for AUDIO only).
    Returns ``(decimated, actual_rate)``.
    """
    env = np.asarray(env, dtype=np.float64)
    if env.size == 0:
        return np.zeros(0, dtype=np.float32), float(target_rate)
    block = max(1, int(round(env_rate / target_rate)))
    n_out = env.size // block
    if n_out == 0:
        return np.array([float(np.mean(env))], dtype=np.float32), float(env_rate)
    trimmed = env[: n_out * block].reshape(n_out, block)
    return np.mean(trimmed, axis=1).astype(np.float32), env_rate / block
