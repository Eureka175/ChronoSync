"""Coarse-matching cascade (Layer 2).

Order (short-circuit): metadata (prior only) -> fingerprint -> envelope
correlation -> transient/event matching -> No Match.

Every stage returns a :class:`~chronosync.models.match.MatchResult`; the
cascade stops at the first stage whose confidence reaches
``accept_confidence``. All evidence from earlier stages is preserved in the
returned result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from chronosync.features import (
    EnvelopeConfig,
    Fingerprint,
    FingerprintConfig,
    SpectralConfig,
    compute_fingerprint,
    envelope,
    envelope_rate,
    transient_map,
)
from chronosync.io import iter_chunks, probe
from chronosync.models.audio import CANONICAL_SAMPLE_RATE, AudioTrack
from chronosync.models.match import MatchResult

from .envelope import EnvelopeMatchConfig, envelope_match
from .fingerprint import FingerprintMatchConfig, fingerprint_match
from .metadata import metadata_match
from .transient import TransientMatchConfig, transient_match


@dataclass
class CoarseConfig:
    """Cascade configuration (all thresholds configurable, documented)."""

    methods: tuple[str, ...] = ("metadata", "fingerprint", "envelope", "transient")
    accept_confidence: float = 0.5
    max_lag_seconds: float | None = None
    prior_margin_seconds: float = 120.0  # search window around the metadata prior
    fingerprint: FingerprintMatchConfig = field(default_factory=FingerprintMatchConfig)
    envelope: EnvelopeMatchConfig = field(default_factory=EnvelopeMatchConfig)
    transient: TransientMatchConfig = field(default_factory=TransientMatchConfig)
    chunk_seconds: float = 30.0  # chunk size for streamed feature extraction


# ------------------------------------------------------------------ cascade


def cascade(
    metadata: MatchResult | None,
    fingerprint_pair: tuple[Fingerprint, Fingerprint] | None,
    envelope_pair: tuple[np.ndarray, np.ndarray, float] | None,  # (env_a, env_b, rate)
    transient_pair: tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]] | None,
    ref_duration_s: float,
    tgt_duration_s: float,
    config: CoarseConfig | None = None,
) -> MatchResult:
    """Short-circuit cascade over precomputed features (feature-level)."""
    cfg = config if config is not None else CoarseConfig()

    prior_samples: float | None = None
    if metadata is not None:
        prior_samples = metadata.offset_samples  # may be None

    # Effective lag window: explicit max_lag wins, else prior +- margin.
    max_lag = cfg.max_lag_seconds
    if max_lag is None and prior_samples is not None:
        max_lag = abs(prior_samples) / CANONICAL_SAMPLE_RATE + cfg.prior_margin_seconds

    evidence: dict[str, float] = {}
    warnings: list[str] = []
    if metadata is not None:
        evidence.update(metadata.evidence)
        warnings.extend(metadata.warnings)

    best_confidence = 0.0
    best: MatchResult | None = None

    for method in cfg.methods:
        result: MatchResult | None = None
        if method == "metadata":
            result = metadata  # never matched; prior-only
        elif method == "fingerprint" and fingerprint_pair is not None:
            fp_cfg = cfg.fingerprint
            fp_cfg = FingerprintMatchConfig(
                min_confidence=fp_cfg.min_confidence,
                min_votes=fp_cfg.min_votes,
                max_lag_seconds=fp_cfg.max_lag_seconds or max_lag,
                chunk_seconds=fp_cfg.chunk_seconds,
                fingerprint=fp_cfg.fingerprint,
            )
            result = fingerprint_match(
                fingerprint_pair[0], fingerprint_pair[1],
                ref_duration_s, tgt_duration_s, fp_cfg,
            )
        elif method == "envelope" and envelope_pair is not None:
            env_a, env_b, env_rate = envelope_pair
            env_cfg = cfg.envelope
            env_cfg = EnvelopeMatchConfig(
                target_rate=env_cfg.target_rate,
                min_corr=env_cfg.min_corr,
                min_confidence=env_cfg.min_confidence,
                max_lag_seconds=env_cfg.max_lag_seconds or max_lag,
                envelope=env_cfg.envelope,
            )
            result = envelope_match(
                env_a, env_b, env_rate, ref_duration_s, tgt_duration_s, env_cfg
            )
        elif method == "transient" and transient_pair is not None:
            (ta, sa), (tb, sb) = transient_pair
            tr_cfg = cfg.transient
            tr_cfg = TransientMatchConfig(
                min_transients=tr_cfg.min_transients,
                min_votes=tr_cfg.min_votes,
                min_confidence=tr_cfg.min_confidence,
                max_lag_seconds=tr_cfg.max_lag_seconds or max_lag,
                exclusion_seconds=tr_cfg.exclusion_seconds,
            )
            result = transient_match(
                ta, sa, tb, sb, ref_duration_s, tgt_duration_s, tr_cfg
            )

        if result is None:
            continue
        if result.matched and result.confidence >= cfg.accept_confidence:
            result.evidence.update(evidence)
            result.warnings = [*warnings, *result.warnings]
            return result
        if result.confidence > best_confidence:
            best_confidence = result.confidence
            best = result
        evidence.update(result.evidence)
        warnings.extend(result.warnings)

    if best is not None:
        best.evidence.update(evidence)
        best.warnings = [*warnings, *best.warnings]
        if best.matched and best.confidence < cfg.accept_confidence:
            # Cascade contract: a matched result below the accept threshold
            # is reported as unmatched (the stage-level evidence is kept).
            best.matched = False
            best.offset_samples = None
            best.offset_seconds = None
            best.warnings.append(
                f"best stage ({best.method}) confidence {best.confidence:.2f} "
                f"below accept threshold {cfg.accept_confidence}"
            )
        return best
    return MatchResult(
        matched=False,
        offset_samples=None,
        offset_seconds=None,
        confidence=0.0,
        method="none",
        evidence=evidence,
        warnings=[*warnings, "no coarse method matched"],
    )


# ------------------------------------------------------- in-RAM front end


def coarse_match(
    reference: np.ndarray,
    target: np.ndarray,
    sample_rate: float = CANONICAL_SAMPLE_RATE,
    config: CoarseConfig | None = None,
) -> MatchResult:
    """Coarse-match two in-RAM mono signals (canonical rate expected)."""
    cfg = config if config is not None else CoarseConfig()
    ref_dur = len(reference) / sample_rate
    tgt_dur = len(target) / sample_rate

    fp_pair = (
        compute_fingerprint(reference, sample_rate, cfg.fingerprint.fingerprint,
                            chunk_seconds=cfg.fingerprint.chunk_seconds),
        compute_fingerprint(target, sample_rate, cfg.fingerprint.fingerprint,
                            chunk_seconds=cfg.fingerprint.chunk_seconds),
    )
    env_pair = (
        envelope(reference, cfg.envelope.envelope),
        envelope(target, cfg.envelope.envelope),
        envelope_rate(sample_rate, cfg.envelope.envelope),
    )
    ta, sa = transient_map(reference, sample_rate)
    tb, sb = transient_map(target, sample_rate)
    return cascade(
        None, fp_pair, env_pair, ((ta, sa), (tb, sb)),
        ref_dur, tgt_dur, cfg,
    )


# ------------------------------------------------------- file front end


def coarse_match_paths(
    reference_path: str | Path,
    target_path: str | Path,
    config: CoarseConfig | None = None,
    cache_dir: str | Path | None = None,
) -> MatchResult:
    """Coarse-match two audio files with streamed feature extraction.

    Features are computed chunk-wise (no full decode into RAM); the metadata
    stage supplies the mtime prior and narrows the search window. When
    ``cache_dir`` is given, fingerprints and envelopes are cached per
    (path, size, mtime, algo/feat version) per ADR-006.
    """
    from chronosync.cache import ArrayStore, FeatureCacheDB, stat_source
    from chronosync.features import (
        ENVELOPE_ALGO_VERSION,
        ENVELOPE_FEAT_VERSION,
        FINGERPRINT_ALGO_VERSION,
        FINGERPRINT_FEAT_VERSION,
    )

    cfg = config if config is not None else CoarseConfig()
    ref_track: AudioTrack = probe(reference_path)
    tgt_track: AudioTrack = probe(target_path)
    meta = metadata_match(ref_track, tgt_track, CANONICAL_SAMPLE_RATE)

    cache_db = None
    if cache_dir is not None:
        cache_db = FeatureCacheDB(
            Path(cache_dir) / "features.sqlite3", ArrayStore(Path(cache_dir) / "arrays")
        )
    try:
        fp_cfg = cfg.fingerprint.fingerprint or FingerprintConfig()

        def _fingerprint(path: str) -> Fingerprint:
            if cache_db is not None:
                info = stat_source(path)
                cached = cache_db.get(
                    info, "fingerprint", FINGERPRINT_ALGO_VERSION, FINGERPRINT_FEAT_VERSION
                )
                if cached is not None:
                    return Fingerprint(
                        cached, fp_cfg.sample_rate, fp_cfg.hop_size, fp_cfg
                    )
            fp = _stream_fingerprint(path, probe(path), cfg)
            if cache_db is not None:
                cache_db.put(
                    stat_source(path), "fingerprint",
                    FINGERPRINT_ALGO_VERSION, FINGERPRINT_FEAT_VERSION, fp.hashes,
                )
            return fp

        def _envelope(path: str) -> np.ndarray:
            if cache_db is not None:
                info = stat_source(path)
                cached = cache_db.get(
                    info, "envelope", ENVELOPE_ALGO_VERSION, ENVELOPE_FEAT_VERSION
                )
                if cached is not None:
                    return cached
            parts = [
                envelope(chunk.data, cfg.envelope.envelope or EnvelopeConfig())
                for chunk in iter_chunks(path, chunk_seconds=cfg.chunk_seconds)
            ]
            env = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
            if cache_db is not None:
                cache_db.put(
                    stat_source(path), "envelope",
                    ENVELOPE_ALGO_VERSION, ENVELOPE_FEAT_VERSION, env,
                )
            return env

        fp_a = _fingerprint(str(reference_path))
        fp_b = _fingerprint(str(target_path))
        env_a = _envelope(str(reference_path))
        env_b = _envelope(str(target_path))
    finally:
        if cache_db is not None:
            cache_db.close()

    ta, sa = _stream_transients(str(reference_path), cfg)
    tb, sb = _stream_transients(str(target_path), cfg)

    return cascade(
        meta,
        (fp_a, fp_b),
        (env_a, env_b, envelope_rate(CANONICAL_SAMPLE_RATE, cfg.envelope.envelope)),
        ((ta, sa), (tb, sb)),
        ref_track.duration_seconds,
        tgt_track.duration_seconds,
        cfg,
    )


def _stream_fingerprint(
    path: str, track: AudioTrack, cfg: CoarseConfig
) -> Fingerprint:
    fp_cfg = cfg.fingerprint.fingerprint or FingerprintConfig()
    hashes: list[np.ndarray] = []
    for chunk in iter_chunks(path, chunk_seconds=cfg.chunk_seconds):
        hashes.append(
            compute_fingerprint(
                chunk.data, chunk.sample_rate, fp_cfg, chunk_seconds=None
            ).hashes
        )
    if not hashes:
        return Fingerprint(np.zeros((0, 2), dtype=np.int64), fp_cfg.sample_rate,
                           fp_cfg.hop_size, fp_cfg)
    return Fingerprint(np.concatenate(hashes), fp_cfg.sample_rate, fp_cfg.hop_size, fp_cfg)


def _stream_transients(
    path: str, cfg: CoarseConfig
) -> tuple[np.ndarray, np.ndarray]:
    spec_cfg = SpectralConfig()
    times: list[np.ndarray] = []
    strengths: list[np.ndarray] = []
    offset = 0.0
    for chunk in iter_chunks(path, chunk_seconds=cfg.chunk_seconds):
        t, s = transient_map(chunk.data, chunk.sample_rate, spec_cfg)
        times.append(t + offset)
        strengths.append(s)
        offset += chunk.data.size / chunk.sample_rate
    if not times:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)
    return (
        np.concatenate(times).astype(np.float32),
        np.concatenate(strengths).astype(np.float32),
    )
