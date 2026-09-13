"""Overlap segment models (Phase 5).

A ``Segment`` is one contiguous region of the unified timeline where two
tracks share content. The key distinction (project requirement): "same
timeline" is NOT the same as "same file duration" — a track that recorded
0-10 / 20-40 / 50-60 min produces THREE segments against a continuous track.

Tracks with recording gaps are modeled as a list of ``TrackSpan``: each span
is a contiguous stretch of the track's local recording plus the affine map
that places it on the global timeline. (A gap cannot be expressed by a
single monotonic local->global function without inventing content, so the
honest model is span-by-span.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chronosync.models.timemap import (
    ConstantOffsetTimeMap,
    LinearTimeMap,
    PiecewiseLinearTimeMap,
    TimeMap,
)


@dataclass(frozen=True)
class Segment:
    """One contiguous overlap region between two tracks.

    All times are seconds on the GLOBAL timeline (ADR-005); the local ranges
    give the corresponding spans inside each track's own recording.
    """

    start_seconds: float  # global timeline
    end_seconds: float
    reference_local_start: float | None  # None when no reference track given
    reference_local_end: float | None
    target_local_start: float
    target_local_end: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds


@dataclass(frozen=True)
class TrackSpan:
    """One contiguous recorded stretch: local range + its global placement.

    ``time_map`` maps this span's LOCAL seconds to GLOBAL seconds; it must be
    increasing over the span (identity/constant/linear are the normal cases).
    """

    local_start_seconds: float
    local_end_seconds: float
    time_map: TimeMap

    def global_range(self) -> tuple[float, float]:
        start = self.time_map.to_global(self.local_start_seconds)
        end = self.time_map.to_global(self.local_end_seconds)
        if end < start:  # defensive: inverted span maps nothing
            return (end, start)
        return (start, end)

    def to_local(self, global_seconds: float) -> float:
        return self.time_map.to_local(global_seconds)


@dataclass(frozen=True)
class TrackContent:
    """A track's content on the unified timeline (its spans)."""

    name: str
    spans: tuple[TrackSpan, ...] = field(default_factory=tuple)

    @classmethod
    def from_timemap(
        cls, name: str, time_map: TimeMap, duration_seconds: float
    ) -> "TrackContent":
        """Single-span track from a TimeMap (drops become gap-less spans)."""
        return cls(name=name, spans=(TrackSpan(0.0, duration_seconds, time_map),))

    @classmethod
    def from_spans(cls, name: str, spans: list[TrackSpan]) -> "TrackContent":
        return cls(name=name, spans=tuple(spans))


def spans_from_timemap(
    time_map: TimeMap, duration_seconds: float
) -> list[TrackSpan]:
    """Convert a (piecewise) TimeMap into recorded spans.

    Flat spans (dropped content) are excluded; each remaining knot segment
    becomes one ``TrackSpan`` with an affine ``LinearTimeMap``.
    """
    if not isinstance(time_map, PiecewiseLinearTimeMap):
        return [TrackSpan(0.0, duration_seconds, time_map)]
    spans: list[TrackSpan] = []
    knots = list(time_map.knots)
    if knots[0][0] > 0.0:
        knots.insert(0, (0.0, time_map.to_global(0.0)))
    if knots[-1][0] < duration_seconds:
        knots.append((duration_seconds, time_map.to_global(duration_seconds)))
    for (l0, g0), (l1, g1) in zip(knots, knots[1:]):
        t0, t1 = max(l0, 0.0), min(l1, duration_seconds)
        if t1 <= t0:
            continue
        seg_len = l1 - l0
        if seg_len <= 0.0:  # vertical knot pair: no recording here
            continue
        if g1 - g0 < 1e-9:  # flat span: dropped content, not a recording
            continue
        scale = (g1 - g0) / seg_len
        offset = g0 - scale * l0
        spans.append(
            TrackSpan(t0, t1, LinearTimeMap(scale=scale, offset_seconds=offset))
        )
    return spans
