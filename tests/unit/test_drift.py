"""Unit tests for drift estimation and time-map correction (Layer 4)."""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from chronosync.drift import (
    DriftConfig,
    WindowSchedule,
    correct_track,
    estimate_drift,
    overlap_center_range,
    robust_linear_fit,
    weighted_linear_fit,
)
from chronosync.fine.gcc_phat import gcc_phat
from chronosync.models.timemap import LinearTimeMap, PiecewiseLinearTimeMap
from synthetic.delay import delay_samples
from synthetic.drift import drift_ppm, drop_samples, insert_samples
from synthetic.generators import speech_like, white_noise

SR = 48_000

# White noise decorrelates under PHAT when the in-window drift exceeds ~1
# sample, so noise-based drift tests use short windows (see docs/algorithms.md
# section 5); speech-like tests exercise the default 30 s windows + adaptive
# shrink. All configs are explicit — no magic numbers in the estimator.

FAST = DriftConfig(
    window_samples=8_192,
    min_window_samples=8_192,
    min_windows=4,
    min_windows_per_segment=3,
)


def _residual(ref, corrected, positions=(8, 25, 45), seconds=1.0):
    out = []
    for s in positions:
        w = slice(int(s * SR), int((s + seconds) * SR))
        out.append(gcc_phat(ref[w], corrected[w], SR).delay_samples)
    return out


# ---------------------------------------------------------------- windows


def test_window_schedule_centers():
    sch = WindowSchedule(window_samples=1000, overlap_ratio=0.5)
    centers = sch.centers(500, 2500)
    assert centers == [500, 1000, 1500, 2000, 2500]
    assert sch.centers(500, 400) == []


def test_overlap_center_range():
    sch = WindowSchedule(window_samples=1000, overlap_ratio=0.5)
    lo, hi = overlap_center_range(10_000, 10_000, 0, sch)
    assert (lo, hi) == (500, 9_500)
    # d = +2000: the target window is shifted right; the earliest valid
    # center is still 500 (target window [2500, 3500) fits fine).
    lo, hi = overlap_center_range(10_000, 10_000, 2_000, sch)
    assert (lo, hi) == (500, 7_500)
    # d = -2000: the reference window must clear the target's left edge.
    lo, hi = overlap_center_range(10_000, 10_000, -2_000, sch)
    assert (lo, hi) == (2_500, 9_500)
    lo, hi = overlap_center_range(10_000, 800, 0, sch)
    assert lo > hi  # no full 1000-sample window fits inside 800 samples


# ------------------------------------------------------------- regression


def test_weighted_linear_fit_exact():
    t = np.arange(100.0)
    d = 0.0002 * t + 500.0
    alpha, beta, r2, residuals = weighted_linear_fit(t, d)
    assert alpha == pytest.approx(0.0002, abs=1e-12)
    assert beta == pytest.approx(500.0, abs=1e-9)
    assert r2 == pytest.approx(1.0)
    assert np.all(np.abs(residuals) < 1e-9)


def test_weighted_fit_respects_weights():
    t = np.arange(50.0)
    d = 0.001 * t + 10.0
    w = np.ones_like(t)
    w[10:] = 0.0  # only the first 10 points count
    alpha, beta, _, _ = weighted_linear_fit(t, d, w)
    assert alpha == pytest.approx(0.001, abs=1e-9)
    assert beta == pytest.approx(10.0, abs=1e-9)


def test_robust_fit_rejects_planted_outliers():
    rng = np.random.default_rng(0)
    t = np.arange(60.0)
    d = 0.0002 * t + 100.0 + rng.normal(0, 0.1, 60)
    d[20] += 400.0
    d[21] -= 350.0
    alpha, beta, r2, _, mask, dropped = robust_linear_fit(t, d)
    assert alpha == pytest.approx(0.0002, abs=2e-3)
    assert beta == pytest.approx(100.0, abs=1.0)
    assert set(dropped) == {20, 21}
    assert mask.sum() == 58


# --------------------------------------------------------------- estimator


def test_linear_drift_white_noise():
    ref = white_noise(30 * SR, seed=0)
    tgt = drift_ppm(delay_samples(ref, 1_000), 150.0)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=1_000, config=FAST)
    assert est.success
    assert est.classification == "clock_drift"
    assert abs(est.model.alpha_ppm - 150.0) < 5.0
    assert est.model.r2 > 0.95
    assert isinstance(est.time_map, LinearTimeMap)
    assert est.time_map.scale == pytest.approx(1.0 / (1 + 150e-6), rel=1e-4)


def test_linear_drift_timemap_math():
    # content at reference sample n lives at local sample n*(1+p) + beta;
    # the map must send it back to n.
    alpha_ppm, beta = 150.0, 2_000.0
    p = alpha_ppm * 1e-6
    tm = LinearTimeMap.from_ppm(alpha_ppm, offset_seconds=0.0)
    tm = LinearTimeMap(
        scale=1.0 / (1.0 + p), offset_seconds=-beta / (SR * (1.0 + p))
    )
    for n in (0, 48_000, 480_000, 960_000):
        local = (beta + n * (1.0 + p)) / SR
        assert tm.to_global(local) * SR == pytest.approx(n, abs=1e-6)


def test_constant_offset_classification():
    ref = white_noise(30 * SR, seed=1)
    tgt = delay_samples(ref, 6_000)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=6_000, config=FAST)
    assert est.success
    assert est.classification == "constant_offset"
    assert abs(est.model.alpha_ppm) < 2.0
    # d = +6000: the target timeline runs ahead -> T_global(0) = -6000/sr,
    # and the content (which starts at local sample 6000) maps to global 0.
    assert est.time_map.to_global(0.0) * SR == pytest.approx(-6_000, abs=50)
    assert est.time_map.to_global(6_000 / SR) * SR == pytest.approx(0.0, abs=50)


