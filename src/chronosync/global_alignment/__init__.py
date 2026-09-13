"""Multi-track global optimization (Layer 5).

* :mod:`chronosync.global_alignment.solver` — weighted least squares over the
  measurement graph (reference pinned at 0, connectivity handling, residuals,
  per-track confidence, optional IRLS).
* :mod:`chronosync.global_alignment.robust` — IRLS reweighting and outlier
  flagging primitives.
"""

from __future__ import annotations

from .robust import flag_outliers, huber_weight, irls_weights, robust_scale
from .solver import SolveConfig, SolvedAlignment, solve

__all__ = [
    "SolveConfig",
    "SolvedAlignment",
    "flag_outliers",
    "huber_weight",
    "irls_weights",
    "robust_scale",
    "solve",
]
