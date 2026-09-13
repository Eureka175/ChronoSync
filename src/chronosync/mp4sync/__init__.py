"""MP4 multi-channel wireless-mic delay sync (dedicated pipeline).

Entry points:

* :func:`chronosync.mp4sync.measure_file` — per-file per-stream delay
* :func:`chronosync.mp4sync.process_file` — measure + fix + remux + verify
* CLI: ``chronosync mp4-sync ...``

Only external dependency: ffmpeg/ffprobe on PATH (demux/remux only).
"""

from __future__ import annotations

from .core import (
    ChannelResult,
    FileReport,
    fix_channels,
    measure_file,
    measure_stream,
    process_file,
    reports_to_csv_rows,
)
from .ffmpeg import StreamInfo, probe_audio_streams, require_ffmpeg

__all__ = [
    "ChannelResult",
    "FileReport",
    "StreamInfo",
    "fix_channels",
    "measure_file",
    "measure_stream",
    "probe_audio_streams",
    "process_file",
    "reports_to_csv_rows",
    "require_ffmpeg",
]
