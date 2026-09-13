"""Peak detection and selection for correlation surfaces (ADR-004).

ChronoSync never accepts "the global maximum is the answer" without further
checks. Candidate peaks are discovered with ``scipy.signal.find_peaks`` and
carry a prominence measure; the primary/secondary selection additionally
supports a search prior for ambiguous (periodic / reverberant) signals.

Every threshold lives in :class:`PeakSelectionConfig` so it can be configured,
tested and documented — no magic constants scattered through callers.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
from scipy import signal


@dataclass
class CorrelationPeak:
    """One local maximum of a correlation surface."""

    lag_samples: int  # absolute lag (ADR-003: positive = target later)
    value: float  # correlation value at the peak
    prominence: float  # peak prominence relative to the surrounding baseline


@dataclass
class PeakSelectionConfig:
    """Configuration for candidate discovery and primary/secondary selection.

    Attributes:
        min_distance_samples: minimum separation between candidate peaks
            (passed to ``scipy.signal.find_peaks`` as ``distance``).
        exclusion_samples: neighbourhood around the chosen primary peak that
            is excluded when looking for the second peak.
        min_height: absolute height threshold for candidate peaks.
        prior_delay_samples: optional expected delay; when set, candidates
            within ``(1 - prior_tolerance)`` of the best peak's height are
            re-ranked by proximity to the prior (useful for periodic signals).
        prior_sigma_samples: scale of the Gaussian prior penalty.
        prior_tolerance: relative height window used for prior re-ranking.
    """

    min_distance_samples: int = 2
    exclusion_samples: int = 8
    min_height: float = 0.0
    prior_delay_samples: float | None = None
    prior_sigma_samples: float = 256.0
    prior_tolerance: float = 0.2


def find_peaks(
    window: np.ndarray, lag_offset: int, config: PeakSelectionConfig
) -> list[CorrelationPeak]:
    """Find local maxima of ``window``; absolute lag = ``lag_offset + index``.

    ``lag_offset`` is the signed lag (in samples) corresponding to window
    index 0. Candidates are sorted by descending value.

    Note: ``scipy.signal.find_peaks`` does NOT report maxima at the array
    edges, so the window is padded with ``-inf`` on both sides for detection
    only. Candidates are then required to be STRICTLY greater than both
    neighbours (kills plateau artifacts of the padding), and prominences are
    computed on the original window so edge peaks get finite, meaningful
    values.
    """
    window = np.asarray(window, dtype=np.float64)
    padded = np.concatenate(([-np.inf], window, [-np.inf]))
    indices, _ = signal.find_peaks(
        padded,
        distance=config.min_distance_samples,
        height=config.min_height,
    )
    if indices.size == 0:
        return []
    keep = [
        int(i)
        for i in indices
        if padded[i] > padded[i - 1] and padded[i] > padded[i + 1]
    ]
    if not keep:
        return []
    indices = np.asarray(keep) - 1  # back to window coordinates
    with warnings.catch_warnings():
        # Equal-height peaks (periodic signals) legitimately yield
        # prominence 0 — an expected, handled case, not a problem.
        warnings.filterwarnings(
            "ignore", message="some peaks have a prominence of 0"
        )
        prominences = signal.peak_prominences(window, indices)[0]
    peaks = [
        CorrelationPeak(
            lag_samples=int(lag_offset) + int(i),
            value=float(window[i]),
            prominence=float(p),
        )
        for i, p in zip(indices, prominences)
    ]
    peaks.sort(key=lambda p: p.value, reverse=True)
    return peaks


def select_primary_and_second(
    peaks: list[CorrelationPeak], config: PeakSelectionConfig
) -> tuple[CorrelationPeak | None, CorrelationPeak | None]:
    """Choose the primary and second peaks from a value-sorted candidate list.

    With a prior configured, candidates within ``prior_tolerance`` of the best
    height are re-ranked by proximity to the prior; the rest of the selection
    is unchanged. The second peak must be at least ``exclusion_samples`` away
    from the primary.
    """
    if not peaks:
        return None, None

    best = peaks[0]
    if config.prior_delay_samples is not None:
        candidates = [
            p
            for p in peaks
            if p.value >= (1.0 - config.prior_tolerance) * best.value
        ]
        best = min(
            candidates,
            key=lambda p: abs(p.lag_samples - config.prior_delay_samples),
        )

    others = [
        p
        for p in peaks
        if p is not best
        and abs(p.lag_samples - best.lag_samples) >= config.exclusion_samples
    ]
    second = others[0] if others else None
    return best, second
