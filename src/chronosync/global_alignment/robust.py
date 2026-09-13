"""Robustification for the multi-track solver (Phase 6, optional layer).

The plain solver is weighted least squares; :func:`irls_weights` provides
iterative reweighting (Huber-style) so that outlier edges lose influence
instead of bending the solution. RANSAC/Huber variants beyond IRLS are
deliberately postponed (ADR-011: v1 keeps the plain solver primary).
"""

from __future__ import annotations

import numpy as np


def huber_weight(residual: float, scale: float) -> float:
    """Huber-type weight for one residual: 1 inside, 1/|z| outside."""
    if scale <= 0.0:
        return 1.0
    z = abs(residual) / max(scale, 1e-12)
    if z <= 1.0:
        return 1.0
    return 1.0 / z


def robust_scale(residuals: np.ndarray) -> float:
    """Median-absolute-deviation scale (robust sigma)."""
    if residuals.size == 0:
        return 0.0
    med = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - med)))
    return 1.4826 * max(mad, 1e-9)


def irls_weights(
    residuals: np.ndarray, current: np.ndarray | None = None, outlier_sigma: float = 3.0
) -> np.ndarray:
    """Updated edge weights: current * Huber(residual / robust_sigma)."""
    scale = robust_scale(residuals)
    if current is None:
        current = np.ones_like(residuals)
    return np.asarray(current, dtype=np.float64) * np.asarray(
        [huber_weight(float(r), scale) for r in residuals], dtype=np.float64
    )


def flag_outliers(residuals: np.ndarray, outlier_sigma: float = 3.0) -> np.ndarray:
    """Boolean mask: residuals beyond ``outlier_sigma`` robust sigmas."""
    scale = robust_scale(residuals)
    if scale <= 0.0:
        return np.zeros(residuals.size, dtype=bool)
    return np.abs(residuals) > outlier_sigma * scale
