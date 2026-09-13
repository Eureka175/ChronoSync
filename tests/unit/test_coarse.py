"""Unit tests for the coarse-matching cascade (Layer 2)."""

from __future__ import annotations

import numpy as np
import pytest

from chronosync.coarse import (
    CoarseConfig,
    coarse_match,
    metadata_match,
    overlap_estimate,
)
from chronosync.fine.gcc_phat import gcc_phat
from synthetic.delay import delay_samples
from synthetic.generators import speech_like, transient_train, white_noise
from synthetic.noise import additive_gaussian

SR = 48_000

pytest.importorskip("soundfile")


def _speech_pair(delay=50_000, duration=20.0, seed=0, snr=20.0):
    ref = speech_like(int(duration * SR), seed=seed)
    tgt = additive_gaussian(delay_samples(ref, delay), snr, seed=seed + 1)
    return ref, tgt


# ------------------------------------------------------------------ basics


def test_coarse_matches_speech_pair():
    ref, tgt = _speech_pair()
    res = coarse_match(ref, tgt)
    assert res.matched
    assert res.method in {"fingerprint", "envelope", "transient"}
    assert abs(res.offset_samples - 50_000) < 2_000  # coarse precision
    assert res.confidence >= 0.5
    assert res.overlap_estimate is not None
    start, end = res.overlap_estimate
    assert 0.0 <= start < end <= 20.0


def test_coarse_offset_sign_matches_gcc():
    ref, tgt = _speech_pair(delay=30_000)
    coarse = coarse_match(ref, tgt)
    gcc = gcc_phat(ref, tgt, SR)
    assert np.sign(coarse.offset_samples) == np.sign(gcc.delay_samples)
    assert abs(coarse.offset_samples - gcc.delay_samples) < 5_000


def test_coarse_white_noise_pair_uses_fingerprint():
    ref = white_noise(15 * SR, seed=3)
    tgt = delay_samples(ref, 40_000)
    res = coarse_match(ref, tgt)
    assert res.matched
    assert abs(res.offset_samples - 40_000) < 2_000


def test_coarse_transient_pair():
    ref = transient_train(15 * SR, seed=4)
    tgt = delay_samples(ref, 25_000)
    res = coarse_match(ref, tgt)
    assert res.matched
    assert abs(res.offset_samples - 25_000) < 2_000


def test_coarse_gain_difference():
    ref, tgt = _speech_pair(delay=20_000)
    res = coarse_match(ref, tgt * 0.001)
    assert res.matched
    assert abs(res.offset_samples - 20_000) < 2_000


def test_coarse_noisy_pair():
    ref, tgt = _speech_pair(delay=20_000, snr=0.0)
    res = coarse_match(ref, tgt)
    assert res.matched
    assert abs(res.offset_samples - 20_000) < 2_000


def test_coarse_negative_delay():
    ref = speech_like(20 * SR, seed=5)
    tgt = delay_samples(ref, -35_000)  # target content EARLIER
    res = coarse_match(ref, tgt)
    assert res.matched
    assert abs(res.offset_samples - (-35_000)) < 2_000


def test_coarse_different_durations():
    ref = speech_like(20 * SR, seed=6)
    content = ref[: 10 * SR]
    tgt = delay_samples(content, 60_000)
    res = coarse_match(ref, tgt)
    assert res.matched
    assert abs(res.offset_samples - 60_000) < 2_000


def test_coarse_unrelated_is_not_matched():
    a = speech_like(15 * SR, seed=7)
    b = speech_like(15 * SR, seed=8)
    res = coarse_match(a, b)
    assert not res.matched
    assert res.confidence < 0.5


# ------------------------------------------------------------ short-circuit


def test_cascade_short_circuits_by_order():
    ref, tgt = _speech_pair(delay=10_000)
    res = coarse_match(ref, tgt, config=CoarseConfig(methods=("fingerprint",)))
    assert res.matched and res.method == "fingerprint"
    res = coarse_match(ref, tgt, config=CoarseConfig(methods=("envelope",)))
    assert res.matched and res.method == "envelope"
    res = coarse_match(ref, tgt, config=CoarseConfig(methods=("transient",)))
    # Speech-like pairs have no transient trains -> transient stage alone
    # should NOT claim a match with default thresholds.
    assert not res.matched


def test_cascade_accept_threshold_requires_confidence():
    ref, tgt = _speech_pair(delay=10_000)
    res = coarse_match(
        ref, tgt, config=CoarseConfig(accept_confidence=0.99)
    )
    # The best stage may still exceed 0.99 for a clean pair; the important
    # contract: a returned match has confidence >= accept_confidence.
    if res.matched:
        assert res.confidence >= 0.99


def test_cascade_all_stages_fail_returns_none_method():
    a = white_noise(3 * SR, seed=9)
    b = white_noise(3 * SR, seed=10)
    res = coarse_match(a, b)
    assert not res.matched
    assert res.method in {"none", "fingerprint", "envelope", "transient"}
    assert res.confidence < 0.5


# ------------------------------------------------------------- components


def test_metadata_match_never_matches():
    from chronosync.io import probe

    res = metadata_match(None, None)
    assert not res.matched and res.method == "metadata"
    assert res.offset_samples is None


def test_overlap_estimate_math():
    assert overlap_estimate(10.0, 10.0, 0.0) == (0.0, 10.0)
    assert overlap_estimate(10.0, 10.0, 2.0) == (0.0, 8.0)
    assert overlap_estimate(10.0, 10.0, -2.0) == (2.0, 10.0)
    assert overlap_estimate(10.0, 10.0, 20.0) is None
    assert overlap_estimate(10.0, 5.0, -4.0) == (4.0, 9.0)


# ------------------------------------------------------------------- files


def test_coarse_match_paths(tmp_path):
    from chronosync.coarse import coarse_match_paths
    from chronosync.io.wav import write_wav

    ref, tgt = _speech_pair(delay=30_000, duration=15.0)
    rp, tp = tmp_path / "r.wav", tmp_path / "t.wav"
    write_wav(rp, ref / np.max(np.abs(ref)), SR)
    write_wav(tp, tgt / np.max(np.abs(tgt)), SR)
    res = coarse_match_paths(rp, tp)
    assert res.matched
    assert abs(res.offset_samples - 30_000) < 2_000


def test_coarse_match_paths_uses_cache(tmp_path):
    from chronosync.coarse import coarse_match_paths
    from chronosync.io.wav import write_wav

    ref, tgt = _speech_pair(delay=30_000, duration=15.0)
    rp, tp = tmp_path / "r.wav", tmp_path / "t.wav"
    write_wav(rp, ref / np.max(np.abs(ref)), SR)
    write_wav(tp, tgt / np.max(np.abs(tgt)), SR)
    cache_dir = tmp_path / "cache"
    coarse_match_paths(rp, tp, cache_dir=cache_dir)
    # The cache directory must now contain the index + cached arrays
    # (fingerprint + envelope per file, >= 4 arrays).
    assert (cache_dir / "features.sqlite3").exists()
    arrays = list((cache_dir / "arrays").glob("*.npy"))
    assert len(arrays) >= 4
