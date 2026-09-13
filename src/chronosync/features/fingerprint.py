"""Constellation (landmark) audio fingerprinting (Layer 1).

Implements the classic "constellation" idea (a la Wang 2003): STFT ->
log-magnitude spectrogram -> 2-D peak picking -> landmark pairs inside a
target zone -> hash = f(freq1, freq2, time_delta) -> list of (hash, time).

This is a clean-room implementation of the published *idea* for internal
coarse matching. Note (ADR-007): the Wang / Haitsma-Kalker / Echoprint
fingerprinting methods may be patent-encumbered in some jurisdictions for
commercial products — evaluate separately before commercial use.

Direction (ADR-003): a fingerprint match yields
``offset = t_target - t_reference`` in canonical-rate samples (positive =
the event occurs later in the target).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage, signal

from chronosync.io.resampler import resample
from chronosync.models.audio import CANONICAL_SAMPLE_RATE

DEFAULT_FP_RATE = 11_025  # working sample rate for fingerprinting
DEFAULT_CHUNK_SECONDS = 300.0  # chunk size for long signals


@dataclass
class FingerprintConfig:
    """Fingerprint parameters (all configurable, documented)."""

    sample_rate: int = DEFAULT_FP_RATE  # working rate (audio is resampled to this)
    fft_size: int = 1024
    hop_size: int = 512  # 50% overlap
    window: str = "hann"
    min_peak_db: float = -45.0  # peak threshold relative to the spectrogram max
    peak_freq_width: int = 21  # local-max neighborhood: frequency bins
    peak_time_width: int = 11  # local-max neighborhood: frames
    min_freq_hz: float = 80.0
    max_freq_hz: float = 5_000.0
    delta_min: int = 1  # min landmark time delta (frames)
    delta_max: int = 100  # max landmark time delta (frames)
    fanout: int = 15  # max pairs per anchor


@dataclass
class Fingerprint:
    """``hashes``: (n, 2) int64 array of [hash, time_frame]."""

    hashes: np.ndarray  # (n, 2) int64: [hash, time_frame], sorted by frame
    sample_rate: int  # working rate of this fingerprint
    hop_size: int
    config: FingerprintConfig

    @property
    def frames_per_second(self) -> float:
        return self.sample_rate / self.hop_size

    def frame_to_canonical_samples(self, frame: int | float) -> float:
        """Frame index -> samples at the canonical 48 kHz rate."""
        return float(frame) * self.hop_size * (CANONICAL_SAMPLE_RATE / self.sample_rate)


@dataclass
class FingerprintMatch:
    """Histogram-vote result of matching two fingerprints."""

    offset_frames: float  # t_target - t_reference in fingerprint frames (sub-frame)
    offset_samples: float  # canonical-rate samples (ADR-003)
    offset_seconds: float
    votes: int  # histogram peak height
    matching_hashes: int  # hashes present in both fingerprints
    second_votes: int  # tallest histogram bin outside the peak neighborhood
    confidence: float  # in [0, 1]
    success: bool


def _spectrogram_peaks(
    work: np.ndarray, cfg: FingerprintConfig
) -> tuple[np.ndarray, np.ndarray]:
    """Log-magnitude spectrogram -> 2-D peak coordinates (frame, bin).

    The dB scale is ABSOLUTE: the input is unit-RMS normalized by the caller
    and the magnitudes are divided by the FFT size, so a full-energy frame
    peaks at ~0 dB and ``min_peak_db`` (default -45 dB) is comparable across
    chunks of the same signal AND across different files (gain invariance
    comes from the RMS normalization, not from a per-segment maximum).
    """
    _, _, zxx = signal.stft(
        work,
        fs=cfg.sample_rate,
        nperseg=cfg.fft_size,
        noverlap=cfg.fft_size - cfg.hop_size,
        window=cfg.window,
        boundary=None,
        padded=False,
    )
    # scipy.stft defaults to scaling='spectrum' (divides by sum(win)); undo
    # that and normalize by sqrt(sum(win^2)) so that a unit-RMS noise frame
    # peaks at ~0 dB — an absolute scale comparable across chunks and files.
    win = signal.get_window(cfg.window, cfg.fft_size, fftbins=False)
    scale = float(np.sum(win)) / np.sqrt(float(np.sum(win * win)))
    mag = np.abs(zxx) * scale
    logmag = 20.0 * np.log10(np.maximum(mag, 1e-12))

    f_bins = np.fft.rfftfreq(cfg.fft_size, d=1.0 / cfg.sample_rate)
    lo = int(np.searchsorted(f_bins, cfg.min_freq_hz))
    hi = int(np.searchsorted(f_bins, cfg.max_freq_hz)) + 1
    band = logmag[lo:hi, :]

    local_max = ndimage.maximum_filter(
        band, size=(cfg.peak_freq_width, cfg.peak_time_width), mode="constant"
    )
    mask = (band == local_max) & (band >= cfg.min_peak_db)
    f_idx, t_idx = np.nonzero(mask)
    return t_idx, f_idx + lo  # absolute bin indices


def _hash_value(f1: int, f2: int, dt: int) -> int:
    # 10 bits per frequency bin, 9 bits for the time delta.
    return (int(f1) << 21) | (int(f2) << 10) | int(dt)


def _landmarks_once(work: np.ndarray, cfg: FingerprintConfig) -> np.ndarray:
    """Landmark pairs of one signal segment -> (n, 2) [hash, frame]."""
    t_idx, f_idx = _spectrogram_peaks(work, cfg)
    if t_idx.size < 2:
        return np.zeros((0, 2), dtype=np.int64)
    order = np.argsort(t_idx, kind="stable")
    t_idx, f_idx = t_idx[order], f_idx[order]

    hashes: list[tuple[int, int]] = []
    n_peaks = t_idx.size
    # Simple linear scan with a moving window (fanout bounded by delta band).
    for i in range(n_peaks):
        t_i = int(t_idx[i])
        f_i = int(f_idx[i])
        count = 0
        j = i + 1
        while j < n_peaks and count < cfg.fanout:
            dt = int(t_idx[j]) - t_i
            if dt > cfg.delta_max:
                break
            if dt >= cfg.delta_min:
                hashes.append((_hash_value(f_i, int(f_idx[j]), dt), t_i))
                count += 1
            j += 1
    if not hashes:
        return np.zeros((0, 2), dtype=np.int64)
    arr = np.asarray(hashes, dtype=np.int64)
    return arr[np.argsort(arr[:, 1], kind="stable")]


def compute_fingerprint(
    x: np.ndarray,
    sample_rate: float,
    config: FingerprintConfig | None = None,
    chunk_seconds: float | None = DEFAULT_CHUNK_SECONDS,
) -> Fingerprint:
    """Compute a constellation fingerprint of a 1-D mono signal.

    The signal is resampled to the working rate (default 11025 Hz). When
    ``chunk_seconds`` is set and the signal exceeds the chunk length, the
    fingerprint is computed on overlapping chunks (landmark pairs that cross
    chunk boundaries are preserved by a ``delta_max``-frame overlap).
    """
    cfg = config if config is not None else FingerprintConfig()
    x = np.asarray(x, dtype=np.float64)
    if float(sample_rate) != float(cfg.sample_rate):
        work = resample(x, sample_rate, cfg.sample_rate)
    else:
        work = x
    # Unit-RMS normalization makes the dB peak threshold absolute (see
    # _spectrogram_peaks): identical chunks yield identical fingerprints,
    # and the fingerprint is gain-invariant across files.
    work = work - work.mean()
    rms = float(np.sqrt(np.mean(work * work)))
    if rms > 1e-12:
        work = work / rms

    if chunk_seconds is None:
        return Fingerprint(_landmarks_once(work, cfg), cfg.sample_rate, cfg.hop_size, cfg)

    chunk_len = int(float(chunk_seconds) * cfg.sample_rate)
    chunk_len = (chunk_len // cfg.hop_size) * cfg.hop_size
    if chunk_len < cfg.fft_size or work.size <= chunk_len + cfg.hop_size * (cfg.delta_max + 2):
        return Fingerprint(_landmarks_once(work, cfg), cfg.sample_rate, cfg.hop_size, cfg)

    overlap_frames = cfg.delta_max + 2
    overlap_samples = overlap_frames * cfg.hop_size
    core_frames = chunk_len // cfg.hop_size
    # Peak picking needs +-peak_time_width//2 frames of REAL context around
    # each candidate, so every chunk is processed with a context margin and
    # only the core anchors are kept (chunked == single-shot exactly).
    ctx_frames = cfg.peak_time_width // 2
    parts: list[np.ndarray] = []
    start = 0
    frame_offset = 0
    while start < work.size:
        end = min(start + chunk_len + overlap_samples, work.size)
        seg_start = max(0, start - ctx_frames * cfg.hop_size)
        seg_end = min(work.size, end + ctx_frames * cfg.hop_size)
        seg = work[seg_start:seg_end]
        local = _landmarks_once(seg, cfg)
        if local.size:
            global_frames = local[:, 1] + seg_start // cfg.hop_size
            if end < work.size:
                keep = (global_frames >= frame_offset) & (
                    global_frames < frame_offset + core_frames
                )
            else:  # final chunk: everything from the core start onwards
                keep = global_frames >= frame_offset
            local = local[keep]
            if local.size:
                local = local.copy()
                local[:, 1] += seg_start // cfg.hop_size
                parts.append(local)
        if end >= work.size:
            break
        start += chunk_len
        frame_offset += core_frames
    if not parts:
        return Fingerprint(np.zeros((0, 2), dtype=np.int64), cfg.sample_rate, cfg.hop_size, cfg)
    return Fingerprint(np.concatenate(parts), cfg.sample_rate, cfg.hop_size, cfg)


def _frames_for(n_samples: int, cfg: FingerprintConfig) -> int:
    if n_samples < cfg.fft_size:
        return 0
    return 1 + (n_samples - cfg.fft_size) // cfg.hop_size


def _group_by_hash(fp: Fingerprint) -> dict[int, np.ndarray]:
    order = np.argsort(fp.hashes[:, 0], kind="stable")
    hashes = fp.hashes[order]
    uniq, starts = np.unique(hashes[:, 0], return_index=True)
    ends = np.append(starts[1:], hashes.shape[0])
    return {int(h): hashes[s:e, 1] for h, s, e in zip(uniq, starts, ends)}


def match_fingerprints(
    fp_a: Fingerprint,
    fp_b: Fingerprint,
    max_lag_seconds: float | None = None,
    exclusion_frames: int = 10,
    min_votes: int = 5,
) -> FingerprintMatch:
    """Vote histogram over ``offset = t_b - t_a`` (frames, ADR-003).

    Args:
        fp_a: fingerprint of the REFERENCE.
        fp_b: fingerprint of the TARGET.
        max_lag_seconds: only count offsets within +/- this bound.
        exclusion_frames: neighborhood around the best bin excluded when
            measuring the second-best bin.
        min_votes: vote-count gate folded into the confidence (a peak with
            fewer votes is not a trustworthy match even when locally sharp).
    """
    a = _group_by_hash(fp_a)
    b = _group_by_hash(fp_b)
    common = set(a) & set(b)
    matching_hashes = len(common)
    if matching_hashes == 0:
        return FingerprintMatch(
            offset_frames=0,
            offset_samples=0.0,
            offset_seconds=0.0,
            votes=0,
            matching_hashes=0,
            second_votes=0,
            confidence=0.0,
            success=False,
        )

    max_lag_frames = (
        None
        if max_lag_seconds is None
        else int(round(max_lag_seconds * fp_a.frames_per_second))
    )
    offsets: list[np.ndarray] = []
    for h in common:
        d = (b[h][:, None] - a[h]).ravel()
        if max_lag_frames is not None:
            d = d[np.abs(d) <= max_lag_frames]
        if d.size:
            offsets.append(d)
    if not offsets:
        return FingerprintMatch(
            offset_frames=0, offset_samples=0.0, offset_seconds=0.0, votes=0,
            matching_hashes=matching_hashes, second_votes=0, confidence=0.0,
            success=False,
        )

    offs = np.concatenate(offsets)
    lo, hi = int(offs.min()), int(offs.max())
    hist = np.bincount(offs - lo, minlength=hi - lo + 1)
    best_rel = int(np.argmax(hist))
    votes = int(hist[best_rel])
    masked = hist.copy()
    masked[max(0, best_rel - exclusion_frames) : best_rel + exclusion_frames + 1] = 0
    second_votes = int(masked.max()) if masked.size else 0

    # Sub-frame refinement: parabolic fit over the three histogram bins
    # around the peak (the vote histogram is locally peak-shaped).
    delta = 0.0
    if 1 <= best_rel <= hist.size - 2:
        y0, y1, y2 = float(hist[best_rel - 1]), float(hist[best_rel]), float(hist[best_rel + 1])
        denom = y0 - 2.0 * y1 + y2
        if abs(denom) > 1e-12:
            delta = float(np.clip(0.5 * (y0 - y2) / denom, -0.5, 0.5))

    offset_frames = float(lo + best_rel) + delta
    # Confidence: fraction of matching hashes that vote for the best offset,
    # tempered by the best/second-best ratio (ambiguity) and gated by the
    # absolute vote count (a 3-vote peak among 10 hash collisions is noise).
    vote_fraction = votes / max(1, sum(len(b[h]) * len(a[h]) for h in common))
    vote_score = float(np.clip((vote_fraction - 0.15) / 0.45, 0.0, 1.0))
    ratio = votes / max(second_votes, 1)
    ratio_score = (ratio - 1.0) / (ratio - 1.0 + 0.5) if ratio >= 1.0 else 0.0
    votes_gate = min(1.0, votes / max(min_votes, 1))
    confidence = float(
        np.clip(0.7 * vote_score + 0.3 * ratio_score, 0.0, 1.0) * votes_gate
    )

    return FingerprintMatch(
        offset_frames=offset_frames,
        offset_samples=fp_a.frame_to_canonical_samples(offset_frames),
        offset_seconds=offset_frames / fp_a.frames_per_second,
        votes=votes,
        matching_hashes=matching_hashes,
        second_votes=second_votes,
        confidence=confidence,
        success=votes >= 3,
    )
