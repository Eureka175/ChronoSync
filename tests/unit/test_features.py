"""Unit tests for the feature layer (envelope / spectral / fingerprint)."""

from __future__ import annotations

import numpy as np
import pytest

from chronosync.features import (
    EnvelopeConfig,
    SpectralConfig,
    compute_fingerprint,
    decimate_envelope,
    envelope,
    envelope_rate,
    match_fingerprints,
    spectral_flux,
    transient_map,
)
from synthetic.delay import delay_samples
from synthetic.generators import (
    sine_wave,
    speech_like,
    transient_train,
    white_noise,
)
from synthetic.noise import additive_gaussian

SR = 48_000


# ---------------------------------------------------------------- envelope


def test_envelope_frame_count_and_level():
    x = white_noise(SR, seed=0)  # unit variance -> RMS ~ 1
    cfg = EnvelopeConfig(frame_samples=1024, hop_samples=512)
    env = envelope(x, cfg)
    assert env.shape == (1 + (SR - 1024) // 512,)
    assert env.dtype == np.float32
    assert abs(float(np.mean(env)) - 1.0) < 0.05


def test_envelope_matches_blockwise_reference():
    x = white_noise(10_000, seed=1)
    cfg = EnvelopeConfig(frame_samples=1024, hop_samples=512)
    env = envelope(x, cfg)
    naive = np.sqrt(np.mean(
        np.lib.stride_tricks.sliding_window_view(x, 1024)[::512] ** 2, axis=1
    ))
    assert np.allclose(env, naive, atol=1e-6)


def test_envelope_edge_cases():
    assert envelope(np.zeros(0)).shape == (0,)
    short = envelope(white_noise(100, seed=2))
    assert short.shape == (1,)
    assert short[0] > 0.0


def test_envelope_rate_and_decimation():
    cfg = EnvelopeConfig(frame_samples=1024, hop_samples=512)
    assert envelope_rate(SR, cfg) == pytest.approx(SR / 512)
    env = envelope(white_noise(SR, seed=3), cfg)
    dec, rate = decimate_envelope(env, envelope_rate(SR, cfg), target_rate=100.0)
    assert rate == pytest.approx(93.75)  # 48000/512 = 93.75 -> block = 1
    assert dec.size == env.size
    dec2, rate2 = decimate_envelope(env, 48000 / 512, target_rate=10.0)
    assert rate2 == pytest.approx(48000 / 512 / 9)


# ---------------------------------------------------------------- spectral


def test_spectral_flux_detects_transients():
    x = transient_train(4 * SR, interval_s=0.5, jitter_s=0.0, seed=0)
    times, strengths = transient_map(x, SR)
    assert times.size >= 6  # ~8 clicks, minus edge effects
    # Click times are at multiples of 0.5 s (+ decaying tail); allow 2 hops.
    hop_s = 512 / SR
    for t in times:
        nearest = min(abs(t - k * 0.5) for k in range(8))
        assert nearest <= 2 * hop_s
    assert np.all(strengths > 0.0)


def test_spectral_flux_silence_is_empty():
    assert spectral_flux(np.zeros(SR, dtype=np.float32), SR).size == 0
    times, strengths = transient_map(np.zeros(SR, dtype=np.float32), SR)
    assert times.size == 0 and strengths.size == 0


def test_spectral_flux_chunked_matches_single():
    x = speech_like(3 * SR, seed=5)
    single = spectral_flux(x, SR, chunk_seconds=30.0)
    chunked = spectral_flux(x, SR, chunk_seconds=0.5)
    assert chunked.size >= single.size - 1
    assert np.allclose(chunked[: single.size], single, atol=1e-5)


# -------------------------------------------------------------- fingerprint


def test_fingerprint_is_deterministic_and_chunk_consistent():
    x = speech_like(20 * SR, seed=7)
    fp1 = compute_fingerprint(x, SR, chunk_seconds=None)
    fp2 = compute_fingerprint(x, SR, chunk_seconds=None)
    fp3 = compute_fingerprint(x, SR, chunk_seconds=5.0)
    assert np.array_equal(fp1.hashes, fp2.hashes)
    assert np.array_equal(fp1.hashes, fp3.hashes)  # chunked == single exactly
    assert fp1.hashes.shape[1] == 2


def test_fingerprint_matches_delayed_signal():
    x = speech_like(20 * SR, seed=8)
    y = additive_gaussian(delay_samples(x, 50_000), 15.0, seed=9)
    fp_a = compute_fingerprint(x, SR)
    fp_b = compute_fingerprint(y, SR)
    m = match_fingerprints(fp_a, fp_b)
    assert m.success
    assert abs(m.offset_samples - 50_000) < 1_500  # sub-frame histogram estimate
    assert m.confidence > 0.8
    assert m.matching_hashes > 10


def test_fingerprint_sign_convention_positive_when_target_later():
    x = speech_like(10 * SR, seed=10)
    y = delay_samples(x, 20_000)  # events later in target -> d > 0
    m = match_fingerprints(compute_fingerprint(x, SR), compute_fingerprint(y, SR))
    assert m.offset_samples > 15_000


def test_fingerprint_gain_invariant():
    x = speech_like(10 * SR, seed=11)
    for gain in (0.001, 100.0):
        y = delay_samples(x, 8_000) * gain
        m = match_fingerprints(compute_fingerprint(x, SR), compute_fingerprint(y, SR))
        assert m.success
        assert abs(m.offset_samples - 8_000) < 1_500


def test_fingerprint_unrelated_signals_fail():
    a = compute_fingerprint(speech_like(10 * SR, seed=12), SR)
    b = compute_fingerprint(speech_like(10 * SR, seed=13), SR)
    m = match_fingerprints(a, b)
    assert (not m.success) or m.confidence < 0.5
    assert m.votes < 5 or m.matching_hashes < 5


def test_fingerprint_noisy_signal_still_matches():
    x = speech_like(15 * SR, seed=14)
    y = additive_gaussian(delay_samples(x, 30_000), 0.0, seed=15)
    m = match_fingerprints(compute_fingerprint(x, SR), compute_fingerprint(y, SR))
    assert m.success
    assert abs(m.offset_samples - 30_000) < 1_500


def test_fingerprint_max_lag_restriction():
    x = speech_like(10 * SR, seed=16)
    y = delay_samples(x, 30_000)
    m = match_fingerprints(
        compute_fingerprint(x, SR), compute_fingerprint(y, SR), max_lag_seconds=2.0
    )
    # With a 2 s window the true 0.625 s offset is inside -> still found.
    assert m.success
    assert abs(m.offset_samples - 30_000) < 1_500
    m2 = match_fingerprints(
        compute_fingerprint(x, SR), compute_fingerprint(y, SR), max_lag_seconds=0.1
    )
    # 0.1 s window excludes the true offset -> nothing usable.
    assert not m2.success
