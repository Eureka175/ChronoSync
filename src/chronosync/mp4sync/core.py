"""MP4 multi-channel wireless-mic delay sync — core measurement and fix.

Real-world case (docs/mp4_wireless_delay_case.md): MP4 recordings with four
mono PCM audio streams; CH1/CH2 (wireless mics) arrive with a constant
per-file latency relative to CH3/CH4 (wired). Measured facts:

* within one file the delay is CONSTANT (same container = same clock; drift
  classification returns ``constant_offset``);
* the delay VARIES per file (measured 19.7-29.5 ms across five files) — every
  file must be measured individually;
* CH3/CH4 (wired) are mutually aligned to < 0.005 ms and serve as reference.

Units & direction (project-wide ADR-003):
``delay = t_stream - t_reference``; a POSITIVE delay means the stream arrives
LATER and must be moved EARLIER by that amount during correction.

Machine-readable handoff: :meth:`FileReport.to_dict` — the JSON schema the
consumer tool (e.g. an editor-side sync implementation) needs is documented
in docs/mp4_wireless_delay_case.md.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from chronosync.drift import DriftConfig, correct_track, estimate_drift
from chronosync.fine.gcc_phat import gcc_phat
from chronosync.io import read_canonical, write_wav
from chronosync.models.timemap import ConstantOffsetTimeMap
from chronosync.validation import mean_coherence

from .ffmpeg import (
    StreamInfo,
    extract_stream,
    probe_audio_streams,
    remux_video_with_mono_audio,
)

SR = 48_000

#: Drift check config: 16k-sample windows are short enough for speech content
#: and long enough to confirm "constant offset" vs real drift.
DRIFT_CONFIG = DriftConfig(
    window_samples=16_384,
    min_window_samples=16_384,
    min_windows=4,
    min_windows_per_segment=3,
)


@dataclass
class ChannelResult:
    """Measured delay of one stream against the reference (ADR-003)."""

    stream: int  # audio position (0 = CH1, ...)
    delay_samples: float  # d = t_stream - t_reference; nan when unmeasurable
    delay_ms: float  # delay_samples * 1000 / 48000
    confidence: float
    drift_classification: str
    drift_alpha_ppm: float
    coherence: float
    duration_seconds: float
    codec: str = "unknown"
    start_time_seconds: float | None = None  # container presentation start (info)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stream": self.stream,
            "delay_samples": (round(self.delay_samples, 3) if np.isfinite(self.delay_samples) else None),
            "delay_ms": (round(self.delay_ms, 4) if np.isfinite(self.delay_ms) else None),
            "confidence": round(self.confidence, 3),
            "drift": self.drift_classification,
            "alpha_ppm": round(self.drift_alpha_ppm, 3),
            "coherence": round(self.coherence, 3),
            "duration_seconds": round(self.duration_seconds, 2),
            "codec": self.codec,
            "start_time_seconds": self.start_time_seconds,
            "warnings": list(self.warnings),
        }


@dataclass
class FileReport:
    """Measurement (+ optional fix/verify) result for one file."""

    file: str
    reference_stream: int
    channels: list[ChannelResult]
    fixed_audio_wav: str | None = None
    fixed_mp4: str | None = None
    verify_max_abs_ms: float | None = None
    verify_ok: bool | None = None
    verify: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "reference_stream": self.reference_stream,
            "channels": [c.to_dict() for c in self.channels],
            "fixed_audio_wav": self.fixed_audio_wav,
            "fixed_mp4": self.fixed_mp4,
            "verify_max_abs_ms": (
                round(self.verify_max_abs_ms, 4)
                if self.verify_max_abs_ms is not None
                else None
            ),
            "verify_ok": self.verify_ok,
            "verify": self.verify,
        }


# --------------------------------------------------------------- measuring


def measure_stream(
    path: str | Path,
    stream: StreamInfo,
    reference_audio: np.ndarray,
    limit_seconds: float | None = None,
) -> ChannelResult:
    """Measure one stream's delay against the reference (GCC + drift check)."""
    warnings: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        wav = extract_stream(path, stream, Path(tmp) / "ch.wav", limit_seconds)
        audio = read_canonical(wav).mono_mix
    if not stream.codec.startswith("pcm"):
        warnings.append(
            f"lossy/non-PCM codec '{stream.codec}': encoder priming may bias "
            "the measured delay"
        )
    common = min(audio.size, reference_audio.size)
    ref = reference_audio[:common]
    tgt = audio[:common]

    gcc = gcc_phat(ref, tgt, SR)
    if not gcc.success:
        return ChannelResult(
            stream=stream.audio_pos,
            delay_samples=float("nan"), delay_ms=float("nan"),
            confidence=0.0, drift_classification="none", drift_alpha_ppm=0.0,
            coherence=0.0, duration_seconds=len(audio) / SR,
            codec=stream.codec, start_time_seconds=stream.start_time,
            warnings=[*gcc.warnings, "GCC failed"],
        )
    est = estimate_drift(ref, tgt, SR, coarse_offset_samples=gcc.delay_samples, config=DRIFT_CONFIG)
    if est.classification not in ("constant_offset", "clock_drift") and abs(est.model.alpha_ppm) > 20.0:
        warnings.append(f"unexpected drift {est.model.alpha_ppm:+.1f} ppm — check the file")
    return ChannelResult(
        stream=stream.audio_pos,
        delay_samples=float(gcc.delay_samples),
        delay_ms=float(gcc.delay_samples) * 1000.0 / SR,
        confidence=float(gcc.confidence),
        drift_classification=est.classification,
        drift_alpha_ppm=est.model.alpha_ppm,
        coherence=mean_coherence(ref, tgt, SR),
        duration_seconds=len(audio) / SR,
        codec=stream.codec,
        start_time_seconds=stream.start_time,
        warnings=warnings,
    )


