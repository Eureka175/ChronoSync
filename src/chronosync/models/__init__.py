"""Core data models of ChronoSync.

All cross-module data exchange happens through these dataclasses so that the
project-wide offset convention (ADR-003) and TimeMap abstraction (ADR-005)
are enforced in one place.
"""

from __future__ import annotations

from .alignment import AlignmentEdge, AlignmentGraph, TrackAlignment
from .audio import (
    CANONICAL_DTYPE,
    CANONICAL_SAMPLE_RATE,
    AudioTrack,
    DecodedAudio,
)
from .drift import DriftModel, OffsetMeasurement
from .match import MatchResult
from .timemap import (
    ConstantOffsetTimeMap,
    IdentityTimeMap,
    LinearTimeMap,
    PiecewiseLinearTimeMap,
    TimeMap,
)

__all__ = [
    "AlignmentEdge",
    "AlignmentGraph",
    "TrackAlignment",
    "AudioTrack",
    "DecodedAudio",
    "CANONICAL_DTYPE",
    "CANONICAL_SAMPLE_RATE",
    "DriftModel",
    "OffsetMeasurement",
    "MatchResult",
    "ConstantOffsetTimeMap",
    "IdentityTimeMap",
    "LinearTimeMap",
    "PiecewiseLinearTimeMap",
    "TimeMap",
]
