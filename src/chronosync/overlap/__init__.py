"""Overlap / segment detection (Phase 5).

Distinguish "same timeline" from "same file duration": tracks whose
recordings contain gaps produce multiple overlap segments.
"""

from __future__ import annotations

from .detector import content_intervals, pair_overlap
from .segments import (
    Segment,
    TrackContent,
    TrackSpan,
    spans_from_timemap,
)

__all__ = [
    "Segment",
    "TrackContent",
    "TrackSpan",
    "content_intervals",
    "pair_overlap",
    "spans_from_timemap",
]
