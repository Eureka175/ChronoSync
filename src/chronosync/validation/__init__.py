"""Validation / confidence / anomaly detection (Layer 6).

* :mod:`chronosync.validation.residual` — post-alignment residual GCC
* :mod:`chronosync.validation.coherence` — mean magnitude-squared coherence
* :mod:`chronosync.validation.polarity` — polarity inversion detection
* :mod:`chronosync.validation.confidence` — interpretable evidence aggregation
"""

from __future__ import annotations

from .coherence import mean_coherence
from .confidence import ValidationReport, validate_pair
from .polarity import PolarityResult, polarity_check
from .residual import ResidualConfig, ResidualResult, residual_offsets

__all__ = [
    "PolarityResult",
    "ResidualConfig",
    "ResidualResult",
    "ValidationReport",
    "mean_coherence",
    "polarity_check",
    "residual_offsets",
    "validate_pair",
]
