"""Unit tests for the Adobe Audition SESX exporter.

Format facts (docs/research/notes/sesx_format.md): plain XML, all times in
integer SAMPLES at the session rate, clips reference external WAVs through
the <files> table. Audition cannot change a clip's playback rate, so linear
drift is exported as documented stair-step clips.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from chronosync.export.sesx import (
    SesxClip,
    SesxTrack,
    build_sesx_xml,
    clips_from_timemap,
    write_sesx,
)
from chronosync.models.timemap import (
    ConstantOffsetTimeMap,
    IdentityTimeMap,
    LinearTimeMap,
    PiecewiseLinearTimeMap,
)

SR = 48_000


def _parse(xml: str) -> ET.Element:
    # strip the DOCTYPE, which ElementTree accepts but keep it separately
    assert "<!DOCTYPE sesx>" in xml
    body = xml.split("<!DOCTYPE sesx>", 1)[1]
    return ET.fromstring(body)


# ------------------------------------------------------------- time units


def test_constant_offset_single_exact_clip():
    tm = ConstantOffsetTimeMap(offset_seconds=12_345 / SR)
    track = clips_from_timemap("C:/audio/x.wav", "Mic 1", 960_000, SR, tm)
    assert len(track.clips) == 1
    clip = track.clips[0]
    assert clip.start_samples == 12_345  # integer samples, exact
    assert clip.source_in_samples == 0
    assert clip.source_out_samples == 960_000
    assert clip.end_samples == 12_345 + 960_000


def test_identity_single_clip_at_zero():
    track = clips_from_timemap("x.wav", "T", 48_000, SR, IdentityTimeMap())
    assert track.clips[0].start_samples == 0


def test_linear_drift_stair_step_approximation():
    tm = LinearTimeMap.from_ppm(alpha_ppm=200.0, offset_seconds=0.5)
    track = clips_from_timemap("x.wav", "T", 60 * SR, SR, tm, chunk_seconds=10.0)
    assert len(track.clips) == 6
    for i, clip in enumerate(track.clips):
        assert clip.source_in_samples == i * 10 * SR
        assert clip.source_out_samples - clip.source_in_samples == 10 * SR
        expected_start = round((0.5 + i * 10.0 * (1 + 200e-6)) * SR)
        assert abs(clip.start_samples - expected_start) <= 2
    # starts are strictly increasing
    starts = [c.start_samples for c in track.clips]
    assert starts == sorted(starts)


def test_piecewise_gap_becomes_timeline_gap():
    # local 0..10 -> global 0..10 ; flat local span 10..10.1 (drop gap) ;
    # local 10.1..20 -> global 10..19.9
    tm = PiecewiseLinearTimeMap(
        knots=((0.0, 0.0), (10.0, 10.0), (10.1, 10.0), (20.0, 19.9))
    )
    track = clips_from_timemap("x.wav", "T", 20 * SR, SR, tm)
    assert len(track.clips) == 2
    first, second = track.clips
    assert first.end_samples == 10 * SR
    assert second.start_samples == 10 * SR
    assert first.source_out_samples == 10 * SR
    assert second.source_in_samples == int(round(10.1 * SR))


# ------------------------------------------------------------ xml structure


def test_xml_structure_and_linkage():
    tm = ConstantOffsetTimeMap(offset_seconds=1000 / SR)
    track = clips_from_timemap("C:/a.wav", "Track & <one> 中文", 48_000, SR, tm)
    xml = build_sesx_xml([track], SR)
    doc = _parse(xml)

    assert doc.tag == "sesx"
    session = doc.find("session")
    assert session is not None
    assert session.get("sampleRate") == "48000"
    assert session.get("duration") == str(48_000 + 1000)

    tracks = session.find("tracks")
    audio_tracks = tracks.findall("audioTrack")
    assert len(audio_tracks) == 1
    assert tracks.find("masterTrack") is not None
    # track routes to the master
    out = audio_tracks[0].find("trackAudioParameters/trackOutput")
    assert out.get("outputID") == tracks.find("masterTrack").get("id")

    clip = audio_tracks[0].find("audioClip")
    assert clip.get("startPoint") == "1000"
    assert clip.get("sourceOutPoint") == "48000"
    # clip name round-trips through XML escaping
    assert clip.get("name") == "Track & <one> 中文"

    files = doc.findall("files/file")
    assert len(files) == 1
    assert files[0].get("mediaHandler") == "AmioWav"
    assert files[0].get("id") == clip.get("fileID")
    assert files[0].get("relativePath") == "a.wav"


def test_all_time_attributes_are_integer_samples():
    t1 = clips_from_timemap("a.wav", "A", 100_000, SR, IdentityTimeMap())
    t2 = clips_from_timemap("b.wav", "B", 50_000, SR,
                            ConstantOffsetTimeMap(offset_seconds=2.5))
    doc = _parse(build_sesx_xml([t1, t2], SR))
    for attr in ("startPoint", "endPoint", "sourceInPoint", "sourceOutPoint"):
        for clip in doc.findall(".//audioClip"):
            int(clip.get(attr))  # must not raise
    int(doc.find("session").get("duration"))


def test_multiple_tracks_and_files():
    a = clips_from_timemap("C:/a.wav", "A", 10 * SR, SR, IdentityTimeMap())
    b = clips_from_timemap("C:/b.wav", "B", 10 * SR, SR,
                           ConstantOffsetTimeMap(offset_seconds=5.0))
    doc = _parse(build_sesx_xml([a, b], SR))
    assert len(doc.findall(".//audioTrack")) == 2
    files = doc.findall("files/file")
    assert len(files) == 2
    ids = [f.get("id") for f in files]
    clip_ids = [c.get("fileID") for c in doc.findall(".//audioClip")]
    assert set(ids) == set(clip_ids) == {"0", "1"}


def test_write_sesx_utf8(tmp_path):
    tm = ConstantOffsetTimeMap(offset_seconds=0.0)
    track = clips_from_timemap("x.wav", "轨道 1", 48_000, SR, tm)
    path = write_sesx(tmp_path / "out.sesx", [track], SR)
    text = path.read_text(encoding="utf-8")
    assert "轨道 1" in text
    doc = ET.fromstring(text.split("<!DOCTYPE sesx>", 1)[1])
    assert doc.find(".//audioTrack/trackParameters/name").text == "轨道 1"


def test_negative_start_is_trimmed_at_session_origin():
    # d = -4000: content starts 4000 samples BEFORE the session origin; the
    # clip must start at 0 with its source in-point advanced accordingly.
    tm = ConstantOffsetTimeMap(offset_seconds=-4_000 / SR)
    track = clips_from_timemap("x.wav", "T", 96_000, SR, tm)
    assert len(track.clips) == 1
    clip = track.clips[0]
    assert clip.start_samples == 0
    assert clip.source_in_samples == 4_000
    assert clip.source_out_samples == 96_000


def test_empty_session_has_zero_duration():
    doc = _parse(build_sesx_xml([], SR))
    assert doc.find("session").get("duration") == "0"
    assert doc.find("session/tracks/masterTrack") is not None
    assert doc.findall("files/file") == []
