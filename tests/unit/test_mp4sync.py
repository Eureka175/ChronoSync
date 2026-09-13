"""Unit tests for the MP4 wireless-mic sync pipeline (no ffmpeg needed)."""

from __future__ import annotations

import numpy as np
import pytest

from chronosync.fine.gcc_phat import gcc_phat
from chronosync.mp4sync import (
    ChannelResult,
    FileReport,
    StreamInfo,
    fix_channels,
    reports_to_csv_rows,
)
from synthetic.delay import delay_samples
from synthetic.generators import speech_like

SR = 48_000


def test_fix_channels_removes_known_delays_exactly():
    base = speech_like(10 * SR, seed=0)
    ch0 = delay_samples(base, 1_223)  # wireless: +1223 samples late
    ch1 = delay_samples(base, 1_350)
    ch2 = base.copy()  # wired reference pair
    ch3 = base.copy()
    channels = [ch0, ch1, ch2, ch3]
    delays = [1_223.0, 1_350.0, 0.0, 0.0]

    fixed = fix_channels(channels, delays)
    assert fixed.shape[0] == 4
    # every channel aligns with the reference within one sample
    for i in (0, 1, 2, 3):
        res = gcc_phat(fixed[2], fixed[i], SR)
        assert res.success
        assert abs(res.delay_samples) < 1.0


def test_fix_channels_ignores_nan_delays():
    base = speech_like(5 * SR, seed=1)
    fixed = fix_channels([delay_samples(base, 500), base], [float("nan"), 0.0])
    assert fixed.shape == (2, len(base))


def test_fix_channels_normalizes_below_full_scale():
    base = speech_like(2 * SR, seed=2)
    fixed = fix_channels([base, base], [0.0, 0.0])
    assert float(np.max(np.abs(fixed))) <= 0.991  # 0.99 + float32 rounding


def test_channel_result_serialization_nan_to_none():
    ok = ChannelResult(
        stream=0, delay_samples=1222.8, delay_ms=25.475, confidence=0.8,
        drift_classification="constant_offset", drift_alpha_ppm=-1.5,
        coherence=0.9, duration_seconds=78.0,
    )
    d = ok.to_dict()
    assert d["delay_ms"] == pytest.approx(25.475)
    assert d["delay_samples"] == pytest.approx(1222.8)
    bad = ChannelResult(
        stream=1, delay_samples=float("nan"), delay_ms=float("nan"),
        confidence=0.0, drift_classification="none", drift_alpha_ppm=0.0,
        coherence=0.0, duration_seconds=3.0, warnings=["GCC failed"],
    )
    d = bad.to_dict()
    assert d["delay_samples"] is None and d["delay_ms"] is None


def test_file_report_serialization_round_shape():
    report = FileReport(
        file="x.MP4", reference_stream=2,
        channels=[
            ChannelResult(0, 1222.8, 25.475, 0.8, "constant_offset", -1.5, 0.9, 78.0),
            ChannelResult(2, 0.0, 0.0, 1.0, "reference", 0.0, 1.0, 78.0),
        ],
        verify_max_abs_ms=0.01, verify_ok=True,
    )
    d = report.to_dict()
    assert d["file"] == "x.MP4"
    assert d["reference_stream"] == 2
    assert len(d["channels"]) == 2
    assert d["verify_ok"] is True


def test_csv_rows_shape():
    report = FileReport(
        file="y.MP4", reference_stream=2,
        channels=[ChannelResult(0, 1000.0, 20.833, 0.7, "constant_offset", 0.1, 0.8, 10.0)],
    )
    rows = reports_to_csv_rows([report])
    assert rows[0][0] == "file"
    assert rows[1][0] == "y.MP4"
    assert rows[1][2] == "1000.000"


def test_stream_info_defaults():
    s = StreamInfo(index=1, audio_pos=0)
    assert s.codec == "unknown" and s.channels == 0
