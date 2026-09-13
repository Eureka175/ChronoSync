"""Clock-drift estimation and time-map construction (Layer 4).

Windowed GCC -> local offset(t) -> robust regression -> classification
(clock drift / discontinuity / bad measurement / no overlap) -> TimeMap.
"""

from __future__ import annotations

from .estimator import DriftConfig, DriftEstimate, SegmentFit, estimate_drift
from .regression import robust_linear_fit, weighted_linear_fit
from .timemap import correct_track
from .windows import WindowSchedule, overlap_center_range

__all__ = [
    "DriftConfig",
    "DriftEstimate",
    "SegmentFit",
    "WindowSchedule",
    "correct_track",
    "estimate_drift",
    "overlap_center_range",
    "robust_linear_fit",
    "weighted_linear_fit",
]
