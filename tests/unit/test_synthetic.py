"""Unit tests for the synthetic framework: reproducibility, semantics,
signal conditioning and the scenario registry."""

from __future__ import annotations

import numpy as np
import pytest

from synthetic import (
    Scenario,
    additive_gaussian,
    add_echo,
    delay_samples,
    drift_ppm,
    fractional_delay,
    piecewise_drift,
    schroeder_reverb,
    scenarios,
    white_noise,
)
from synthetic.scenarios import all_scenarios, scenario_clock_drift, scenario_fixed_delay

SR = 48_000


# ---------------------------------------------------------------- seeds


def test_seeded_generators_are_reproducible():
    a = white_noise(1_000, seed=42)
    b = white_noise(1_000, seed=42)
    c = white_noise(1_000, seed=43)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_seeded_noise_is_reproducible():
    x = white_noise(1_000, seed=1)
    y1 = additive_gaussian(x, snr_db=10.0, seed=7)
    y2 = additive_gaussian(x, snr_db=10.0, seed=7)
    assert np.array_equal(y1, y2)


def test_scenarios_are_reproducible():
    s1 = scenario_fixed_delay()
    s2 = scenario_fixed_delay()
    assert np.array_equal(s1.reference, s2.reference)
    assert np.array_equal(s1.target, s2.target)


# ---------------------------------------------------------------- delay


def test_delay_samples_positive_semantics():
    x = white_noise(1_000, seed=3)
    y = delay_samples(x, 17)
    assert np.array_equal(y[17:], x[:-17])  # content appears 17 samples LATER
    assert np.all(y[:17] == 0.0)


def test_delay_samples_negative_semantics():
    x = white_noise(1_000, seed=3)
    y = delay_samples(x, -17)
    assert np.array_equal(y[:-17], x[17:])  # content appears 17 samples EARLIER
    assert np.all(y[-17:] == 0.0)


def test_delay_samples_zero_is_identity():
    x = white_noise(100, seed=3)
    assert np.array_equal(delay_samples(x, 0), x)


def test_delay_samples_beyond_length_is_silence():
    x = white_noise(100, seed=3)
    assert np.all(delay_samples(x, 150) == 0.0)


def test_fractional_delay_half_sample_shifts_low_frequency_tone():
    # For a slowly varying signal the windowed-sinc filter must realize an
    # exact half-sample delay (a white-noise test cannot check this: the
    # filter's high-frequency tail terms are of the same order as the noise).
    from synthetic.generators import sine_wave

    freq = 100.0
    x = sine_wave(10_000, freq, SR)
    y = fractional_delay(x, 0.5)
    n = np.arange(10_000)
    expected = np.sin(2.0 * np.pi * freq * (n - 0.5) / SR)
    interior = slice(64, -64)
    assert np.allclose(y[interior], expected[interior], atol=2e-3)


def test_fractional_delay_zero_is_identity_in_interior():
    x = white_noise(10_000, seed=5)
    y = fractional_delay(x, 0.0)
    interior = slice(64, -64)
    assert np.allclose(y[interior], x[interior], atol=1e-6)


# ---------------------------------------------------------------- echo / reverb


def test_add_echo_composition():
    x = white_noise(10_000, seed=9)
    y = add_echo(x, [(100, 0.5)])
    # At sample n (n >= 100): y[n] = x[n] + 0.5 * x[n - 100].
    expected = x + 0.5 * delay_samples(x, 100)
    assert np.allclose(y, expected, atol=1e-6)


def test_schroeder_reverb_keeps_dry_signal():
    x = white_noise(10_000, seed=9)
    y = schroeder_reverb(x, wet=0.0)
    assert np.allclose(y, x, atol=1e-6)


# ---------------------------------------------------------------- drift


def test_drift_ppm_positive_ppm_stretches_output():
    x = white_noise(48_000, seed=4)
    y = drift_ppm(x, ppm=1000.0)
    assert len(y) == len(x) + 48  # 1000 ppm = 0.1%


def test_drift_ppm_gcc_sees_local_offset_in_short_windows():
    # A single full-window GCC is blind to drift for white noise (the drift
    # decorrelates the spectrum), which is exactly why the drift estimator
    # (Phase 4) uses SHORT windows: within one window the drift is < 2
    # samples and the local offset d(n) = ppm*1e-6 * n is measurable.
    from chronosync.fine.gcc_phat import gcc_phat

    ppm, duration_s = 200.0, 20.0
    sc = scenario_clock_drift(ppm=ppm, duration_s=duration_s, seed=0)
    p = ppm * 1e-6
    n = len(sc.reference)
    window = 8_192
    n0 = n // 2 - window // 2  # probe at the overlap midpoint
    # Both windows start at the SAME sample position: the target window then
    # contains the reference content shifted by -d(n0) = -p * n0 samples, so
    # GCC must report d(n0) = p * n0.
    ref_win = sc.reference[n0 : n0 + window]
    tgt_win = sc.target[n0 : n0 + window]
    res = gcc_phat(ref_win, tgt_win, SR)
    assert res.success
    assert abs(res.delay_samples - p * n0) < 3.0


def test_piecewise_drift_preserves_natural_segment_lengths():
    x = white_noise(int(10.0 * SR), seed=4)
    y = piecewise_drift(x, [(0.0, 5.0, 300.0), (5.0, 10.0, -150.0)])
    fade = int(0.005 * SR)
    expected = int(round(240_000 * 1.0003)) + int(round(240_000 * 0.99985)) - fade
    assert abs(len(y) - expected) <= 4


# ---------------------------------------------------------------- scenarios


def test_scenario_registry_covers_required_cases():
    names = set(all_scenarios())
    required = {
        "fixed_delay",
        "zero_delay",
        "negative_delay",
        "gain_difference",
        "additive_noise",
        "echo",
        "reverb",
        "periodic",
        "different_duration",
        "unrelated",
        "fractional_delay",
        "transients",
        "clock_drift",
        "piecewise_drift",
        "discontinuity",
    }
    assert required <= names


def test_all_scenarios_have_expected_offsets():
    for scenario in all_scenarios().values():
        assert isinstance(scenario, Scenario)
        if scenario.expected_offset_samples is not None:
            assert isinstance(scenario.expected_offset_samples, float)
        assert scenario.expected_offset_tolerance > 0.0
