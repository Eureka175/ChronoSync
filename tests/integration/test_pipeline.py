"""End-to-end pipeline smoke test: files -> coarse -> drift -> TimeMap ->
SESX timeline (non-destructive export)."""

from __future__ import annotations

import warnings
from xml.etree import ElementTree as ET

import numpy as np
import pytest

pytest.importorskip("soundfile", reason="libsndfile not installed")

from chronosync.coarse import coarse_match_paths
from chronosync.drift import DriftConfig, estimate_drift
from chronosync.export.sesx import clips_from_timemap, write_sesx
from chronosync.io.wav import write_wav
from synthetic.delay import delay_samples
from synthetic.drift import drift_ppm
from synthetic.generators import speech_like

SR = 48_000


def _normalize(x):
    return (x / (np.max(np.abs(x)) + 1e-12) * 0.9).astype(np.float32)


def test_full_pipeline_to_sesx(tmp_path):
    # Ground truth: 30 s speech-like pair, +100 ppm drift, +4000 samples.
    ref = speech_like(30 * SR, seed=0)
    tgt = drift_ppm(delay_samples(ref, 4_000), 100.0)
    ref_path = tmp_path / "reference.wav"
    tgt_path = tmp_path / "target.wav"
    write_wav(ref_path, _normalize(ref), SR)
    write_wav(tgt_path, _normalize(tgt), SR)

    coarse = coarse_match_paths(ref_path, tgt_path, cache_dir=tmp_path / "cache")
    assert coarse.matched

    est = estimate_drift(
        ref, tgt, SR, coarse_offset_samples=coarse.offset_samples,
        config=DriftConfig(window_samples=8_192, min_window_samples=8_192,
                           min_windows=4, min_windows_per_segment=3),
    )
    assert est.success
    assert est.classification == "clock_drift"
    assert abs(est.model.alpha_ppm - 100.0) < 10.0

    # Non-destructive SESX timeline from the estimated TimeMap.
    track = clips_from_timemap(str(tgt_path), "Target", len(tgt), SR, est.time_map)
    sesx_path = write_sesx(tmp_path / "session.sesx", [track], SR)
    xml = sesx_path.read_text(encoding="utf-8")
    doc = ET.fromstring(xml.split("<!DOCTYPE sesx>", 1)[1])
    clips = doc.findall(".//audioClip")
    assert len(clips) >= 1
    # clip placement starts near the estimated offset
    first_start = int(clips[0].get("startPoint"))
    assert abs(first_start - est.model.beta_samples) < SR  # within one second

    # Rendering (optional feature) realigns the pair.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from chronosync.drift import correct_track
        from chronosync.fine.gcc_phat import gcc_phat

        corrected = correct_track(tgt, est.time_map, SR)
    for s in (5, 15, 25):
        w = slice(s * SR, (s + 1) * SR)
        assert abs(gcc_phat(ref[w], corrected[w], SR).delay_samples) < 2.0
