"""Unit tests for overlap / segment detection (Phase 5)."""

from __future__ import annotations

import pytest

from chronosync.models.timemap import (
    ConstantOffsetTimeMap,
    IdentityTimeMap,
    LinearTimeMap,
    PiecewiseLinearTimeMap,
)
from chronosync.overlap import (
    Segment,
    TrackContent,
    TrackSpan,
    content_intervals,
    pair_overlap,
    spans_from_timemap,
)


def _span(l0, l1, offset=0.0):
    return TrackSpan(l0, l1, ConstantOffsetTimeMap(offset_seconds=offset))


def _track(name, spans_or_map, duration=None):
    if isinstance(spans_or_map, TrackContent):
        return spans_or_map
    if duration is not None:
        return TrackContent.from_timemap(name, spans_or_map, duration)
    return TrackContent.from_spans(name, spans_or_map)


def test_content_intervals_identity_and_constant():
    assert content_intervals(TrackContent.from_timemap("A", IdentityTimeMap(), 60.0)) == [(0.0, 60.0)]
    tm = ConstantOffsetTimeMap(offset_seconds=2.0)
    assert content_intervals(TrackContent.from_timemap("A", tm, 60.0)) == [(2.0, 62.0)]


def test_content_intervals_from_bare_timemap():
    assert content_intervals(IdentityTimeMap(), 60.0) == [(0.0, 60.0)]


def test_content_intervals_excludes_flat_spans():
    # local 0..10 -> global 0..10; flat local 10..10.1 -> global 10 (drop);
    # local 10.1..20 -> global 10..19.9. The DROP is a hole in the track's
    # LOCAL recording: its remaining content still covers every global time,
    # so the content interval is continuous.
    tm = PiecewiseLinearTimeMap(
        knots=((0.0, 0.0), (10.0, 10.0), (10.1, 10.0), (20.0, 19.9))
    )
    assert content_intervals(tm, 20.0) == [(0.0, 19.9)]
    spans = spans_from_timemap(tm, 20.0)
    assert len(spans) == 2  # the flat (drop) span is not a recording


def test_content_intervals_track_with_recording_gaps():
    # Track B recorded 0-10, 20-40, 50-60 min of a continuous event.
    b = TrackContent.from_spans(
        "B",
        [_span(0.0, 600.0, offset=0.0),
         _span(600.0, 1800.0, offset=600.0),   # local 10-30 min -> global 20-40
         _span(1800.0, 2400.0, offset=1200.0)],  # local 30-40 min -> global 50-60
    )
    assert content_intervals(b) == [(0.0, 600.0), (1200.0, 2400.0), (3000.0, 3600.0)]


def test_pair_overlap_produces_three_segments():
    # The prompt's official example: Track A 0-60 min; Track B records
    # 0-10, 20-40, 50-60 min -> THREE segments.
    ref = TrackContent.from_timemap("A", IdentityTimeMap(), 3600.0)
    tgt = TrackContent.from_spans(
        "B",
        [_span(0.0, 600.0, 0.0), _span(600.0, 1800.0, 600.0), _span(1800.0, 2400.0, 1200.0)],
    )
    segments = pair_overlap(ref, tgt)
    assert len(segments) == 3
    s1, s2, s3 = segments
    assert (s1.start_seconds, s1.end_seconds) == pytest.approx((0.0, 600.0))
    assert (s2.start_seconds, s2.end_seconds) == pytest.approx((1200.0, 2400.0))
    assert (s3.start_seconds, s3.end_seconds) == pytest.approx((3000.0, 3600.0))
    # target local ranges are continuous spans of B's own recording
    assert (s1.target_local_start, s1.target_local_end) == pytest.approx((0.0, 600.0))
    assert (s2.target_local_start, s2.target_local_end) == pytest.approx((600.0, 1800.0))
    assert (s3.target_local_start, s3.target_local_end) == pytest.approx((1800.0, 2400.0))


def test_pair_overlap_with_offsets_and_drift():
    ref = TrackContent.from_timemap("A", IdentityTimeMap(), 60.0)
    tgt = TrackContent.from_timemap(
        "B", LinearTimeMap.from_ppm(120.0, offset_seconds=2.0), 60.0
    )
    segments = pair_overlap(ref, tgt)
    assert len(segments) == 1
    s = segments[0]
    assert (s.start_seconds, s.end_seconds) == pytest.approx((2.0, 60.0))
    assert s.target_local_start == pytest.approx(0.0, abs=1e-6)
    assert s.target_local_end == pytest.approx(58.0 / (1 + 120e-6), abs=1e-4)


def test_pair_overlap_no_overlap():
    ref = TrackContent.from_timemap("A", IdentityTimeMap(), 10.0)
    tgt = TrackContent.from_timemap("B", ConstantOffsetTimeMap(100.0), 10.0)
    assert pair_overlap(ref, tgt) == []


def test_pair_overlap_partial_span_coverage():
    # B only covers global [100, 200] of A's [0, 300] -> one segment.
    ref = TrackContent.from_timemap("A", IdentityTimeMap(), 300.0)
    tgt = TrackContent.from_spans("B", [_span(0.0, 100.0, offset=100.0)])
    segments = pair_overlap(ref, tgt)
    assert len(segments) == 1
    s = segments[0]
    assert (s.start_seconds, s.end_seconds) == pytest.approx((100.0, 200.0))
    assert (s.target_local_start, s.target_local_end) == pytest.approx((0.0, 100.0))


def test_segment_is_a_dataclass_with_duration():
    s = Segment(0.0, 10.0, 0.0, 10.0, 1.0, 11.0)
    assert s.duration_seconds == 10.0
