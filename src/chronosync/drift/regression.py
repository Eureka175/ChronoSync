"""Weighted and robust linear regression for offset(t) fits (Layer 4).

``d(t) = alpha * t + beta`` with ``t`` in samples (canonical rate) and
``d`` the local offset (ADR-003). Outlier rejection uses the median /
MAD rule so a few bad windows (wrong content, dropouts) cannot bend the
fit; the drift estimator re-checks classification afterwards.
"""

from __future__ import annotations

import numpy as np


def weighted_linear_fit(
    t: np.ndarray, d: np.ndarray, w: np.ndarray | None = None
) -> tuple[float, float, float, np.ndarray]:
    """Weighted least-squares fit of ``d = alpha * t + beta``.

    Returns ``(alpha, beta, r2, residuals)``. ``t`` is centered internally
    for numerical stability (beta is reported at ``t = 0``).
    """
    t = np.asarray(t, dtype=np.float64)
    d = np.asarray(d, dtype=np.float64)
    if w is None:
        w = np.ones_like(d)
    w = np.asarray(w, dtype=np.float64)
    if t.size < 2:
        raise ValueError("at least two points are required for a linear fit")

    t0 = float(np.average(t, weights=w))
    tc = t - t0
    a_w = np.sqrt(w)
    a_mat = np.column_stack([tc, np.ones_like(tc)]) * a_w[:, None]
    b_vec = d * a_w
    (slope_c, beta_c), *_ = np.linalg.lstsq(a_mat, b_vec, rcond=None)
    slope = float(slope_c)
    beta = float(beta_c - slope_c * t0)

    pred = slope * t + beta
    residuals = d - pred
    ss_res = float(np.sum(w * residuals * residuals))
    d_mean = float(np.average(d, weights=w))
    ss_tot = float(np.sum(w * (d - d_mean) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 0.0
    return slope, beta, r2, residuals


def robust_linear_fit(
    t: np.ndarray,
    d: np.ndarray,
    w: np.ndarray | None = None,
    *,
    mad_k: float = 3.0,
    max_iter: int = 2,
) -> tuple[float, float, float, np.ndarray, np.ndarray, list[int]]:
    """Weighted fit with MAD-based outlier rejection.

    Returns ``(alpha, beta, r2, residuals, inlier_mask, dropped_indices)``.
    ``inlier_mask`` is relative to the ORIGINAL inputs; ``dropped_indices``
    lists the rejected positions in the original arrays.
    """
    t = np.asarray(t, dtype=np.float64)
    d = np.asarray(d, dtype=np.float64)
    if w is None:
        w = np.ones_like(d)
    w = np.asarray(w, dtype=np.float64)

    mask = np.ones(t.size, dtype=bool)
    for _ in range(max_iter + 1):
        slope, beta, r2, residuals = weighted_linear_fit(t[mask], d[mask], w[mask])
        if mask.sum() <= 2:
            break
        med = float(np.median(residuals))
        mad = float(np.median(np.abs(residuals - med)))
        bound = mad_k * 1.4826 * max(mad, 1e-12)
        new_mask = mask.copy()
        new_mask[mask] = np.abs(residuals - med) <= bound
        if np.array_equal(new_mask, mask):
            break
        mask = new_mask

    slope, beta, r2, residuals = weighted_linear_fit(t[mask], d[mask], w[mask])
    full_residuals = d - (slope * t + beta)
    dropped = [int(i) for i in np.nonzero(~mask)[0]]
    return slope, beta, r2, full_residuals, mask, dropped
