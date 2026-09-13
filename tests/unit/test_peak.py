"""Unit tests for correlation peak discovery and selection."""

from __future__ import annotations

import numpy as np

from chronosync.fine.peak import (
    CorrelationPeak,
    PeakSelectionConfig,
    find_peaks,
    select_primary_and_second,
)


def _window_with_peaks() -> np.ndarray:
    # Two clear peaks at relative indices 10 (height 1.0) and 30 (height 0.6).
    w = np.zeros(64)
    w[10], w[9], w[11] = 1.0, 0.1, 0.1
    w[30], w[29], w[31] = 0.6, 0.05, 0.05
    return w


def test_find_peaks_returns_absolute_lags_sorted_by_value():
    w = _window_with_peaks()
    peaks = find_peaks(w, lag_offset=-20, config=PeakSelectionConfig())
    # Relative index 10 -> lag -20 + 10 = -10 (taller), then +10.
    assert [p.lag_samples for p in peaks] == [-10, 10]
    assert peaks[0].value == 1.0
    assert peaks[1].value == 0.6


def test_select_primary_and_second():
    peaks = [
        CorrelationPeak(lag_samples=10, value=1.0, prominence=0.9),
        CorrelationPeak(lag_samples=30, value=0.6, prominence=0.5),
    ]
    primary, second = select_primary_and_second(peaks, PeakSelectionConfig())
    assert primary is peaks[0]
    assert second is peaks[1]


def test_second_peak_must_be_outside_exclusion_zone():
    peaks = [
        CorrelationPeak(lag_samples=10, value=1.0, prominence=0.9),
        CorrelationPeak(lag_samples=12, value=0.9, prominence=0.8),
    ]
    config = PeakSelectionConfig(exclusion_samples=8)
    primary, second = select_primary_and_second(peaks, config)
    assert primary is peaks[0]
    assert second is None  # 12 - 10 = 2 < 8


def test_prior_reranks_ambiguous_peaks():
    # Two nearly equal peaks; the prior prefers the one further from the top.
    peaks = [
        CorrelationPeak(lag_samples=100, value=1.00, prominence=0.0),
        CorrelationPeak(lag_samples=200, value=0.98, prominence=0.0),
    ]
    config = PeakSelectionConfig(
        prior_delay_samples=195.0, prior_sigma_samples=50.0, prior_tolerance=0.2
    )
    primary, second = select_primary_and_second(peaks, config)
    assert primary.lag_samples == 200
    assert second.lag_samples == 100


def test_prior_does_not_override_clear_winner():
    peaks = [
        CorrelationPeak(lag_samples=100, value=1.0, prominence=0.9),
        CorrelationPeak(lag_samples=200, value=0.1, prominence=0.05),
    ]
    config = PeakSelectionConfig(prior_delay_samples=195.0, prior_tolerance=0.2)
    primary, _ = select_primary_and_second(peaks, config)
    assert primary.lag_samples == 100  # 0.1 is far below (1 - 0.2) * 1.0


def test_empty_input():
    assert find_peaks(np.zeros(10), 0, PeakSelectionConfig()) == []
    primary, second = select_primary_and_second([], PeakSelectionConfig())
    assert primary is None and second is None
