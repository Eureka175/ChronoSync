"""JSON export of alignments (offsets + time maps + segments).

Non-destructive timeline representation (ADR-005): offsets, TimeMap dicts
and overlap segments — never a re-render. NaN/Inf serialize to ``null``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from chronosync.models.alignment import TrackAlignment
from chronosync.models.timemap import TimeMap
from chronosync.overlap import Segment


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    return obj


def track_alignment_to_dict(
    track: TrackAlignment, time_map: TimeMap | None = None
) -> dict[str, Any]:
    """One track's placement (+ optional TimeMap) as a JSON-safe dict."""
    out: dict[str, Any] = {
        "track": track.track,
        "offset_samples": track.offset_samples,
        "offset_seconds": track.offset_seconds,
        "confidence": track.confidence,
        "residual_samples": track.residual_samples,
        "warnings": track.warnings,
    }
    if time_map is not None:
        out["time_map"] = time_map.to_dict()
    return out


def segment_to_dict(segment: Segment) -> dict[str, Any]:
    return {
        "start_seconds": segment.start_seconds,
        "end_seconds": segment.end_seconds,
        "duration_seconds": segment.duration_seconds,
        "reference_local_start": segment.reference_local_start,
        "reference_local_end": segment.reference_local_end,
        "target_local_start": segment.target_local_start,
        "target_local_end": segment.target_local_end,
    }


def write_json(
    path: str | Path,
    payload: Any,
) -> Path:
    """Write a JSON-safe payload to disk (NaN/Inf -> null)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_sanitize(payload), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path
