"""TimeMap construction and drift correction (Layer 4).

Correction uses high-quality ASYNCHRONOUS RESAMPLING (SoXR) — a clock
correction, not a musical time-stretch. No phase vocoder, no transient
smearing beyond what a polyphase resampler introduces. This follows the
project decision: for tiny long-term clock drift, resample the timeline.
"""

from __future__ import annotations

import numpy as np

from chronosync.io.resampler import resample
from chronosync.models.timemap import TimeMap

_CROSSFADE_SAMPLES = 240  # 5 ms @ 48 kHz at seams


def correct_track(
    track: np.ndarray,
    time_map: TimeMap,
    sample_rate: int = 48_000,
    quality: str = "HQ",
) -> np.ndarray:
    """Render a track onto the global timeline by resampling.

    The output covers the global timeline ``[0, to_global(len/sr)]``.
    Content that maps to negative global times (the track starts before the
    global origin) is dropped with a warning; flat TimeMap spans
    (discontinuity gaps / duplicated ranges) become silence, as documented
    in the estimator.

    Args:
        track: mono signal on the track's LOCAL timeline.
        time_map: mapping local -> global (seconds).
        sample_rate: canonical sample rate.
        quality: SoXR quality preset.
    """
    import warnings as _warnings

    track = np.asarray(track, dtype=np.float64)
    duration_s = track.size / sample_rate

    knots = _render_knots(time_map, duration_s)
    total_out = max(0, int(round(float(knots[-1][1]) * sample_rate)))
    out = np.zeros(total_out, dtype=np.float64)
    dropped_head = False

    for (l0, g0), (l1, g1) in zip(knots, knots[1:]):
        if g1 <= 0.0:
            dropped_head = True
            continue
        src_len = max(0, int(round((l1 - l0) * sample_rate)))
        if src_len == 0:  # flat span: gap/duplicated range -> silence
            continue
        start = min(int(round(l0 * sample_rate)), track.size)
        src = track[start : start + src_len]
        if src.size == 0:
            continue

        dst_len = int(round((g1 - g0) * sample_rate))
        if dst_len <= 0:
            continue  # flat span (drop gap / duplicated range): no output
        ratio = dst_len / src.size
        piece = resample(src, sample_rate, sample_rate * ratio, quality=quality)
        piece = np.asarray(piece, dtype=np.float64)
        if piece.size > dst_len:
            piece = piece[:dst_len]
        elif piece.size < dst_len:
            piece = np.pad(piece, (0, dst_len - piece.size))

        # Place at absolute global positions, clipped to [0, total_out).
        place_start = max(0, int(round(g0 * sample_rate)))
        place_end = min(total_out, int(round(g1 * sample_rate)))
        piece_offset = place_start - int(round(g0 * sample_rate))
        seg_len = place_end - place_start
        if seg_len <= 0:
            continue

        # tiny crossfade at seams between non-silent pieces
        prev_has_signal = place_start > 0 and bool(
            np.any(out[max(0, place_start - _CROSSFADE_SAMPLES) : place_start] != 0)
        )
        if prev_has_signal:
            fade = min(_CROSSFADE_SAMPLES, seg_len, place_start)
            if fade > 0:
                w = np.linspace(0.0, 1.0, fade)
                piece[:fade] = (
                    piece[:fade] * w + out[place_start - fade : place_start] * (1.0 - w)
                )
        out[place_start:place_end] = piece[piece_offset : piece_offset + seg_len]

    if dropped_head:
        _warnings.warn(
            "track content mapping to negative global times was dropped "
            f"({time_map.to_global(0.0):.4f} s before the global origin)",
            stacklevel=2,
        )
    return out.astype(np.float32)


def _render_knots(time_map: TimeMap, duration_s: float) -> list[tuple[float, float]]:
    """Knots covering [0, duration] in LOCAL time (with extrapolation).

    Identity/constant/linear maps yield their boundary knots; piecewise maps
    are extended to the full local range using the end slopes.
    """
    from chronosync.models.timemap import PiecewiseLinearTimeMap

    if isinstance(time_map, PiecewiseLinearTimeMap):
        knots = list(time_map.knots)
    else:
        knots = [(0.0, time_map.to_global(0.0)), (duration_s, time_map.to_global(duration_s))]

    if not knots:
        return [(0.0, time_map.to_global(0.0)), (duration_s, time_map.to_global(duration_s))]
    if knots[0][0] > 0.0:
        knots.insert(0, (0.0, time_map.to_global(0.0)))
    if knots[-1][0] < duration_s:
        knots.append((duration_s, time_map.to_global(duration_s)))
    return knots
