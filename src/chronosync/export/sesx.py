"""Adobe Audition SESX session export (non-destructive timeline).

Format facts (see docs/research/notes/sesx_format.md, community reverse
engineering — Adobe ships no public schema):

* plain XML, no checksum/signature; hand-written files open in Audition
  (validated by the MIT ``outhud`` converter in Audition 2025);
* ALL time fields (``startPoint``/``endPoint``/``sourceInPoint``/
  ``sourceOutPoint``/``duration``) are INTEGER SAMPLE COUNTS at the session
  sample rate;
* a track's clips reference external WAV files through ``<file id>`` entries
  (``mediaHandler="AmioWav"``); playback is NON-DESTRUCTIVE.

Fidelity rules (honest, documented):

* identity / constant-offset TimeMaps  -> one exact clip per file;
* linear drift                        -> stair-step clips of configurable
  granularity: Audition clips cannot change playback rate, so continuous
  drift is approximated by piecewise-CONSTANT placement (gaps/overlaps of up
  to ``ppm * chunk_seconds`` samples per chunk). For sample-exact drift
  correction use ``chronosync.drift.correct_track`` (SoXR rendering);
* piecewise maps (discontinuities)    -> one clip per knot interval; flat
  spans become timeline gaps (lost content is NOT invented).

Clip placement follows ADR-003/ADR-005: the TimeMap maps the track's LOCAL
timeline to the GLOBAL session timeline in seconds; the reference track sits
at offset 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from chronosync.models.timemap import PiecewiseLinearTimeMap, TimeMap

#: Conservative-but-current version pair (opens in CS6 through CC 2025).
SESX_VERSION = "1.9"
APP_VERSION = "25.2"
APP_BUILD = "chronosync"

#: Number of local-timeline samples per stair-step chunk for linear maps.
DEFAULT_CHUNK_SECONDS = 10.0


@dataclass
class SesxClip:
    """One clip placed on the session timeline (all times in samples)."""

    name: str
    source_path: str
    start_samples: int  # timeline position (session sample rate)
    source_in_samples: int  # playback offset inside the source file
    source_out_samples: int  # exclusive playback end inside the source file
    source_sample_rate: int

    @property
    def length_samples(self) -> int:
        return self.source_out_samples - self.source_in_samples

    @property
    def end_samples(self) -> int:
        return self.start_samples + self.length_samples


@dataclass
class SesxTrack:
    """One session track (mono source files become mono clips)."""

    name: str
    clips: list[SesxClip] = field(default_factory=list)


# --------------------------------------------------------------- timeline


def clips_from_timemap(
    source_path: str | Path,
    track_name: str,
    source_duration_samples: int,
    source_sample_rate: int,
    time_map: TimeMap,
    session_sample_rate: int = 48_000,
    chunk_seconds: float = DEFAULT_CHUNK_SECONDS,
) -> SesxTrack:
    """Convert a TimeMap into SESX clips (see module docstring for fidelity).

    Content mapping to negative global times (before the session origin) is
    trimmed: the clip starts at 0 and its source in-point is advanced.
    """
    if isinstance(time_map, PiecewiseLinearTimeMap):
        track = _clips_piecewise(
            source_path, track_name, source_duration_samples, source_sample_rate,
            time_map, session_sample_rate,
        )
        return _trim_negative_starts(track)

    # identity / constant offset / linear: single clip when identity-like.
    if time_map.is_identity() or _is_constant(time_map):
        track = SesxTrack(
            name=track_name,
            clips=[
                SesxClip(
                    name=track_name,
                    source_path=str(source_path),
                    start_samples=int(round(time_map.to_global(0.0) * session_sample_rate)),
                    source_in_samples=0,
                    source_out_samples=source_duration_samples,
                    source_sample_rate=source_sample_rate,
                )
            ],
        )
        return _trim_negative_starts(track)

    # Linear drift: stair-step approximation.
    chunk = max(1, int(round(chunk_seconds * session_sample_rate)))
    clips: list[SesxClip] = []
    local = 0
    index = 0
    while local < source_duration_samples:
        end = min(local + chunk, source_duration_samples)
        start_g = int(round(time_map.to_global(local / session_sample_rate) * session_sample_rate))
        clips.append(
            SesxClip(
                name=f"{track_name} #{index + 1}",
                source_path=str(source_path),
                start_samples=start_g,
                source_in_samples=local,
                source_out_samples=end,
                source_sample_rate=source_sample_rate,
            )
        )
        local = end
        index += 1
    return _trim_negative_starts(SesxTrack(name=track_name, clips=clips))


def _trim_negative_starts(track: SesxTrack) -> SesxTrack:
    """Clip content before the session origin: advance the source in-point."""
    trimmed: list[SesxClip] = []
    for clip in track.clips:
        if clip.start_samples < 0:
            skip = -clip.start_samples
            clip = SesxClip(
                name=clip.name,
                source_path=clip.source_path,
                start_samples=0,
                source_in_samples=clip.source_in_samples + skip,
                source_out_samples=clip.source_out_samples,
                source_sample_rate=clip.source_sample_rate,
            )
        if clip.source_out_samples > clip.source_in_samples:
            trimmed.append(clip)
    return SesxTrack(name=track.name, clips=trimmed)


def _is_constant(time_map: TimeMap) -> bool:
    from chronosync.models.timemap import ConstantOffsetTimeMap

    return isinstance(time_map, ConstantOffsetTimeMap)


def _clips_piecewise(
    source_path: str | Path,
    track_name: str,
    source_duration_samples: int,
    source_sample_rate: int,
    time_map: PiecewiseLinearTimeMap,
    session_sample_rate: int,
) -> SesxTrack:
    knots = list(time_map.knots)  # (local_s, global_s), sorted by local
    clips: list[SesxClip] = []
    index = 0
    for (l0, g0), (l1, g1) in zip(knots, knots[1:]):
        # Flat GLOBAL span: a drop gap / duplicated range — no timeline
        # extent, so no clip (content is skipped, never invented).
        if g1 - g0 < 1e-9 or l1 - l0 < 1e-9:
            continue
        in_s = int(round(l0 * source_sample_rate))
        out_s = int(round(l1 * source_sample_rate))
        out_s = min(max(out_s, in_s + 1), source_duration_samples)
        in_s = min(in_s, out_s - 1)
        clips.append(
            SesxClip(
                name=f"{track_name} #{index + 1}",
                source_path=str(source_path),
                start_samples=int(round(g0 * session_sample_rate)),
                source_in_samples=in_s,
                source_out_samples=out_s,
                source_sample_rate=source_sample_rate,
            )
        )
        index += 1
    return SesxTrack(name=track_name, clips=clips)


# ----------------------------------------------------------------- writer


def _bit_depth_for(session_bit_depth: int) -> str:
    return str(int(session_bit_depth))


def build_sesx_xml(
    tracks: list[SesxTrack],
    session_sample_rate: int,
    session_bit_depth: int = 32,
    audio_channel_type: str = "stereo",
    version: str = SESX_VERSION,
    app_version: str = APP_VERSION,
    app_build: str = APP_BUILD,
) -> str:
    """Render the SESX XML document as a string (UTF-8, no BOM)."""
    max_end = max((c.end_samples for t in tracks for c in t.clips), default=0)
    file_ids: dict[str, int] = {}
    for track in tracks:
        for clip in track.clips:
            if clip.source_path not in file_ids:
                file_ids[clip.source_path] = len(file_ids)

    root = ET.Element("sesx", {"version": version})
    session = ET.SubElement(
        root,
        "session",
        {
            "appBuild": app_build,
            "appVersion": app_version,
            "audioChannelType": audio_channel_type,
            "bitDepth": _bit_depth_for(session_bit_depth),
            "duration": str(int(max_end)),
            "sampleRate": str(int(session_sample_rate)),
        },
    )
    tracks_el = ET.SubElement(session, "tracks")

    master_id = 10000
    for idx, track in enumerate(tracks):
        track_el = ET.SubElement(
            tracks_el,
            "audioTrack",
            {
                "automationLaneOpenState": "false",
                "id": str(10001 + idx),
                "index": str(idx + 1),
                "select": "false",
                "visible": "true",
            },
        )
        tp = ET.SubElement(
            track_el,
            "trackParameters",
            {"trackHeight": "134", "trackHue": "0", "trackMinimized": "false"},
        )
        ET.SubElement(tp, "name").text = track.name
        tap = ET.SubElement(
            track_el,
            "trackAudioParameters",
            {
                "audioChannelType": audio_channel_type,
                "automationMode": "1",
                "monitoring": "false",
                "recordArmed": "false",
                "solo": "false",
                "soloSafe": "false",
            },
        )
        ET.SubElement(tap, "trackOutput", {"outputID": str(master_id), "type": "trackID"})

        for z, clip in enumerate(track.clips):
            ET.SubElement(
                track_el,
                "audioClip",
                {
                    "clipAutoCrossfade": "true",
                    "crossFadeHeadClipID": "-1",
                    "crossFadeTailClipID": "-1",
                    "endPoint": str(clip.end_samples),
                    "fileID": str(file_ids[clip.source_path]),
                    "hue": "-1",
                    "id": str(z),
                    "lockedInTime": "false",
                    "looped": "false",
                    "name": clip.name,
                    "offline": "false",
                    "select": "false",
                    "sourceInPoint": str(clip.source_in_samples),
                    "sourceOutPoint": str(clip.source_out_samples),
                    "startPoint": str(clip.start_samples),
                    "zOrder": str(z),
                },
            )

    master = ET.SubElement(
        tracks_el,
        "masterTrack",
        {
            "automationLaneOpenState": "false",
            "id": str(master_id),
            "index": str(len(tracks) + 1),
            "select": "false",
            "visible": "true",
        },
    )
    mtp = ET.SubElement(
        master,
        "trackParameters",
        {"trackHeight": "134", "trackHue": "-1", "trackMinimized": "false"},
    )
    ET.SubElement(mtp, "name").text = "Mix"
    mtap = ET.SubElement(
        master,
        "trackAudioParameters",
        {
            "audioChannelType": audio_channel_type,
            "automationMode": "1",
            "monitoring": "false",
            "recordArmed": "false",
            "solo": "false",
            "soloSafe": "true",
        },
    )
    ET.SubElement(mtap, "trackOutput", {"outputID": "1", "type": "hardwareOutput"})

    ss = ET.SubElement(session, "sessionState", {"ctiPosition": "0", "smpteStart": "0"})
    tfs = ET.SubElement(
        ss,
        "timeFormatState",
        {
            "beatsPerBar": "4",
            "beatsPerMinute": "120",
            "customFrameRate": "12",
            "linkToDefaultTimeSettings": "true",
            "noteLength": "4",
            "subdivisions": "16",
            "timeCodeDropFrame": "false",
            "timeCodeFrameRate": "30",
            "timeCodeNTSC": "false",
            "timeFormat": "timeFormatDecimal",
        },
    )
    ET.SubElement(
        ss,
        "mixingOptionState",
        {
            "defaultPanModeLogarithmic": "true",  # preserve unity gain on centered tracks
            "panPower": "-3",
            "playOverlappingClips": "false",
        },
    )

    files_el = ET.SubElement(root, "files")
    for source_path, file_id in file_ids.items():
        ET.SubElement(
            files_el,
            "file",
            {
                "absolutePath": source_path,
                "id": str(file_id),
                "mediaHandler": "AmioWav",
                "relativePath": Path(source_path).name,
            },
        )

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n'
        "<!DOCTYPE sesx>\n"
        + body
        + "\n"
    )


def write_sesx(
    path: str | Path,
    tracks: list[SesxTrack],
    session_sample_rate: int = 48_000,
    session_bit_depth: int = 32,
    audio_channel_type: str = "stereo",
) -> Path:
    """Write a session file to disk. Returns the written path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = build_sesx_xml(
        tracks,
        session_sample_rate=session_sample_rate,
        session_bit_depth=session_bit_depth,
        audio_channel_type=audio_channel_type,
    )
    path.write_text(xml, encoding="utf-8")
    return path
