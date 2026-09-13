"""Unit tests for the validation layer (Phase 7)."""

from __future__ import annotations

import numpy as np
import pytest

from chronosync.drift import DriftConfig, estimate_drift
from chronosync.models.match import MatchResult
from chronosync.models.timemap import ConstantOffsetTimeMap, LinearTimeMap
from chronosync.validation import (
    ValidationReport,
    mean_coherence,
    polarity_check,
    residual_offsets,
    validate_pair,
)
from synthetic.delay import delay_samples
from synthetic.drift import drift_ppm
from synthetic.generators import speech_like, white_noise

SR = 48_000

FAST = DriftConfig(
    window_samples=8_192, min_window_samples=8_192,
    min_windows=4, min_windows_per_segment=3,
)


# ---------------------------------------------------------------- residual


def test_residual_near_zero_for_correct_map():
    ref = white_noise(20 * SR, seed=0)
    tgt = drift_ppm(delay_samples(ref, 2_000), 150.0)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=2_000, config=FAST)
    res = residual_offsets(ref, tgt, est.time_map, SR)
    assert res.max_abs_samples < 2.0


def test_residual_reports_large_error_for_wrong_map():
    ref = white_noise(20 * SR, seed=1)
    tgt = delay_samples(ref, 2_000)
    # wrong map: claims zero offset
    res = residual_offsets(ref, tgt, ConstantOffsetTimeMap(0.0), SR)
    assert res.max_abs_samples > 1_000.0


# --------------------------------------------------------------- coherence


def test_coherence_high_for_identical_and_low_for_unrelated():
    x = white_noise(10 * SR, seed=2)
    assert mean_coherence(x, x.copy(), SR) > 0.95
    y = white_noise(10 * SR, seed=3)
    assert mean_coherence(x, y, SR) < 0.05


def test_coherence_zero_for_silence_and_short_inputs():
    assert mean_coherence(np.zeros(SR), np.zeros(SR), SR) == 0.0
    assert mean_coherence(np.ones(100), np.ones(100), SR) == 0.0


# ---------------------------------------------------------------- polarity


def test_polarity_normal_and_inverted():
    # Polarity is judged on ALIGNED signals (the alignment itself is not the
    # polarity check's job).
    x = white_noise(5 * SR, seed=4)
    normal = polarity_check(x, x.copy())
    assert normal.polarity == 1 and not normal.inverted
    inverted = polarity_check(x, -x)
    assert inverted.polarity == -1 and inverted.inverted
    assert inverted.corr_inverted > inverted.corr_normal


def test_low_coherence_does_not_imply_inversion():
    # The project rule: unrelated content has LOW MSC but is NOT polarity
    # inverted — polarity must be decided by the correlation comparison.
    x = white_noise(5 * SR, seed=5)
    y = white_noise(5 * SR, seed=6)
    assert mean_coherence(x, y, SR) < 0.05  # low MSC...
    result = polarity_check(x, y)
    assert not result.inverted  # ...but NOT an inversion
    assert result.polarity == 0


# -------------------------------------------------------------- confidence


def _coarse(confidence=0.9):
    return MatchResult(
        matched=True, offset_samples=2_000.0, offset_seconds=2_000 / SR,
        confidence=confidence, method="fingerprint",
    )


def test_validate_pair_clean_pair_high_confidence():
    ref = speech_like(30 * SR, seed=7)
    tgt = drift_ppm(delay_samples(ref, 2_000), 120.0)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=2_000, config=FAST)
    report = validate_pair(ref, tgt, _coarse(), est, est.time_map, SR)
    assert isinstance(report, ValidationReport)
    assert report.success
    assert report.confidence > 0.7
    for key in ("coarse", "drift_r2", "residual", "coherence", "polarity"):
        assert key in report.evidence, key
    assert report.inverted is False


def test_validate_pair_unrelated_low_confidence():
    ref = white_noise(20 * SR, seed=8)
    tgt = white_noise(20 * SR, seed=9)
    report = validate_pair(
        ref, tgt, _coarse(0.05), None, ConstantOffsetTimeMap(0.0), SR
    )
    assert report.confidence < 0.4
    assert report.coherence is not None and report.coherence < 0.1


def test_validate_pair_reports_polarity_inversion():
    ref = white_noise(20 * SR, seed=10)
    tgt = -delay_samples(ref, 2_000)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=2_000, config=FAST)
    report = validate_pair(ref, tgt, _coarse(), est, est.time_map, SR)
    assert report.inverted
    assert any("POLARITY" in w for w in report.warnings)


def test_validate_pair_missing_evidence_is_warned_not_invented():
    ref = white_noise(10 * SR, seed=11)
    tgt = delay_samples(ref, 1_000)
    report = validate_pair(ref, tgt, _coarse(), None, None, SR)
    assert any("no usable drift model" in w for w in report.warnings)
    assert any("no time map" in w for w in report.warnings)
    assert 0.0 <= report.confidence <= 1.0
