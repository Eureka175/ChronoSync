"""Audio data models and canonical-format constants.

Canonical internal DSP format (ADR-002):

* sample rate = 48000 Hz
* dtype       = float32
* analysis on a quality-weighted mono downmix; per-channel arrays
  (left / right) are retained and never permanently discarded.

All sample counts in this module refer to the canonical sample rate unless
stated otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

CANONICAL_SAMPLE_RATE: int = 48_000
CANONICAL_DTYPE = np.float32


@dataclass(frozen=True)
class AudioTrack:
    """Static metadata of one recorded track (no audio data)."""

    name: str
    path: str | None
    sample_rate: int  # Hz; sample rate of the source file
    channels: int  # channel count in the source file
    frames: int  # total frames in the source file
    duration_seconds: float  # frames / sample_rate
    format: str  # container / format name, e.g. "WAV", "FLAC"
    subtype: str  # sample encoding, e.g. "PCM_16", "PCM_24", "FLOAT"


@dataclass
class DecodedAudio:
    """Decoded audio in canonical float32 form (ADR-002).

    ``data`` has shape ``(channels, n_samples)`` at the canonical sample rate.
    ``mono_mix`` is the quality-weighted downmix used by default for analysis:
    channels with persistent clipping are down-weighted instead of being
    dropped (ADR-002).
    """

    data: np.ndarray  # (channels, n_samples) float32, canonical sample rate
    sample_rate: int  # always CANONICAL_SAMPLE_RATE
    channel_names: tuple[str, ...]  # e.g. ("L", "R") or ("Mono",)
    mono_mix: np.ndarray  # (n_samples,) float32, quality-weighted downmix
    clip_fraction: tuple[float, ...]  # per-channel fraction of near-full-scale samples
    source_sample_rate: int  # sample rate of the source file before resampling
    warnings: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        return float(self.mono_mix.size) / self.sample_rate
