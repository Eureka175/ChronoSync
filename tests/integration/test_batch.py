"""Integration test: multi-track batch alignment (Phases 5-7 together)."""

from __future__ import annotations

import json
from xml.etree import ElementTree as ET

import numpy as np
import pytest

pytest.importorskip("soundfile", reason="libsndfile not installed")

from chronosync.export import write_csv, write_sesx
from chronosync.export.json import track_alignment_to_dict, write_json
from chronosync.export.sesx import clips_from_timemap
from chronosync.io import probe
from chronosync.io.wav import write_wav
from chronosync.pipeline import PipelineConfig, batch_align
from synthetic.delay import delay_samples
from synthetic.drift import drift_ppm
from synthetic.generators import speech_like

SR = 48_000


def _norm(x):
    return (x / (np.max(np.abs(x)) + 1e-12) * 0.9).astype(np.float32)


def _write(name, data):
    path = f"tmp_{name}.wav"
    write_wav(path, _norm(data), SR)
    return path


def test_batch_align_three_tracks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Ground truth: A = reference; B = +2000 samples (+120 ppm drift);
    # C = -3000 samples (no drift). All three share 25 s of speech-like.
    base = speech_like(25 * SR, seed=0)
    a = base
    b = drift_ppm(delay_samples(base, 2_000), 120.0)
    c = delay_samples(base, -3_000)
    pa, pb, pc = _write("a", a), _write("b", b), _write("c", c)

    result = batch_align(
        [pa, pb, pc],
        PipelineConfig(max_seconds=25.0),
    )
    solved = result.solved
    assert solved.success
    by_name = {t.track: t.offset_samples for t in solved.tracks}
    assert by_name[solved.reference] == 0.0
    # offsets relative to A (the auto-selected reference may be any track)
    def rel_a(name):
        return by_name[name] - by_name["tmp_a.wav"]

    assert abs(rel_a("tmp_b.wav") - 2_000.0) < 150.0
    assert abs(rel_a("tmp_c.wav") - (-3_000.0)) < 150.0

    # the reference is auto-selected as the most connected track
    assert any("auto-selected" in w for w in solved.warnings)

    # TimeMaps: direct-to-reference pairs carry drift maps.
    assert all(
        t.track in result.time_maps for t in solved.tracks
    )

    # JSON round-trip
    payload = {
        "status": "success",
        "reference": solved.reference,
        "tracks": [
            track_alignment_to_dict(t, result.time_maps.get(t.track))
            for t in solved.tracks
        ],
        "warnings": result.warnings,
    }
    jp = write_json(tmp_path / "batch.json", payload)
    data = json.loads(jp.read_text(encoding="utf-8"))
    assert data["reference"] == solved.reference
    assert len(data["tracks"]) == 3

    # CSV
    write_csv(tmp_path / "batch.csv", solved.tracks, result.time_maps)

    # SESX: three tracks, each with clips, all files linked.
    sesx_tracks = []
    for track in sorted(result.time_maps):
        tm = result.time_maps[track]
        frames = probe(track).frames
        sesx_tracks.append(clips_from_timemap(str(tmp_path / track), track, frames, SR, tm))
    sp = write_sesx(tmp_path / "batch.sesx", sesx_tracks, SR)
    doc = ET.fromstring(
        sp.read_text(encoding="utf-8").split("<!DOCTYPE sesx>", 1)[1]
    )
    assert len(doc.findall(".//audioTrack")) == 3
    assert len(doc.findall("files/file")) == 3


def test_batch_rejects_unrelated_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    base = speech_like(15 * SR, seed=1)
    unrelated = speech_like(15 * SR, seed=2)
    pa = _write("x", base)
    pb = _write("y", delay_samples(base, 1_000))
    pc = _write("z", unrelated)
    result = batch_align([pa, pb, pc], PipelineConfig(max_seconds=15.0))
    assert any("matched nothing" in w for w in result.warnings)
    assert "tmp_z.wav" not in {t.track for t in result.solved.tracks}
