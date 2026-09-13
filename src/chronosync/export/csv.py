"""CSV export of alignments (one row per track).

Columns: track, offset_samples, offset_seconds, confidence,
residual_samples, time_map_kind (+ time map parameters as JSON text).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from chronosync.models.alignment import TrackAlignment
from chronosync.models.timemap import TimeMap

_COLUMNS = [
    "track",
    "offset_samples",
    "offset_seconds",
    "confidence",
    "residual_samples",
    "time_map_kind",
    "time_map_json",
]


def write_csv(
    path: str | Path,
    tracks: list[TrackAlignment],
    time_maps: dict[str, TimeMap] | None = None,
) -> Path:
    """Write one row per track; the time map travels as a JSON text field."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    time_maps = time_maps or {}
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_COLUMNS)
        for track in tracks:
            tm = time_maps.get(track.track)
            writer.writerow(
                [
                    track.track,
                    f"{track.offset_samples:.3f}",
                    f"{track.offset_seconds:.6f}",
                    f"{track.confidence:.4f}",
                    (
                        f"{track.residual_samples:.3f}"
                        if track.residual_samples is not None
                        else ""
                    ),
                    (tm.kind if tm is not None else ""),
                    (json.dumps(tm.to_dict()) if tm is not None else ""),
                ]
            )
    return path
