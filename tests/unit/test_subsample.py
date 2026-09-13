"""Unit tests for parabolic sub-sample interpolation."""

from __future__ import annotations

import math

from chronosync.fine.subsample import parabolic_interpolation


def test_symmetric_peak_stays_centered():
    delta, peak = parabolic_interpolation(0.75, 1.0, 0.75)
    assert delta == 0.0
    assert peak == 1.0


def test_peak_shifted_left():
    delta, peak = parabolic_interpolation(0.8, 1.0, 0.6)
    assert math.isclose(delta, -0.1666667, abs_tol=1e-5)
    assert peak > 1.0  # vertex above the discrete sample


def test_peak_shifted_right():
    delta, peak = parabolic_interpolation(0.6, 1.0, 0.8)
    assert math.isclose(delta, +0.1666667, abs_tol=1e-5)


def test_delta_is_clamped_to_half_sample():
    delta, _ = parabolic_interpolation(0.0, 1.0, 0.0)  # delta = 0
    assert delta == 0.0
    delta, _ = parabolic_interpolation(0.0, 0.01, 1.0)  # would exceed 0.5
    assert -0.5 <= delta <= 0.5


def test_degenerate_flat_neighborhood_keeps_discrete_peak():
    delta, peak = parabolic_interpolation(1.0, 1.0, 1.0)
    assert delta == 0.0
    assert peak == 1.0


def test_non_finite_inputs_are_safe():
    delta, peak = parabolic_interpolation(float("nan"), 1.0, 0.5)
    assert delta == 0.0
    assert peak == 1.0
