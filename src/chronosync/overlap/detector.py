"""Overlap / segment detection (Phase 5).

The content of a track on the unified timeline is the union of its spans'
global images. Intersecting two tracks' content intervals yields the overlap
segments; a track that recorded 0-10 / 20-40 / 50-60 min against a
continuous one therefore yields three segments.
"""

from __future__ import annotations

from chronosync.models.timemap import TimeMap

from .segments import Segment, TrackContent, TrackSpan, spans_from_timemap


def content_intervals(
    track: TrackContent | TimeMap, duration_seconds: float | None = None
) -> list[tuple[float, float]]:
    """Global-time intervals ``[start, end)`` where the track HAS content.

    Accepts either a :class:`TrackContent` (spans) or a bare TimeMap with a
    duration (converted via :func:`spans_from_timemap`; flat spans/drops are
    excluded).
    """
    if isinstance(track, TrackContent):
        spans = track.spans
    else:
        assert duration_seconds is not None, "duration required for a bare TimeMap"
        spans = spans_from_timemap(track, duration_seconds)
    intervals = [s.global_range() for s in spans]
    return _merge(intervals)


def _merge(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge touching/overlapping intervals (sorted output)."""
    if not intervals:
        return []
    out = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def pair_overlap(
    reference: TrackContent, target: TrackContent
) -> list[Segment]:
    """All contiguous overlap regions between two tracks.

    The local fields give each track's own recording range for the overlap
    (the span whose global image contains the overlap is unique because
    spans of one track never overlap).
    """
    ref_intervals = content_intervals(reference)
    tgt_intervals = content_intervals(target)
    segments: list[Segment] = []
    for r0, r1 in ref_intervals:
        for t0, t1 in tgt_intervals:
            s, e = max(r0, t0), min(r1, t1)
            if e <= s:
                continue
            ref_span = _span_covering(reference, s)
            tgt_span = _span_covering(target, s)
            segments.append(
                Segment(
                    start_seconds=s,
                    end_seconds=e,
                    reference_local_start=(
                        ref_span.to_local(s) if ref_span else None
                    ),
                    reference_local_end=(
                        ref_span.to_local(e) if ref_span else None
                    ),
                    target_local_start=tgt_span.to_local(s),
                    target_local_end=tgt_span.to_local(e),
                )
            )
    return segments


def _span_covering(track: TrackContent, global_seconds: float) -> TrackSpan | None:
    for span in track.spans:
        g0, g1 = span.global_range()
        if g0 - 1e-9 <= global_seconds <= g1 + 1e-9:
            return span
    return None