def test_piecewise_drift_two_segments():
    ref = white_noise(40 * SR, seed=2)
    tgt = np.concatenate(
        [drift_ppm(ref[: 20 * SR], 250.0), drift_ppm(ref[20 * SR :], -100.0)]
    )
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=0.0, config=FAST)
    assert est.success
    assert est.classification == "piecewise_drift"
    assert len(est.segments) == 2
    assert abs(est.segments[0].model.alpha_ppm - 250.0) < 5.0
    assert abs(est.segments[1].model.alpha_ppm - (-100.0)) < 5.0
    assert isinstance(est.time_map, PiecewiseLinearTimeMap)
    # the split sits near 20 s
    split_s = est.segments[1].start_sample / SR
    assert abs(split_s - 20.0) < 2.0


def test_discontinuity_detected():
    ref = white_noise(40 * SR, seed=3)
    tgt = drop_samples(delay_samples(ref, 800), 20 * SR, 4_800)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=800, config=FAST)
    assert est.success
    assert est.classification == "discontinuity"
    assert len(est.segments) == 2
    jumps = [
        w for w in est.warnings if w.startswith("CLOCK_DISCONTINUITY")
    ]
    assert len(jumps) == 1
    assert "-4800" in jumps[0].replace("~", "") or "4800" in jumps[0]
    # split position near 20 s
    assert abs(est.segments[1].start_sample / SR - 20.0) < 2.0


def test_drop_reports_negative_local_jump_warning():
    # A dropped buffer makes the content appear EARLIER (d jumps negative);
    # the local->global mapping then contains a flat GAP span.
    ref = white_noise(30 * SR, seed=4)
    tgt = drop_samples(delay_samples(ref, 500), 15 * SR, 4_800)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=500, config=FAST)
    assert est.success
    assert est.classification == "discontinuity"
    assert any("negative local-time jump" in w for w in est.warnings)


def test_insert_produces_positive_jump_without_negative_warning():
    # Inserted zeros make the content appear LATER (d jumps positive): the
    # flat span (the inserted silence) is simply skipped on correction.
    ref = white_noise(30 * SR, seed=4)
    tgt = insert_samples(delay_samples(ref, 500), 15 * SR, 4_800)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=500, config=FAST)
    assert est.success
    assert est.classification == "discontinuity"
    assert not any("negative local-time jump" in w for w in est.warnings)


def test_no_overlap_classification():
    a = white_noise(20 * SR, seed=5)
    b = white_noise(20 * SR, seed=6)
    est = estimate_drift(a, b, SR, coarse_offset_samples=0.0, config=FAST)
    assert not est.success
    assert est.classification == "no_overlap"
    assert est.time_map is None


def test_bad_measurements_rejected():
    ref = white_noise(30 * SR, seed=7)
    tgt = drift_ppm(delay_samples(ref, 1_000), 150.0)
    # corrupt three windows with unrelated content
    for c in (5 * SR, 10 * SR, 20 * SR):
        tgt[c : c + 8_192] = white_noise(8_192, seed=100 + c)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=1_000, config=FAST)
    assert est.success
    assert est.classification == "clock_drift"
    assert abs(est.model.alpha_ppm - 150.0) < 10.0
    assert any("bad measurements" in w for w in est.warnings)


def test_adaptive_window_shrink_for_noise_like_content():
    ref = speech_like(60 * SR, seed=8)
    tgt = drift_ppm(delay_samples(ref, 5_000), 120.0)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=5_000)
    assert est.success
    assert est.classification == "clock_drift"
    assert abs(est.model.alpha_ppm - 120.0) < 20.0
    assert any("shrinking" in w for w in est.warnings)


def test_corrected_track_realigns_white_noise():
    ref = white_noise(30 * SR, seed=9)
    tgt = drift_ppm(delay_samples(ref, 1_000), 150.0)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=1_000, config=FAST)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        corrected = correct_track(tgt, est.time_map, SR)
    # The delay-then-drift synthetic truncates the stretched tail, so the
    # corrected output is ~1000 samples shorter than the reference; the
    # alignment quality is judged on interior windows.
    assert abs(len(corrected) - len(ref)) < 2_000
    for d in _residual(ref, corrected, positions=(8, 15, 25)):
        assert abs(d) < 2.0


def test_corrected_track_constant_offset():
    ref = white_noise(20 * SR, seed=10)
    tgt = delay_samples(ref, 6_000)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=6_000, config=FAST)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        corrected = correct_track(tgt, est.time_map, SR)
    for d in _residual(ref, corrected, positions=(4, 10, 16)):
        assert abs(d) < 1.0


def test_corrected_track_piecewise():
    ref = white_noise(40 * SR, seed=11)
    tgt = np.concatenate(
        [drift_ppm(ref[: 20 * SR], 250.0), drift_ppm(ref[20 * SR :], -100.0)]
    )
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=0.0, config=FAST)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        corrected = correct_track(tgt, est.time_map, SR)
    for d in _residual(ref, corrected, positions=(5, 15, 25, 35)):
        assert abs(d) < 2.0


def test_measurements_report_full_offset_after_fixup():
    ref = white_noise(20 * SR, seed=12)
    tgt = drift_ppm(delay_samples(ref, 3_000), 100.0)
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=3_000, config=FAST)
    assert est.model.beta_samples == pytest.approx(3_000.0, abs=50.0)
    # measured offsets track beta + alpha * center
    centers = np.array([m.center_samples for m in est.measurements])
    offsets = np.array([m.offset_samples for m in est.measurements])
    alpha, beta, r2, _ = weighted_linear_fit(centers, offsets)
    assert beta == pytest.approx(3_000.0, abs=50.0)
    assert r2 > 0.9
