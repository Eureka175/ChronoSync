"""Unit tests for GCC-PHAT delay estimation.

Covers the Phase-1 acceptance matrix: 0 / ±1 / ±10 / ±123 / ±12345, gain
difference, additive noise, echo, reverb, periodic signals, different
durations, fractional (sub-sample) delays, unrelated audio, search ranges,
silence, sign antisymmetry and cross-validation against scipy's plain
cross-correlation. All cases are deterministic (fixed seeds).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.signal import correlate, correlation_lags

from chronosync.fine.gcc_phat import GCCResult, gcc_phat
from chronosync.fine.peak import PeakSelectionConfig
from synthetic.delay import delay_samples, fractional_delay
from synthetic.echo import add_echo, schroeder_reverb
from synthetic.generators import sine_wave, speech_like, white_noise
from synthetic.noise import additive_gaussian

SR = 48_000


def _pair(delay: int, duration_s: float = 4.0, seed: int = 0):
    ref = white_noise(int(duration_s * SR), seed=seed)
    tgt = delay_samples(ref, delay)
    return ref, tgt


@pytest.mark.parametrize(
    "delay",
    [0, 1, -1, 10, -10, 123, -123, 12_345, -12_345],
)
def test_integer_delays_are_exact(delay: int):
    ref, tgt = _pair(delay)
    res = gcc_phat(ref, tgt, SR)
    assert res.success
    assert abs(res.delay_samples - delay) < 0.5
    assert res.confidence > 0.8
    # Regularized PHAT (eps_rel = 1e-3) trades a few % of peak height for
    # robustness against spectral leakage.
    assert res.peak_value > 0.85


@pytest.mark.parametrize("delay", [123_456, -123_456])
def test_large_delays_with_partial_overlap(delay: int):
    # Only ~68% of the 8 s target overlaps the reference; the peak height is
    # therefore reduced but the location must stay exact.
    ref = white_noise(int(8.0 * SR), seed=0)
    tgt = delay_samples(ref, delay)
    res = gcc_phat(ref, tgt, SR)
    assert res.success
    assert abs(res.delay_samples - delay) < 0.5
    assert res.confidence > 0.7
    assert res.peak_value > 0.4


def test_delay_seconds_matches_sample_rate():
    ref, tgt = _pair(12_345)
    res = gcc_phat(ref, tgt, SR)
    assert res.delay_seconds == pytest.approx(res.delay_samples / SR)


def test_gain_difference_is_irrelevant_to_phat():
    ref, tgt = _pair(2_500)
    for gain_db in (-60.0, -20.0, 20.0):
        tgt_scaled = tgt * (10.0 ** (gain_db / 20.0))
        res = gcc_phat(ref, tgt_scaled, SR)
        assert res.success
        assert abs(res.delay_samples - 2_500) < 0.5


@pytest.mark.parametrize("snr_db", [10.0, 0.0])
def test_additive_noise(snr_db: float):
    ref, tgt = _pair(2_500)
    tgt_noisy = additive_gaussian(tgt, snr_db, seed=1)
    res = gcc_phat(ref, tgt_noisy, SR)
    assert res.success
    assert abs(res.delay_samples - 2_500) < 0.5
    assert res.confidence > 0.4


def test_echo_keeps_direct_path_primary():
    ref, tgt = _pair(5_000)
    tgt_echo = add_echo(tgt, [(3_000, 0.6), (7_000, 0.35)])
    res = gcc_phat(ref, tgt_echo, SR)
    assert res.success
    assert abs(res.delay_samples - 5_000) < 1.0


def test_reverb_keeps_direct_path_primary():
    ref, tgt = _pair(5_000)
    tgt_rev = schroeder_reverb(tgt, rt60_s=0.8, wet=0.25)
    res = gcc_phat(ref, tgt_rev, SR)
    assert res.success
    assert abs(res.delay_samples - 5_000) < 1.0


def test_periodic_signal_reports_ambiguity():
    # A periodic signal has a sparse (comb) spectrum; PHAT gives every
    # frequency bin an equal vote, so its correlation peaks are intrinsically
    # tiny and mutually ambiguous. The contract: GCC must NOT pretend
    # success, must report low confidence, and the location it does report is
    # still correct modulo the period.
    freq, delay = 440.0, 100
    period = SR / freq
    ref = sine_wave(int(3.0 * SR), freq)
    tgt = delay_samples(ref, delay)
    res = gcc_phat(ref, tgt, SR)
    assert not res.success
    assert res.confidence < 0.6
    residual = abs(res.delay_samples - delay)
    assert min(residual % period, period - residual % period) < 2.0
    assert any("ambiguous" in w for w in res.warnings)


def test_different_durations():
    ref = white_noise(int(5.0 * SR), seed=3)
    content = ref[: 3 * SR]  # the target recorded only the first 3 s
    tgt = delay_samples(content, 12_345)
    res = gcc_phat(ref, tgt, SR)
    assert res.success
    assert abs(res.delay_samples - 12_345) < 0.5


def test_unrelated_signals_have_low_confidence():
    ref = white_noise(int(5.0 * SR), seed=0)
    tgt = white_noise(int(5.0 * SR), seed=1)
    res = gcc_phat(ref, tgt, SR)
    assert res.confidence < 0.4


def test_fractional_delay_sub_sample():
    ref = white_noise(int(5.0 * SR), seed=7)
    for delay in (0.4, 10.4, -7.3):
        tgt = fractional_delay(ref, delay)
        res = gcc_phat(ref, tgt, SR)
        assert res.success
        assert abs(res.delay_samples - delay) < 0.15


def test_sign_antisymmetry():
    ref, tgt = _pair(3_333)
    forward = gcc_phat(ref, tgt, SR)
    backward = gcc_phat(tgt, ref, SR)
    assert forward.delay_samples == pytest.approx(-backward.delay_samples, abs=0.05)


def test_matches_plain_cross_correlation_on_broadband_signal():
    ref, tgt = _pair(2_222)
    plain = correlate(ref, tgt, method="fft")
    lags = correlation_lags(len(ref), len(tgt))
    plain_delay = float(lags[np.argmax(plain)])
    res = gcc_phat(ref, tgt, SR)
    # scipy's correlate(a, v) peaks where v lags a, i.e. at -delay (ADR-003).
    assert plain_delay == pytest.approx(-2_222, abs=1)
    assert abs(res.delay_samples - 2_222) < 0.5


def test_search_range_restricts_result():
    ref, tgt = _pair(5_000)
    res = gcc_phat(ref, tgt, SR, search_min=4_900, search_max=5_100)
    assert res.success
    assert abs(res.delay_samples - 5_000) < 0.5
    assert res.search_range_samples == (4_900, 5_100)


def test_search_range_wrong_region_does_not_report_garbage():
    ref, tgt = _pair(5_000)
    res = gcc_phat(ref, tgt, SR, search_min=-1_000, search_max=1_000)
    # Either nothing usable is found (nan delay), or the result stays inside
    # the requested range — it must never report 5000 from outside the range.
    assert (not res.success) or (-1_000 <= res.delay_samples <= 1_000)


def test_peak_at_search_boundary_warns():
    ref, tgt = _pair(5_000)
    res = gcc_phat(ref, tgt, SR, search_min=4_000, search_max=5_000)
    assert res.success
    assert abs(res.delay_samples - 5_000) < 0.5
    assert any("boundary" in w for w in res.warnings)


def test_search_range_clipped_to_valid_lags():
    ref, tgt = _pair(0)
    res = gcc_phat(ref, tgt, SR, search_min=-1_000_000, search_max=1_000_000)
    n_ref, n_tgt = len(ref), len(tgt)
    assert res.search_range_samples == (-(n_tgt - 1), n_ref - 1)
    assert any("clipped" in w for w in res.warnings)


def test_empty_search_range_fails_cleanly():
    ref, tgt = _pair(100)
    res = gcc_phat(ref, tgt, SR, search_min=100, search_max=50)
    assert not res.success
    assert res.confidence == 0.0
    assert math.isnan(res.delay_samples)


def test_silence_fails_cleanly():
    ref = np.zeros(1_000, dtype=np.float32)
    tgt = np.zeros(1_000, dtype=np.float32)
    res = gcc_phat(ref, tgt, SR)
    assert not res.success
    assert res.confidence == 0.0


def test_empty_input_fails_cleanly():
    res = gcc_phat(np.zeros(0), np.zeros(100), SR)
    assert not res.success


def test_short_inputs():
    ref = white_noise(64, seed=5)
    tgt = delay_samples(ref, 7)
    res = gcc_phat(ref, tgt, SR)
    assert res.success
    assert abs(res.delay_samples - 7) < 0.5


def test_speech_like_signals():
    ref = speech_like(int(6.0 * SR), seed=11)
    tgt = additive_gaussian(delay_samples(ref, 20_000), 15.0, seed=12)
    res = gcc_phat(ref, tgt, SR)
    assert res.success
    assert abs(res.delay_samples - 20_000) < 1.0


def test_prior_resolves_periodic_ambiguity():
    freq, delay = 440.0, 100
    ref = sine_wave(int(3.0 * SR), freq)
    tgt = delay_samples(ref, delay)
    config = PeakSelectionConfig(
        prior_delay_samples=float(delay), prior_sigma_samples=20.0
    )
    res = gcc_phat(ref, tgt, SR, peak_config=config)
    # With a prior, the (equal-height, ambiguous) candidates are re-ranked by
    # proximity to the expected delay: the estimate lands on the true lag.
    # The measurement still reports low confidence — the prior does not
    # fabricate evidence.
    assert abs(res.delay_samples - delay) < 2.0
    assert res.confidence < 0.6


def test_multichannel_input_is_rejected():
    ref = np.zeros((2, 100), dtype=np.float32)
    tgt = np.zeros(100, dtype=np.float32)
    with pytest.raises(ValueError):
        gcc_phat(ref, tgt, SR)


def test_polarity_inverted_pair_is_detected_and_aligned():
    ref, tgt = _pair(2_500)
    res = gcc_phat(ref, -tgt, SR)
    assert res.success
    assert res.polarity == -1
    assert abs(res.delay_samples - 2_500) < 0.5
    assert any("polarity" in w for w in res.warnings)


def test_result_is_a_dataclass_with_documented_fields():
    ref, tgt = _pair(123)
    res = gcc_phat(ref, tgt, SR)
    assert isinstance(res, GCCResult)
    for field in (
        "delay_samples",
        "delay_seconds",
        "peak_value",
        "second_peak_value",
        "peak_prominence",
        "confidence",
        "search_range_samples",
        "success",
    ):
        assert hasattr(res, field)


def test_confidence_ordering_clean_noisy_unrelated():
    ref, tgt = _pair(2_500)
    clean = gcc_phat(ref, tgt, SR)
    noisy = gcc_phat(ref, additive_gaussian(tgt, 0.0, seed=1), SR)
    unrelated = gcc_phat(ref, white_noise(len(ref), seed=99), SR)
    assert clean.confidence > noisy.confidence > unrelated.confidence
