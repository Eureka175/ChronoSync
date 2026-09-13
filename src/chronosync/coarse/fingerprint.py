"""Fingerprint coarse matching (Layer 2).

Constellation fingerprints are matched by offset-vote histogram; the winning
offset follows ADR-003 (``d = t_target - t_reference``).
"""

from __future__ import annotations

from dataclasses import dataclass

from chronosync.features import (
    Fingerprint,
    FingerprintConfig,
    compute_fingerprint,
    match_fingerprints,
)
from chronosync.models.match import MatchResult

from .metadata import overlap_estimate


@dataclass
class FingerprintMatchConfig:
    """Fingerprint-stage thresholds (all configurable, documented)."""

    min_confidence: float = 0.5
    min_votes: int = 5
    max_lag_seconds: float | None = None
    chunk_seconds: float | None = 300.0
    fingerprint: FingerprintConfig | None = None


def fingerprint_match(
    fp_a: Fingerprint,
    fp_b: Fingerprint,
    ref_duration_s: float,
    tgt_duration_s: float,
    config: FingerprintMatchConfig | None = None,
) -> MatchResult:
    """Match two precomputed fingerprints (feature-level stage)."""
    cfg = config if config is not None else FingerprintMatchConfig()
    m = match_fingerprints(fp_a, fp_b, max_lag_seconds=cfg.max_lag_seconds)
    matched = bool(
        m.success and m.votes >= cfg.min_votes and m.confidence >= cfg.min_confidence
    )
    evidence = {
        "fingerprint_votes": float(m.votes),
        "fingerprint_matching_hashes": float(m.matching_hashes),
        "fingerprint_second_votes": float(m.second_votes),
        "fingerprint_confidence": m.confidence,
    }
    warnings: list[str] = []
    if not matched and m.matching_hashes > 0:
        warnings.append(
            f"fingerprint votes {m.votes} below threshold "
            f"(min_votes={cfg.min_votes}, min_confidence={cfg.min_confidence})"
        )
    return MatchResult(
        matched=matched,
        offset_samples=m.offset_samples if m.success else None,
        offset_seconds=m.offset_seconds if m.success else None,
        confidence=m.confidence,
        method="fingerprint",
        overlap_estimate=(
            overlap_estimate(ref_duration_s, tgt_duration_s, m.offset_seconds)
            if m.success
            else None
        ),
        evidence=evidence,
        warnings=warnings,
    )


def fingerprint_from_audio(
    x, sample_rate: float, config: FingerprintMatchConfig | None = None
) -> Fingerprint:
    cfg = config if config is not None else FingerprintMatchConfig()
    return compute_fingerprint(
        x,
        sample_rate,
        cfg.fingerprint,
        chunk_seconds=cfg.chunk_seconds,
    )
