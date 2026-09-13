"""Export (Phase 3+): non-destructive timeline representations.

* :mod:`chronosync.export.sesx` — Adobe Audition session (.sesx) writer
* :mod:`chronosync.export.json` — JSON alignment export
* :mod:`chronosync.export.csv` — CSV alignment export

The core output is ALWAYS offsets + time maps + segments; audio rendering
is optional and never the default.
"""

from __future__ import annotations

from .csv import write_csv
from .json import write_json
from .sesx import (
    SesxClip,
    SesxTrack,
    build_sesx_xml,
    clips_from_timemap,
    write_sesx,
)

__all__ = [
    "SesxClip",
    "SesxTrack",
    "build_sesx_xml",
    "clips_from_timemap",
    "write_csv",
    "write_json",
    "write_sesx",
]
