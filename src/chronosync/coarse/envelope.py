"""Envelope-correlation coarse matching (Layer 2).

The decimated RMS envelopes of both signals are cross-correlated with the
normalized correlation coefficient as the quality measure. Well suited to
speech-like material (strong syllable dynamics). Offset sign: ADR-003.

Note on the sign: ``scipy.signal.correlate(ref, tgt)`` peaks at the NEGATIVE
of the ADR-003 offset (verified against GCC in the test suite), so the
conversion is ``offset = -lags[argmax]``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal

from chronosync.features import (
    EnvelopeConfig,
    decimate_envelope,
    envelope,
    envelope_rate,
)
from chronosync.models.audio import CANONICAL_SAMPLE_RATE
from chronosync.models.match import MatchResult

from .metadata import overlap_estimate


@dataclass
class EnvelopeMatchConfig:
    """Envelope-stage parameters (all configurable, documented)."""

    target_rate: float = 100.0  # decimated envelope rate used for correlation
    min_corr: float = 0.25  # absolute minimum normalized correlation
    min_confidence: float = 0.5
    max_lag_seconds: float | None = None
    envelope: EnvelopeConfig | None = None


def envelope_match(
    env_a: np.ndarray,
    env_b: np.ndarray,
    env_rate: float,
    ref_duration_s: float,
    tgt_duration_s: float,
    config: EnvelopeMatchConfig | None = None,
) -> MatchResult:
    """Match two precomputed envelopes (feature-level stage)."""
    cfg = config if config is not None else EnvelopeMatchConfig()
    if env_a.size == 0 or env_b.size == 0:
        return MatchResult(
            matched=False,
            offset_samples=None,
            offset_seconds=None,
            confidence=0.0,
            method="envelope",
            evidence={},
            warnings=["empty envelope"],
        )

    ea, rate = decimate_envelope(env_a, env_rate, cfg.target_rate)
    eb, _ = decimate_envelope(env_b, env_rate, cfg.target_rate)
    if ea.size < 4 or eb.size < 4:
        return MatchResult(
            matched=False,
            offset_samples=None,
            offset_seconds=None,
            confidence=0.0,
            method="envelope",
            evidence={},
            warnings=["envelope too short to correlate"],
        )

    a = ea - ea.mean()
    b = eb - eb.mean()
    denom = float(np.sqrt(np.sum(a * a) * np.sum(b * b)))
    if denom <= 0.0:
        return MatchResult(
            matched=False, offset_samples=None, offset_seconds=None,
            confidence=0.0, method="envelope", evidence={},
            warnings=["constant (zero-variance) envelope"],
        )

    corr = signal.correlate(a, b, method="fft")
    lags = signal.correlation_lags(ea.size, eb.size)  # lag in envelope samples
    if cfg.max_lag_seconds is not None:
        mask = np.abs(lags) <= cfg.max_lag_seconds * rate
        if not np.any(mask):
            return MatchResult(
                matched=False, offset_samples=None, offset_seconds=None,
                confidence=0.0, method="envelope", evidence={},
                warnings=["empty lag window after max_lag restriction"],
            )
        corr = corr[mask]
        lags = lags[mask]

    idx = int(np.argmax(corr))
    r = float(corr[idx]) / denom
    # sub-sample refinement (parabolic on the decimated envelope correlation)
    delta = 0.0
    if 1 <= idx <= corr.size - 2:
        y0, y1, y2 = float(corr[idx - 1]), float(corr[idx]), float(corr[idx + 1])
        dnom = y0 - 2.0 * y1 + y2
        if abs(dnom) > 1e-12:
            delta = float(np.clip(0.5 * (y0 - y2) / dnom, -0.5, 0.5))

    # scipy's correlate(ref, tgt) peaks at the NEGATIVE of the ADR-003 offset.
    offset_seconds = -(float(lags[idx]) + delta) / rate
    confidence = float(np.clip((r - cfg.min_corr) / (1.0 - cfg.min_corr), 0.0, 1.0))
    matched = bool(r >= cfg.min_corr and confidence >= cfg.min_confidence)

    return MatchResult(
        matched=matched,
        offset_samples=offset_seconds * CANONICAL_SAMPLE_RATE,
        offset_seconds=offset_seconds,
        confidence=confidence,
        method="envelope",
        overlap_estimate=overlap_estimate(ref_duration_s, tgt_duration_s, offset_seconds),
        evidence={"envelope_corr": r, "envelope_rate": rate},
        warnings=(
            []
            if matched
            else [f"envelope correlation {r:.3f} below min_corr {cfg.min_corr}"]
        ),
    )


def envelope_from_audio(
    x: np.ndarray, sample_rate: float, config: EnvelopeMatchConfig | None = None
) -> np.ndarray:
    cfg = config if config is not None else EnvelopeMatchConfig()
    return envelope(x, cfg.envelope)


def envelope_signal_rate(sample_rate: float, config: EnvelopeMatchConfig | None = None) -> float:
    cfg = config if config is not None else EnvelopeMatchConfig()
    return envelope_rate(sample_rate, cfg.envelope)
