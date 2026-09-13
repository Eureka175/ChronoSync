"""End-to-end smoke test: WAV files -> probe -> decode -> GCC.

Requires libsndfile (pytest.importorskip) but exercises the real Layer 0 +
Layer 3 path used by the CLI.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("soundfile", reason="libsndfile not installed")

from chronosync.fine.gcc_phat import gcc_phat
from chronosync.io import probe, read_canonical, write_wav
from synthetic.scenarios import scenario_fixed_delay

SR = 48_000


def _normalize(x: np.ndarray) -> np.ndarray:
    return (x / (np.max(np.abs(x)) + 1e-12) * 0.9).astype(np.float32)


def test_end_to_end_gcc(tmp_path):
    scenario = scenario_fixed_delay(delay=12_345, duration_s=3.0, seed=0)
    # Scale into [-1, 1] so the PCM_16 write does not clip (white noise
    # has unbounded peaks; the scenario is only normalized for the file test).
    ref_pcm = _normalize(scenario.reference)
    tgt_pcm = _normalize(scenario.target)
    ref_path = tmp_path / "reference.wav"
    tgt_path = tmp_path / "target.wav"
    write_wav(ref_path, ref_pcm, SR)
    write_wav(tgt_path, tgt_pcm, SR)

    ref_track = probe(ref_path)
    tgt_track = probe(tgt_path)
    assert ref_track.sample_rate == SR
    assert ref_track.channels == 1
    assert ref_track.duration_seconds == pytest.approx(3.0, abs=0.01)
    assert tgt_track.frames == ref_track.frames

    ref = read_canonical(ref_path)
    tgt = read_canonical(tgt_path)
    assert ref.sample_rate == SR
    assert ref.mono_mix.dtype == np.float32
    assert np.allclose(ref.mono_mix, ref_pcm, atol=1e-3)  # PCM_16 quantization

    res = gcc_phat(ref.mono_mix, tgt.mono_mix, SR)
    assert res.success
    assert abs(res.delay_samples - 12_345) < 0.5
