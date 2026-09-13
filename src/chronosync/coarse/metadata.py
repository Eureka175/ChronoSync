"""Metadata-based coarse stage (Layer 2).

Honest scope: file metadata alone cannot produce a *sample* offset (BWF
timecode parsing is not implemented yet), so this stage never reports
``matched=True``. It provides:

* an overlap-feasibility gate and duration evidence;
* an optional **search prior** from file modification times
  (``prior = t_target_mtime - t_reference_mtime``) — useful when the files
  were written by the recording devices themselves.

The cascade uses the prior to narrow the fingerprint/envelope search.
"""

from __future__ import annotations

from chronosync.models.audio import AudioTrack
from chronosync.models.match import MatchResult


def metadata_match(
    ref_track: AudioTrack | None,
    tgt_track: AudioTrack | None,
    sample_rate: int = 48_000,
) -> MatchResult:
    """Build the metadata evidence / prior for a track pair (never matched)."""
    warnings: list[str] = []
    evidence: dict[str, float] = {}
    prior_samples: float | None = None

    if ref_track is not None:
        evidence["reference_duration_seconds"] = ref_track.duration_seconds
        evidence["reference_sample_rate"] = float(ref_track.sample_rate)
    if tgt_track is not None:
        evidence["target_duration_seconds"] = tgt_track.duration_seconds
        evidence["target_sample_rate"] = float(tgt_track.sample_rate)

    if ref_track is not None and tgt_track is not None:
        if ref_track.sample_rate != tgt_track.sample_rate:
            warnings.append(
                f"sample rates differ: {ref_track.sample_rate} vs {tgt_track.sample_rate} Hz"
            )
        # mtime prior: difference of the files' modification times as a guess
        # of the recording-start difference (copies/touches invalidate it).
        import os

        try:
            ref_mtime = os.path.getmtime(ref_track.path or "")
            tgt_mtime = os.path.getmtime(tgt_track.path or "")
        except OSError:
            ref_mtime = tgt_mtime = None
        if ref_mtime is not None and tgt_mtime is not None:
            prior_seconds = tgt_mtime - ref_mtime
            prior_samples = prior_seconds * sample_rate
            evidence["mtime_prior_seconds"] = prior_seconds
            if abs(prior_seconds) > max(
                ref_track.duration_seconds, tgt_track.duration_seconds
            ):
                warnings.append(
                    "mtime prior exceeds both durations (copied/edited files?) "
                    "— the prior is unreliable"
                )
        else:
            warnings.append("no usable mtime prior (file timestamps unavailable)")

    return MatchResult(
        matched=False,
        offset_samples=prior_samples,
        offset_seconds=(prior_samples / sample_rate if prior_samples is not None else None),
        confidence=0.0,
        method="metadata",
        evidence=evidence,
        warnings=warnings,
    )


def overlap_estimate(
    ref_duration_s: float, tgt_duration_s: float, offset_seconds: float
) -> tuple[float, float] | None:
    """Overlap region ``(start_s, end_s)`` on the REFERENCE timeline.

    Returns ``None`` when the offset admits no overlap at all.
    """
    start = max(0.0, -offset_seconds)
    end = min(ref_duration_s, tgt_duration_s - offset_seconds)
    if end <= start:
        return None
    return (start, end)
