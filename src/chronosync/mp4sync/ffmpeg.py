"""ffmpeg/ffprobe subprocess wrappers for the MP4 channel-sync pipeline.

ffmpeg is the ONLY external tool dependency of this module (any modern
build works); all audio math is ChronoSync's own. ffmpeg is used only to
demux the container (exact PCM copies, no resampling) and to remux the
original video with the corrected mono streams.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StreamInfo:
    """One audio stream as seen by ffprobe."""

    index: int  # container stream index (video is 0, audio starts at 1)
    audio_pos: int  # 0-based audio position (0:a:N)
    codec: str = "unknown"
    channels: int = 0
    start_time: float | None = None  # container presentation time of sample 0 (s)
    duration: float | None = None


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} not found on PATH; install FFmpeg first")


def probe_audio_streams(path: str | Path) -> list[StreamInfo]:
    """Enumerate the audio streams of a media file via ffprobe.

    ``start_time`` is the container presentation time of the stream's first
    sample; different muxers/versions may write edit lists that shift it
    (measured: ffmpeg 6 on Linux wrote a 305-sample offset where ffmpeg 8 on
    Windows wrote 0). Callers must account for it — see
    :func:`chronosync.mp4sync.measure_file`.
    """
    require_ffmpeg()
    out = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,channels,start_time,duration",
            "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    streams = []
    audio_pos = 0
    for s in data.get("streams", []):
        if s.get("codec_type") != "audio":
            continue
        streams.append(
            StreamInfo(
                index=int(s["index"]),
                audio_pos=audio_pos,
                codec=str(s.get("codec_name", "unknown")),
                channels=int(s.get("channels", 0)),
                start_time=_opt_float(s.get("start_time")),
                duration=_opt_float(s.get("duration")),
            )
        )
        audio_pos += 1
    return streams


def _opt_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_stream(
    path: str | Path,
    stream: StreamInfo,
    out_wav: str | Path,
    limit_seconds: float | None = None,
) -> Path:
    """Exact PCM copy of one audio stream to a WAV (no resampling).

    ``-ignore_editlist 1`` is deliberate: edit lists (which some muxers write
    to align audio to video) would otherwise TRIM the head of the decoded
    stream on some ffmpeg versions, silently biasing every delay measurement.
    We want the raw sample stream; container offsets are reported separately
    via :attr:`StreamInfo.start_time`.
    """
    require_ffmpeg()
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-ignore_editlist", "1",
        "-i", str(path),
        "-map", f"0:a:{stream.audio_pos}",
    ]
    if limit_seconds:
        cmd += ["-t", str(limit_seconds)]
    cmd += ["-f", "wav", "-acodec", "pcm_s24le", str(out_wav)]
    subprocess.run(cmd, check=True, capture_output=True)
    return Path(out_wav)


def remux_video_with_mono_audio(
    src: str | Path, mono_wavs: list[Path], out: str | Path
) -> Path:
    """Mux the ORIGINAL video with corrected mono streams (layout preserved).

    Output has the same structure as the source: video stream(s) copied
    losslessly (when present) + one PCM audio stream per corrected WAV.
    """
    require_ffmpeg()
    has_video = any(
        s.get("codec_type") == "video"
        for s in _probe_streams(src)
    )
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(src)]
    for wav in mono_wavs:
        cmd += ["-i", str(wav)]
    if has_video:
        cmd += ["-map", "0:v:0"]
    for i in range(len(mono_wavs)):
        cmd += ["-map", f"{i + 1}:a:0", f"-c:a:{i}", "pcm_s24le"]
    cmd += ["-map_metadata", "0", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return Path(out)


def _probe_streams(path: str | Path) -> list[dict]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.stdout).get("streams", [])
