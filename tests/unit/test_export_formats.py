"""Unit tests for JSON / CSV export."""

from __future__ import annotations

import csv
import json
import math

import pytest

from chronosync.export import write_csv, write_json
from chronosync.models.alignment import TrackAlignment
from chronosync.models.timemap import ConstantOffsetTimeMap, LinearTimeMap


def _tracks():
    return [
        TrackAlignment("A", 0.0, 0.0, 1.0),
        TrackAlignment("B", 1_000.0, 1_000 / 48_000, 0.93, residual_samples=2.5),
    ]


def test_write_json_sanitizes_and_round_trips(tmp_path):
    payload = {
        "reference": "A",
        "tracks": [
            {"track": "A", "offset_samples": 0.0, "nan": float("nan")},
            {"track": "B", "offset_samples": float("inf")},
        ],
        "warnings": [],
    }
    path = write_json(tmp_path / "out.json", payload)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tracks"][0]["nan"] is None
    assert data["tracks"][1]["offset_samples"] is None
    assert data["reference"] == "A"


def test_write_json_utf8(tmp_path):
    path = write_json(tmp_path / "o.json", {"track": "轨道 1"})
    assert "轨道 1" in path.read_text(encoding="utf-8")


def test_write_csv_rows_and_time_map_column(tmp_path):
    path = write_csv(
        tmp_path / "align.csv",
        _tracks(),
        {
            "A": ConstantOffsetTimeMap(0.0),
            "B": LinearTimeMap(scale=1.0001, offset_seconds=0.02),
        },
    )
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    header, a_row, b_row = rows
    assert header[0] == "track"
    assert a_row[0] == "A" and a_row[5] == "constant_offset"
    assert b_row[0] == "B" and b_row[5] == "linear"
    tm = json.loads(b_row[6])
    assert tm["kind"] == "linear"
    assert tm["scale"] == pytest.approx(1.0001)