def measure_file(
    path: str | Path,
    reference_stream: int = 2,
    limit_seconds: float | None = None,
) -> list[ChannelResult]:
    """Measure ALL audio streams of one file against the reference stream.

    Measurements are made in the CONTENT domain: extraction ignores muxer
    edit lists (``-ignore_editlist 1``). Streams of one recording must have
    equal decoded lengths — a per-stream head/tail trim (measured on some
    ffmpeg versions when remuxing multichannel PCM into MP4) biases every
    relative delay by the trimmed amount, so it is DETECTED and reported
    instead of being silently absorbed.
    """
    streams = probe_audio_streams(path)
    if reference_stream >= len(streams):
        raise ValueError(f"reference stream {reference_stream} not present")
    with tempfile.TemporaryDirectory() as tmp:
        ref_wav = extract_stream(
            path, streams[reference_stream], Path(tmp) / "ref.wav", limit_seconds
        )
        ref_audio = read_canonical(ref_wav).mono_mix
        results = []
        for i, stream in enumerate(streams):
            if i == reference_stream:
                results.append(
                    ChannelResult(
                        stream=i, delay_samples=0.0, delay_ms=0.0, confidence=1.0,
                        drift_classification="reference", drift_alpha_ppm=0.0,
                        coherence=1.0, duration_seconds=len(ref_audio) / SR,
                        codec=stream.codec, start_time_seconds=stream.start_time,
                    )
                )
            else:
                results.append(
                    measure_stream(path, stream, ref_audio, limit_seconds)
                )

    # Container integrity check: unequal decoded lengths across streams of the
    # same recording mean a per-stream trim/pad, which biases relative delays.
    lengths = [int(round(r.duration_seconds * SR)) for r in results]
    spread = max(lengths) - min(lengths)
    if spread > 2:
        detail = ", ".join(
            f"ch{r.stream}={n}" for r, n in zip(results, lengths)
        )
        for r in results:
            r.warnings.append(
                f"container anomaly: decoded stream lengths differ by {spread} "
                f"samples ({detail}); per-stream trims bias relative delays by "
                "the trimmed amount — verify against the source before trusting "
                "small offsets"
            )
    return results


