"""GCC-PHAT delay estimation (ADR-004).

The core local fine-alignment tool of ChronoSync. Offset sign convention
(ADR-003)::

    delay = t_target - t_reference
    delay > 0  =>  the corresponding event occurs LATER in `target`.

Implementation sketch (all FFTs zero-padded to at least
``len(ref) + len(tgt) - 1``, so the result is the *linear*
cross-correlation, not a circular one)::

    R = rfft(ref, nfft);  T = rfft(tgt, nfft)
    G[k] = conj(R[k]) * T[k] / (|R[k]| * |T[k]| + eps)     # PHAT whitening
    gcc[j] = irfft(G, nfft) ~ sum_n ref[n] * tgt[n + j]    # j <= nfft // 2

Negative lags are wrapped: ``lag = j - nfft`` for ``j > nfft // 2``.
Valid lags are ``[-(len(tgt) - 1), len(ref) - 1]``; the search range is
clipped to this interval. Peak selection, sub-sample refinement and
confidence estimation are described in ``docs/algorithms.md``.

Whitening is *regularized*: ``eps = epsilon_rel * max(|G|) + epsilon_abs``.
Pure absolute floors (``epsilon_rel = 0``) amplify spectral-leakage and
near-zero bins of narrowband signals (e.g. a truncated pure tone) into
garbage; the relative floor suppresses bins below ``epsilon_rel`` of the
spectral peak instead of whitening them. Default ``epsilon_rel = 1e-3``
keeps broadband signals essentially untouched (peak ~0.99) while making
periodic signals behave like their plain cross-correlation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import fft

from .peak import PeakSelectionConfig, find_peaks, select_primary_and_second
from .subsample import parabolic_interpolation

#: Minimum peak height (relative to the theoretical noise floor of a
#: whitened spectrum) for a result to be reported as successful.
_MIN_PEAK_FLOOR_RATIO = 2.0

#: Confidence weights: height / peak-ratio / prominence (sums to 1).
#: The ratio term dominates because peak ambiguity (periodic signals, echo
#: chains) is the most dangerous failure mode of a delay estimate.
_W_HEIGHT, _W_RATIO, _W_PROMINENCE = 0.3, 0.5, 0.2


@dataclass
class GCCResult:
    """Result of one GCC-PHAT measurement (ADR-003 sign convention)."""

    delay_samples: float  # d = t_target - t_reference; nan when not successful
    delay_seconds: float  # delay_samples / sample_rate
    peak_value: float  # (interpolated) primary peak height
    second_peak_value: float | None  # highest peak outside the exclusion zone
    peak_prominence: float | None  # prominence of the primary peak
    confidence: float  # in [0, 1]; evidence sources documented in docs/algorithms.md
    search_range_samples: tuple[int, int]  # effective (clipped) lag search range
    success: bool
    polarity: int = 1  # +1 normal, -1 inverted (negative correlation peak)
    method: str = "gcc-phat"
    warnings: list[str] = field(default_factory=list)


def _prepare(x: np.ndarray, normalize: bool) -> tuple[np.ndarray, float]:
    """Convert to float64, remove the mean, optionally scale to unit RMS.

    Returns ``(prepared, rms)``; ``rms == 0.0`` signals a zero-energy signal.
    """
    x = np.asarray(x, dtype=np.float64)
    x = x - x.mean()
    if not normalize:
        return x, float(np.sqrt(np.mean(x * x)))
    rms = float(np.sqrt(np.mean(x * x)))
    if not math.isfinite(rms) or rms <= 1e-12:
        return x, 0.0
    return x / rms, rms


def _valid_lag_range(n_ref: int, n_tgt: int) -> tuple[int, int]:
    return (-(n_tgt - 1), n_ref - 1)


def _lag_to_index(lag: int, nfft: int) -> int:
    return lag if lag >= 0 else lag + nfft


def _noise_floor(nfft: int) -> float:
    """Expected peak of an irfft of a unit-magnitude random-phase spectrum."""
    return math.sqrt(2.0 * math.log(nfft)) / math.sqrt(nfft)


def _failure(
    search_range: tuple[int, int], warnings: list[str], extra: str = ""
) -> GCCResult:
    warnings = list(warnings)
    if extra:
        warnings.append(extra)
    nan = float("nan")
    return GCCResult(
        delay_samples=nan,
        delay_seconds=nan,
        peak_value=0.0,
        second_peak_value=None,
        peak_prominence=None,
        confidence=0.0,
        search_range_samples=search_range,
        success=False,
        warnings=warnings,
    )


def gcc_phat(
    reference: np.ndarray,
    target: np.ndarray,
    sample_rate: float,
    search_min: int | None = None,
    search_max: int | None = None,
    *,
    normalize: bool = True,
    epsilon: float = 1e-12,
    epsilon_rel: float = 1e-3,
    peak_config: PeakSelectionConfig | None = None,
) -> GCCResult:
    """Estimate the delay between two mono signals with GCC-PHAT.

    Args:
        reference: 1-D mono signal (any dtype, internally float64).
        target: 1-D mono signal.
        sample_rate: sample rate in Hz (used only to convert to seconds).
        search_min: lower bound of the lag search range, in samples
            (inclusive; clipped to the valid range).
        search_max: upper bound of the lag search range, in samples.
        normalize: remove the mean and scale both signals to unit RMS before
            correlation (default True; PHAT itself is gain-invariant).
        epsilon: absolute PHAT denominator floor ``|G| + eps`` (division
            guard). Default 1e-12.
        epsilon_rel: relative floor as a fraction of ``max(|G|)``; see the
            module docstring. Default 1e-3.
        peak_config: peak discovery/selection configuration.

    Returns:
        :class:`GCCResult` — never raises on empty/zero-energy inputs; such
        cases yield ``success=False`` with a warning instead.
    """
    warnings: list[str] = []
    ref = np.asarray(reference, dtype=np.float64)
    tgt = np.asarray(target, dtype=np.float64)
    if ref.ndim != 1 or tgt.ndim != 1:
        raise ValueError("reference and target must be 1-D mono signals")
    config = peak_config if peak_config is not None else PeakSelectionConfig()

    if ref.size == 0 or tgt.size == 0:
        return _failure((0, 0), warnings, "empty input signal")

    ref, rms_ref = _prepare(ref, normalize)
    tgt, rms_tgt = _prepare(tgt, normalize)
    if rms_ref == 0.0 or rms_tgt == 0.0:
        return _failure((0, 0), warnings, "zero-energy input signal")

    nfft = fft.next_fast_len(ref.size + tgt.size - 1, real=True)
    r_spec = fft.rfft(ref, nfft)
    t_spec = fft.rfft(tgt, nfft)
    g = np.conj(r_spec) * t_spec
    g /= np.abs(g) + epsilon_rel * float(np.max(np.abs(g))) + epsilon
    gcc = fft.irfft(g, nfft)

    lag_min_valid, lag_max_valid = _valid_lag_range(ref.size, tgt.size)
    lo = lag_min_valid if search_min is None else max(int(search_min), lag_min_valid)
    hi = lag_max_valid if search_max is None else min(int(search_max), lag_max_valid)
    if search_min is not None and int(search_min) < lag_min_valid:
        warnings.append(
            f"search_min {search_min} clipped to valid lower lag {lag_min_valid}"
        )
    if search_max is not None and int(search_max) > lag_max_valid:
        warnings.append(
            f"search_max {search_max} clipped to valid upper lag {lag_max_valid}"
        )
    if lo > hi:
        return _failure(
            (lo, hi),
            warnings,
            f"empty search range after clipping to valid lags "
            f"[{lag_min_valid}, {lag_max_valid}]",
        )

    i_lo = _lag_to_index(lo, nfft)
    i_hi = _lag_to_index(hi, nfft)
    if i_lo <= i_hi:
        window = gcc[i_lo : i_hi + 1]
    else:  # the requested lag range straddles the wrap-around point
        window = np.concatenate((gcc[i_lo:], gcc[: i_hi + 1]))

    peaks = find_peaks(window, lag_offset=lo, config=config)
    if not peaks:
        return _failure((lo, hi), warnings, "no peak found in search range")

    # Polarity-aware peak selection: a polarity-INVERTED pair correlates
    # negatively, so its peak is the deepest MINIMUM of the surface. When the
    # negative peak is clearly stronger, flip the surface and analyze it
    # exactly like a normal peak (magnitudes, ratio, prominence).
    inverted = False
    surface = window
    if window.size:
        pos_best = float(np.max(window))
        neg_best = -float(np.min(window))
        if neg_best > pos_best * 1.2:
            inverted = True
            surface = -window
            warnings.append(
                "polarity inversion: negative correlation peak "
                "(the pair appears phase-inverted)"
            )
            peaks = find_peaks(surface, lag_offset=lo, config=config)
            if not peaks:
                return _failure((lo, hi), warnings, "no peak found in search range")

    primary, second = select_primary_and_second(peaks, config)

    rel = primary.lag_samples - lo
    if 1 <= rel <= len(surface) - 2:
        delta, refined_value = parabolic_interpolation(
            float(surface[rel - 1]), float(surface[rel]), float(surface[rel + 1])
        )
    else:  # peak at a search-range edge: no neighbours available
        delta, refined_value = 0.0, primary.value
    delay_samples = float(primary.lag_samples) + delta
    delay_seconds = delay_samples / float(sample_rate)

    # Confidence: weighted, interpretable evidence (docs/algorithms.md).
    #   1) height of the whitened peak vs the theoretical noise floor
    #   2) peak ratio vs the second peak (ambiguity — dominant weight)
    #   3) peak prominence (sharpness)
    nf = _noise_floor(nfft)
    v = max(float(refined_value), 0.0)
    if v <= nf:
        height_score = 0.0
    else:
        height_score = min(1.0, math.log10(v / nf) / math.log10(1.0 / nf))
    if second is None or second.value <= 0.0:
        ratio_score = 1.0
    else:
        ratio = v / float(second.value)
        ratio_score = max(0.0, min(1.0, (ratio - 1.0) / (ratio - 1.0 + 0.5)))
    prominence = float(primary.prominence)
    prominence_score = max(0.0, min(1.0, prominence / v)) if v > 0.0 else 0.0
    confidence = float(
        np.clip(
            _W_HEIGHT * height_score + _W_RATIO * ratio_score + _W_PROMINENCE * prominence_score,
            0.0,
            1.0,
        )
    )

    success = v >= _MIN_PEAK_FLOOR_RATIO * nf

    if second is not None and second.value > 0.0 and v / second.value < 1.5:
        warnings.append(
            "ambiguous peaks: primary/secondary ratio < 1.5 (periodic-like signal?)"
        )
    if v > 0.0 and prominence < 0.1 * v:
        warnings.append("low peak prominence")
    if delay_samples <= lo + 0.5 or delay_samples >= hi - 0.5:
        warnings.append("peak at search-range boundary")
    if not success:
        warnings.append(
            f"peak height {v:.3g} below threshold {_MIN_PEAK_FLOOR_RATIO * nf:.3g}"
        )

    return GCCResult(
        delay_samples=delay_samples,
        delay_seconds=delay_seconds,
        peak_value=refined_value,
        second_peak_value=(second.value if second is not None else None),
        peak_prominence=prominence,
        confidence=confidence,
        search_range_samples=(lo, hi),
        success=success,
        polarity=(-1 if inverted else 1),
        warnings=warnings,
    )
