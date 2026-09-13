"""Decode audio files into the canonical format (ADR-002).

* float32 output at the canonical sample rate (48000 Hz);
* stereo is kept as left/right *plus* a quality-weighted ``mono_mix`` —
  channels with persistent clipping are down-weighted, never dropped;
* long files can be streamed chunk-wise via :func:`iter_chunks`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

from chronosync.models.audio import CANONICAL_SAMPLE_RATE, DecodedAudio

from .resampler import resample

#: Fraction of full scale at/above which a float32 sample counts as clipped.
CLIP_THRESHOLD = 0.999


@dataclass
class AudioChunk:
    """One streamed mono chunk in canonical float32 format."""

    data: np.ndarray  # (n_samples,) float32 at the canonical sample rate
    start_sample: int  # canonical-rate sample index of the chunk start
    sample_rate: int  # always CANONICAL_SAMPLE_RATE


def _load_float32(path: str, frames: int | None = None) -> np.ndarray:
    import soundfile as sf

    with sf.SoundFile(path) as f:
        n = f.frames if frames is None else min(int(frames), f.frames)
        block = f.read(n, dtype="float32", always_2d=True)
    return np.ascontiguousarray(block.T, dtype=np.float32)  # (channels, n)


def _source_rate(path: str) -> int:
    import soundfile as sf

    return int(sf.info(path).samplerate)


def _clip_fractions(data: np.ndarray) -> tuple[float, ...]:
    if data.size == 0:
        return (0.0,) * data.shape[0]
    return tuple(
        float(np.mean(np.abs(channel) >= CLIP_THRESHOLD)) for channel in data
    )


def _channel_weights(clip_fractions: tuple[float, ...]) -> tuple[float, ...]:
    """Down-weight clipped channels (quadratic falloff, floored at 1e-3)."""
    return tuple(max(1.0 - c, 1e-3) ** 2 for c in clip_fractions)


def _channel_names(n_channels: int) -> tuple[str, ...]:
    if n_channels == 1:
        return ("Mono",)
    if n_channels == 2:
        return ("L", "R")
    return tuple(f"Ch{i + 1}" for i in range(n_channels))


def _mono_mix(data: np.ndarray, weights: tuple[float, ...]) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float32)[:, None]
    total = float(np.sum(weights))
    return (np.sum(data * w, axis=0) / total).astype(np.float32)


def read_canonical(
    path: str | Path,
    target_rate: int = CANONICAL_SAMPLE_RATE,
    max_seconds: float | None = None,
) -> DecodedAudio:
    """Decode a file into :class:`~chronosync.models.audio.DecodedAudio`.

    The whole file is loaded into RAM — suitable for short/medium files.
    For multi-hour recordings use :func:`iter_chunks`.
    """
    warnings: list[str] = []
    path = str(path)
    data = _load_float32(path)  # (channels, n) at the source rate
    src_rate = _source_rate(path)
    if max_seconds is not None:
        limit = int(max_seconds * src_rate)
        data = data[:, :limit]

    clip = _clip_fractions(data)
    if src_rate != target_rate:
        data = resample(data, src_rate, target_rate)
        warnings.append(f"resampled {src_rate} Hz -> {target_rate} Hz")

    weights = _channel_weights(clip)
    mono = _mono_mix(data, weights)
    return DecodedAudio(
        data=data,
        sample_rate=target_rate,
        channel_names=_channel_names(data.shape[0]),
        mono_mix=mono,
        clip_fraction=clip,
        source_sample_rate=src_rate,
        warnings=warnings,
    )


def iter_chunks(
    path: str | Path,
    chunk_seconds: float = 30.0,
    target_rate: int = CANONICAL_SAMPLE_RATE,
    margin_seconds: float = 0.5,
) -> Iterator[AudioChunk]:
    """Stream a file as canonical mono chunks (Layer 0 groundwork).

    Each chunk is resampled independently with a small overlap margin that is
    trimmed afterwards. NOTE (documented limitation, resolved by the drift
    layer in Phase 4): per-chunk resampling introduces small edge transients,
    so chunk boundaries are not yet stitched into one seamless stream.
    """
    import soundfile as sf

    path = str(path)
    info = sf.info(path)
    chunk_src = int(round(chunk_seconds * info.samplerate))
    margin_src = int(round(margin_seconds * info.samplerate))
    margin_out = int(round(margin_seconds * target_rate))
    pos = 0

    with sf.SoundFile(path) as f:
        while True:
            block = f.read(
                chunk_src + 2 * margin_src, dtype="float32", always_2d=True
            )
            if block.shape[0] == 0:
                break
            data = np.ascontiguousarray(block.T, dtype=np.float32)  # (ch, n)
            clip = _clip_fractions(data)
            if info.samplerate != target_rate:
                data = resample(data, info.samplerate, target_rate)
            mono = _mono_mix(data, _channel_weights(clip))
            if mono.size <= 2 * margin_out:
                yield AudioChunk(mono, pos, target_rate)
                break
            core = mono[margin_out : mono.size - margin_out]
            start_sample = int(round((pos + margin_src) / info.samplerate * target_rate))
            yield AudioChunk(
                data=core.astype(np.float32),
                start_sample=start_sample,
                sample_rate=target_rate,
            )
            pos += block.shape[0]