# ------------------------------------------------------------------ fixing


def fix_channels(
    channels: list[np.ndarray], delays_samples: list[float]
) -> np.ndarray:
    """Sample-accurate delay removal: content shifted EARLIER by its delay.

    All channels are trimmed to the common aligned length; output is a
    float32 array of shape ``(channels, n)`` normalized below full scale.
    Unmeasurable streams (NaN delay) are left untouched.
    """
    shifted = []
    for audio, delay in zip(channels, delays_samples):
        if np.isnan(delay) or delay == 0.0:
            shifted.append(audio)
            continue
        tm = ConstantOffsetTimeMap(offset_seconds=-delay / SR)
        shifted.append(correct_track(audio, tm, SR).astype(np.float32))
    common = min(len(s) for s in shifted)
    out = np.stack([s[:common] for s in shifted]).astype(np.float32)
    peak = np.max(np.abs(out)) + 1e-12
    return out / peak * 0.99


def write_mono_wavs(out_dir: Path, stem: str, channels: np.ndarray) -> list[Path]:
    """One corrected mono WAV per channel (preserves the source layout)."""
    paths = []
    for i in range(channels.shape[0]):
        p = out_dir / f"{stem}_fixed_ch{i}.wav"
        write_wav(p, channels[i], SR, subtype="PCM_24")
        paths.append(p)
    return paths


def process_file(
    path: str | Path,
    reference_stream: int = 2,
    limit_seconds: float | None = None,
    fix: bool = False,
    out_dir: str | Path | None = None,
    remux: bool = False,
) -> FileReport:
    """Measure (+ optionally fix, remux and verify) one MP4 file."""
    path = Path(path)
    report = FileReport(
        file=path.name,
        reference_stream=reference_stream,
        channels=measure_file(path, reference_stream, limit_seconds),
    )
    if not fix:
        return report

    out_dir = Path(out_dir) if out_dir else path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem

    streams = probe_audio_streams(path)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        channels = []
        for stream in streams:
            wav = extract_stream(path, stream, tmp / f"c{stream.audio_pos}.wav", limit_seconds)
            channels.append(read_canonical(wav).mono_mix)

    delays = [c.delay_samples for c in report.channels]
    fixed = fix_channels(channels, delays)
    report.fixed_audio_wav = str(out_dir / f"{stem}_fixed_audio.wav")
    write_wav(report.fixed_audio_wav, fixed, SR, subtype="PCM_24")
    mono_wavs = write_mono_wavs(out_dir, stem, fixed)

    if remux:
        fixed_mp4 = out_dir / f"{stem}_fixed.MP4"
        remux_video_with_mono_audio(path, mono_wavs, fixed_mp4)
        report.fixed_mp4 = str(fixed_mp4)
        # VERIFY: re-measure the fixed MP4 with the SAME measurement path.
        verify = measure_file(fixed_mp4, reference_stream, limit_seconds)
        report.verify = [c.to_dict() for c in verify]
        finite = [c.delay_ms for c in verify if np.isfinite(c.delay_ms)]
        if finite:
            report.verify_max_abs_ms = max(abs(v) for v in finite)
            report.verify_ok = report.verify_max_abs_ms < 0.05
    return report


def reports_to_csv_rows(reports: list[FileReport]) -> list[list[str]]:
    rows = [["file", "stream", "delay_samples", "delay_ms", "confidence", "drift"]]
    for r in reports:
        for c in r.channels:
            rows.append(
                [
                    r.file, str(c.stream),
                    f"{c.delay_samples:.3f}" if np.isfinite(c.delay_samples) else "",
                    f"{c.delay_ms:.4f}" if np.isfinite(c.delay_ms) else "",
                    f"{c.confidence:.3f}", c.drift_classification,
                ]
            )
    return rows
