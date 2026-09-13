"""Sub-sample delay refinement via parabolic interpolation (ADR-004).

A parabola is fitted through the correlation peak and its two immediate
neighbours; its vertex is used as the sub-sample delay estimate.

Important: parabolic interpolation yields a *numerical estimate*, not a claim
of absolute physical timing accuracy. We do not claim e.g. "0.1 sample
accuracy" unless a benchmark demonstrates it for a specific signal condition.
"""

from __future__ import annotations

import math


def parabolic_interpolation(
    y_left: float, y_center: float, y_right: float
) -> tuple[float, float]:
    """Refine a peak position given three equally spaced correlation samples.

    Args:
        y_left: correlation value at lag - 1.
        y_center: correlation value at the discrete peak (lag).
        y_right: correlation value at lag + 1.

    Returns:
        ``(delta, peak_value)`` where ``delta`` in ``[-0.5, 0.5]`` is the
        sub-sample shift of the vertex relative to the discrete peak, and
        ``peak_value`` is the interpolated vertex height.
    """
    yl = float(y_left)
    yc = float(y_center)
    yr = float(y_right)

    denominator = yl - 2.0 * yc + yr
    if not math.isfinite(denominator) or abs(denominator) < 1e-12:
        # Degenerate / flat neighborhood: keep the discrete peak.
        return 0.0, yc

    delta = 0.5 * (yl - yr) / denominator
    delta = max(-0.5, min(0.5, delta))  # clamp to the physical range
    peak_value = yc - 0.25 * (yl - yr) * delta
    if not math.isfinite(peak_value):
        return 0.0, yc
    return float(delta), float(peak_value)
