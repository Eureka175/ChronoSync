"""Transient/event coarse matching (Layer 2).

Transient times from the two signals are paired in an offset-vote histogram
(1-D analogue of constellation matching). Robust for click/percussion-heavy
material. Offset sign: ADR-003 (``offset = t_target - t_reference``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from chronosync.models.match import MatchResult

from .metadata import overlap_estimate


@dataclass
class TransientMatchConfig:
    """Transient-stage parameters (all configurable, documented)."""

    min_transients: int = 3  # per side
    min_votes: int = 3
    min_confidence: float = 0.5
    max_lag_seconds: float | None = None
    exclusion_seconds: float = 0.2  # neighborhood around the best bin


def transient_match(
    times_a: np.ndarray,
    strengths_a: np.ndarray,
    times_b: np.ndarray,
    strengths_b: np.ndarray,
    ref_duration_s: float,
    tgt_duration_s: float,
    config: TransientMatchConfig | None = None,
) -> MatchResult:
    """Match two precomputed transient maps (feature-level stage)."""
    cfg = config if config is not None else TransientMatchConfig()
    if times_a.size < cfg.min_transients or times_b.size < cfg.min_transients:
        return MatchResult(
            matched=False,
            offset_samples=None,
            offset_seconds=None,
            confidence=0.0,
            method="transient",
            evidence={
                "transients_reference": float(times_a.size),
                "transients_target": float(times_b.size),
            },
            warnings=["not enough transients for event matching"],
        )

    # All pairwise offsets within the lag window, weighted by strength product.
    offsets = (times_b[:, None] - times_a[None, :]).ravel()
    weights = (strengths_b[:, None] * strengths_a[None, :]).ravel()
    if cfg.max_lag_seconds is not None:
        keep = np.abs(offsets) <= cfg.max_lag_seconds
        offsets, weights = offsets[keep], weights[keep]
    if offsets.size == 0:
        return MatchResult(
            matched=False, offset_samples=None, offset_seconds=None,
            confidence=0.0, method="transient",
            evidence={"transients_reference": float(times_a.size),
                      "transients_target": float(times_b.size)},
            warnings=["empty offset window"],
        )

    # Histogram with 10 ms bins (fixed; documented).
    bin_s = 0.01
    lo, hi = float(offsets.min()), float(offsets.max())
    n_bins = max(1, int(np.ceil((hi - lo) / bin_s)) + 1)
    hist = np.zeros(n_bins)
    rel = np.floor((offsets - lo) / bin_s).astype(np.int64)
    np.add.at(hist, rel, weights)

    best = int(np.argmax(hist))
    votes = float(hist[best])
    exclusion = max(1, int(cfg.exclusion_seconds / bin_s))
    masked = hist.copy()
    masked[max(0, best - exclusion) : best + exclusion + 1] = 0.0
    second = float(masked.max()) if masked.size else 0.0

    offset_seconds = lo + (best + 0.5) * bin_s
    ratio = votes / max(second, 1e-12)
    ratio_score = (ratio - 1.0) / (ratio - 1.0 + 0.5) if ratio >= 1.0 else 0.0
    share = votes / max(float(np.sum(hist)), 1e-12)
    confidence = float(np.clip(0.5 * ratio_score + 0.5 * min(share * 4.0, 1.0), 0.0, 1.0))
    matched = bool(votes >= cfg.min_votes and confidence >= cfg.min_confidence)

    return MatchResult(
        matched=matched,
        offset_samples=offset_seconds * 48_000.0,
        offset_seconds=offset_seconds,
        confidence=confidence,
        method="transient",
        overlap_estimate=overlap_estimate(ref_duration_s, tgt_duration_s, offset_seconds),
        evidence={
            "transient_votes": votes,
            "transient_second": second,
            "transients_reference": float(times_a.size),
            "transients_target": float(times_b.size),
        },
        warnings=(
            []
            if matched
            else [
                f"transient votes {votes:.1f} (min_votes {cfg.min_votes}) or "
                f"confidence {confidence:.2f} below threshold"
            ]
        ),
    )
