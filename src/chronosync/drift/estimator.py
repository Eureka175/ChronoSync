"""Drift estimation (Layer 4).

Pipeline: sliding-window GCC (30-60 s windows, 50% overlap, prior from the
coarse offset) -> local offset(t) measurements -> robust weighted linear fit
-> discontinuity detection (offset steps) -> classification:

* ``clock_drift``      — significant linear rate difference;
* ``constant_offset``  — rate below ``min_drift_ppm``;
* ``piecewise_drift``  — multiple segments with different rates;
* ``discontinuity``    — offset steps (lost/inserted buffers) between segments;
* ``bad_measurements`` — outliers were rejected (warning, not a class by itself);
* ``no_overlap``       — too few usable windows.

A change of the offset over time is NOT automatically clock drift — the
classification rules above are what separates drift from discontinuity,
bad measurements and missing overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chronosync.fine.gcc_phat import gcc_phat
from chronosync.fine.peak import PeakSelectionConfig
from chronosync.models.drift import DriftModel, OffsetMeasurement
from chronosync.models.timemap import (
    ConstantOffsetTimeMap,
    LinearTimeMap,
    TimeMap,
)

from .regression import robust_linear_fit, weighted_linear_fit
from .windows import WindowSchedule, overlap_center_range


def _fit_sse(t: np.ndarray, d: np.ndarray, w: np.ndarray) -> float:
    """Weighted SSE of the best linear fit (changepoint scan helper)."""
    _, _, _, residuals = weighted_linear_fit(t, d, w)
    return float(np.sum(w * residuals * residuals))


@dataclass
class DriftConfig:
    """Drift-estimator parameters (all configurable, documented)."""

    window_samples: int = 30 * 48_000  # window length (prompt: 30-60 s)
    min_window_samples: int = 24_000  # adaptive-shrink floor (0.5 s)
    overlap_ratio: float = 0.5
    min_confidence: float = 0.3  # drop windows below this GCC confidence
    min_windows: int = 4  # minimum usable windows for any verdict
    min_windows_per_segment: int = 3  # each side of a split needs this many
    min_windows_for_split: int = 8  # no changepoint scan below this many points
    split_improvement: float = 0.25  # min relative SSE reduction to accept a split
    split_step_samples: float = 100.0  # ...AND the offset step must be real
    split_slope_ppm: float = 4.0  # ...OR the rate must actually change
    min_drift_ppm: float = 2.0  # below this the pair counts as constant offset
    max_splits: int = 3
    max_lag_seconds: float = 4.0  # GCC search window around the prior
    prior_tolerance: float = 0.2
    mad_k: float = 3.0


@dataclass
class SegmentFit:
    """One fitted segment: reference-time span + its linear model."""

    start_sample: float  # reference timeline (samples)
    end_sample: float
    model: DriftModel
    measurement_indices: list[int]


@dataclass
class DriftEstimate:
    """Full result of drift estimation."""

    model: DriftModel  # first segment's model (or the only one)
    classification: str
    time_map: TimeMap | None  # None when no model could be built
    measurements: list[OffsetMeasurement]
    segments: list[SegmentFit]
    warnings: list[str] = field(default_factory=list)
    success: bool = False


def estimate_drift(
    reference: np.ndarray,
    target: np.ndarray,
    sample_rate: float,
    coarse_offset_samples: float | None = 0.0,
    config: DriftConfig | None = None,
) -> DriftEstimate:
    """Estimate the clock drift / time map between a reference and a target.

    Args:
        reference: mono signal on the reference timeline (canonical rate).
        target: mono signal of the track to map onto the reference.
        sample_rate: canonical sample rate.
        coarse_offset_samples: prior offset d = t_target - t_reference from
            the coarse layer (ADR-003); ``None`` means 0.
        config: see :class:`DriftConfig`.
    """
    cfg = config if config is not None else DriftConfig()
    warnings: list[str] = []
    ref = np.asarray(reference, dtype=np.float64)
    tgt = np.asarray(target, dtype=np.float64)
    d0 = 0.0 if coarse_offset_samples is None else float(coarse_offset_samples)

    # Adaptive window shrink: noise-like content decorrelates under PHAT when
    # the in-window drift exceeds ~1 sample per coherence length, so long
    # windows can yield zero usable measurements. Halve the window until
    # enough windows pass (documented; the prompt's 30-60 s default remains
    # the preferred choice for real tonal/speech content).
    measurements: list[OffsetMeasurement] = []
    window_samples = cfg.window_samples
    floor = max(1024, cfg.min_window_samples)
    # Prefer a denser measurement set: halve the window until at least
    # `target_windows` pass (more windows -> tighter regression).
    target_windows = max(cfg.min_windows, 12)
    while True:
        schedule = WindowSchedule(
            window_samples=window_samples, overlap_ratio=cfg.overlap_ratio
        )
        lo, hi = overlap_center_range(ref.size, tgt.size, d0, schedule)
        if hi < lo:
            window_samples //= 2
            if window_samples < floor:
                return DriftEstimate(
                    model=DriftModel(0.0, 0.0, 0.0, "none", False, warnings),
                    classification="no_overlap",
                    time_map=None,
                    measurements=[],
                    segments=[],
                    warnings=[*warnings, "overlap too short for a full drift window"],
                )
            continue
        measurements = _measure_windows(
            ref, tgt, d0, schedule, lo, hi, cfg, sample_rate
        )
        if len(measurements) >= target_windows or window_samples <= floor:
            break
        warnings.append(
            f"only {len(measurements)} usable windows at {window_samples} samples; "
            f"shrinking the analysis window"
        )
        window_samples //= 2

    if len(measurements) < cfg.min_windows:
        return DriftEstimate(
            model=DriftModel(0.0, 0.0, 0.0, "none", False, warnings),
            classification="no_overlap",
            time_map=None,
            measurements=measurements,
            segments=[],
            warnings=[
                *warnings,
                f"only {len(measurements)} usable windows (< {cfg.min_windows}); "
                "the pair may not share content",
            ],
        )

    t = np.array([m.center_samples for m in measurements], dtype=np.float64)
    d = np.array([m.offset_samples for m in measurements], dtype=np.float64)
    w = np.array([m.confidence for m in measurements], dtype=np.float64)

    segments = _fit_segments(t, d, w, cfg, warnings)

    for prev, cur in zip(segments, segments[1:]):
        t_split = cur.start_sample
        d_before = prev.model.alpha_ppm * 1e-6 * t_split + prev.model.beta_samples
        d_after = cur.model.alpha_ppm * 1e-6 * t_split + cur.model.beta_samples
        jump = d_after - d_before
        if abs(jump) >= 1.0:  # real offset step; a pure slope change reports ~0
            warnings.append(
                f"CLOCK_DISCONTINUITY at reference sample {round(t_split)} "
                f"(offset step {jump:+.0f} samples)"
            )

    classification, time_map = _classify_and_map(
        segments, measurements, cfg, sample_rate, warnings
    )

    first = segments[0]
    return DriftEstimate(
        model=first.model,
        classification=classification,
        time_map=time_map,
        measurements=measurements,
        segments=segments,
        warnings=warnings,
        success=classification != "no_overlap",
    )


def _measure_windows(
    ref: np.ndarray,
    tgt: np.ndarray,
    d0: float,
    schedule: WindowSchedule,
    lo: int,
    hi: int,
    cfg: DriftConfig,
    sample_rate: float,
) -> list[OffsetMeasurement]:
    """Run windowed GCC with a prior and collect usable measurements."""
    peak_config = PeakSelectionConfig(
        prior_delay_samples=d0,
        prior_sigma_samples=float(max(schedule.window_samples / 2.0, 1.0)),
        prior_tolerance=cfg.prior_tolerance,
    )
    half = schedule.window_samples // 2
    max_lag_samples = int(round(cfg.max_lag_seconds * sample_rate))
    measurements: list[OffsetMeasurement] = []
    for center in schedule.centers(lo, hi):
        ref_win = ref[center - half : center + half]
        tgt_start = center + int(round(d0)) - half
        tgt_win = tgt[tgt_start : tgt_start + schedule.window_samples]
        if tgt_win.size < schedule.window_samples:
            continue
        res = gcc_phat(
            ref_win,
            tgt_win,
            sample_rate,
            search_min=int(round(d0)) - max_lag_samples,
            search_max=int(round(d0)) + max_lag_samples,
            peak_config=peak_config,
        )
        if not res.success or res.confidence < cfg.min_confidence:
            continue
        if any("boundary" in w for w in res.warnings):
            continue  # peak pinned to the search edge: unreliable
        measurements.append(
            OffsetMeasurement(
                center_samples=float(center),
                # The window was placed at the coarse offset, so GCC returned
                # the RESIDUAL offset; report the FULL local offset instead.
                offset_samples=float(res.delay_samples) + d0,
                confidence=float(res.confidence),
                window_start_samples=center - half,
                window_end_samples=center + half,
            )
        )
    return measurements


def _fit_segments(
    t: np.ndarray, d: np.ndarray, w: np.ndarray, cfg: DriftConfig, warnings: list[str]
) -> list[SegmentFit]:
    """Recursive robust fit with discontinuity splitting."""

    def fit_range(idx: list[int], depth: int) -> list[SegmentFit]:
        ti, di, wi = t[idx], d[idx], w[idx]
        alpha, beta, r2, residuals, mask, dropped = robust_linear_fit(
            ti, di, wi, mad_k=cfg.mad_k
        )
        if dropped:
            warnings.append(
                f"rejected {len(dropped)} outlier window(s) as bad measurements "
                f"(centers {[round(float(ti[i])) for i in dropped]})"
            )
        inliers = [idx[i] for i in range(len(idx)) if mask[i]]

        # Changepoint scan: split where fitting the two halves separately
        # reduces the weighted SSE the most (detects BOTH offset steps and
        # slope changes — piecewise drift), when the improvement is real.
        # Requires enough points: with too few windows, fitting two halves
        # "improves" the SSE by chance.
        if (
            depth < cfg.max_splits
            and len(inliers) >= cfg.min_windows_for_split
            and len(inliers) >= 2 * cfg.min_windows_per_segment
        ):
            n = len(inliers)
            tm, dm, wm = ti[mask], di[mask], wi[mask]
            sse_full = _fit_sse(tm, dm, wm)
            best_k, best_sse = -1, sse_full
            for k in range(cfg.min_windows_per_segment, n - cfg.min_windows_per_segment + 1):
                sse_split = _fit_sse(tm[:k], dm[:k], wm[:k]) + _fit_sse(
                    tm[k:], dm[k:], wm[k:]
                )
                if sse_split < best_sse:
                    best_k, best_sse = k, sse_split
            if sse_full > 0.0 and (sse_full - best_sse) / sse_full >= cfg.split_improvement:
                # Correlated measurement noise (50% overlapping windows) can
                # make "two halves" look better by chance; require a REAL
                # effect: an offset step or a slope change.
                t_split = tm[best_k - 1]
                alpha_l, beta_l, _, _ = weighted_linear_fit(tm[:best_k], dm[:best_k], wm[:best_k])
                alpha_r, beta_r, _, _ = weighted_linear_fit(tm[best_k:], dm[best_k:], wm[best_k:])
                d_l = alpha_l * t_split + beta_l
                d_r = alpha_r * t_split + beta_r
                step = abs(d_r - d_l)
                slope_change = abs(alpha_r - alpha_l) * 1e6
                if (
                    step >= cfg.split_step_samples
                    or slope_change >= cfg.split_slope_ppm
                ):
                    return fit_range(inliers[:best_k], depth + 1) + fit_range(
                        inliers[best_k:], depth + 1
                    )

        ppm = alpha * 1e6
        start = float(ti[mask].min())
        end = float(ti[mask].max())
        # A segment fit is "successful" when the line explains the data
        # (r2 >= 0.5) OR the segment is effectively a constant offset
        # (|alpha| below the drift floor: r2 of a flat fit is meaningless).
        model = DriftModel(
            alpha_ppm=ppm,
            beta_samples=beta,
            r2=r2,
            model_type="linear",
            success=bool(r2 >= 0.5 or abs(ppm) <= cfg.min_drift_ppm),
        )
        return [SegmentFit(start, end, model, inliers)]

    return fit_range(list(range(t.size)), 0)


def _classify_and_map(
    segments: list[SegmentFit],
    measurements: list[OffsetMeasurement],
    cfg: DriftConfig,
    sample_rate: float,
    warnings: list[str],
) -> tuple[str, TimeMap | None]:
    if not segments:
        return "no_overlap", None

    if len(segments) == 1:
        model = segments[0].model
        if abs(model.alpha_ppm) < cfg.min_drift_ppm:
            # d = t_target - t_reference = beta > 0 means the target runs
            # AHEAD: T_global = T_local - beta/sr (ADR-003/ADR-005).
            offset_seconds = -model.beta_samples / sample_rate
            return "constant_offset", ConstantOffsetTimeMap(offset_seconds)
        return "clock_drift", _linear_time_map(model, sample_rate)

    # Multiple segments: discontinuity (same rate, offset steps) vs piecewise.
    alphas = [s.model.alpha_ppm for s in segments]
    median_alpha = float(np.median(alphas))
    all_same_rate = all(
        abs(a - median_alpha) <= max(cfg.min_drift_ppm, 5.0) for a in alphas
    )
    time_map = _piecewise_time_map(segments, sample_rate, warnings)
    return ("discontinuity" if all_same_rate else "piecewise_drift"), time_map


def _linear_time_map(model: DriftModel, sample_rate: float) -> LinearTimeMap:
    """Invert d(t) = alpha*t + beta into T_global = f(T_local)."""
    alpha = model.alpha_ppm * 1e-6
    scale = 1.0 / (1.0 + alpha)
    offset_seconds = -model.beta_samples / (sample_rate * (1.0 + alpha))
    return LinearTimeMap(scale=scale, offset_seconds=offset_seconds)


def _piecewise_time_map(
    segments: list[SegmentFit], sample_rate: float, warnings: list[str]
) -> TimeMap:
    """Build a piecewise-linear TimeMap from per-segment fits.

    Knots are ``(t_local, t_global)`` in seconds. At a discontinuity the two
    segments map to the same global time: the span between the two local
    times becomes a FLAT region — content there (a drop gap or a duplicated
    span after an insert) contributes nothing on the global timeline.
    """
    from chronosync.models.timemap import PiecewiseLinearTimeMap

    def tau(seg: SegmentFit, t_s: float) -> float:
        alpha = seg.model.alpha_ppm * 1e-6
        return t_s * (1.0 + alpha) + seg.model.beta_samples / sample_rate

    knots: list[tuple[float, float]] = []
    first = segments[0]
    knots.append((tau(first, first.start_sample / sample_rate), first.start_sample / sample_rate))
    for i in range(1, len(segments)):
        prev, cur = segments[i - 1], segments[i]
        a_s = cur.start_sample / sample_rate
        prev_tau = tau(prev, a_s)
        cur_tau = tau(cur, a_s)
        if cur_tau < prev_tau - 1e-4:  # more than ~5 samples of dropped span
            warnings.append(
                "negative local-time jump (dropped content): the span is "
                "modeled as a flat gap (silence on correction)"
            )
        knots.append((min(prev_tau, cur_tau), a_s))
        knots.append((max(prev_tau, cur_tau), a_s))
    last = segments[-1]
    knots.append((tau(last, last.end_sample / sample_rate), last.end_sample / sample_rate))

    return PiecewiseLinearTimeMap(knots=tuple(knots))
