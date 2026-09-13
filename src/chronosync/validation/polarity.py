"""Polarity validation (Phase 7).

IMPORTANT (project requirement): a LOW magnitude-squared coherence is NOT
equivalent to a polarity inversion — MSC can be low for unrelated content,
different microphone placements, noise, etc. Polarity is decided by
comparing corr(x, y) with corr(x, -y); only when the inverted correlation is
clearly HIGHER do we report an inversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class PolarityResult:
    """Polarity decision based on BOTH correlation signs."""

    polarity: int  # +1 normal, -1 inverted, 0 undecided
    corr_normal: float
    corr_inverted: float
    inverted: bool
    warnings: list[str] = field(default_factory=list)


def polarity_check(
    x: np.ndarray,
    y: np.ndarray,
    margin: float = 0.1,
) -> PolarityResult:
    """Decide polarity by comparing corr(x, y) with corr(x, -y).

    ``inverted=True`` only when the inverted correlation exceeds the normal
    one by at least ``margin``; otherwise the pair is either normal or
    undecided (a low MSC alone never implies inversion).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    common = min(x.size, y.size)
    if common < 4 or not np.any(x[:common]) or not np.any(y[:common]):
        return PolarityResult(
            polarity=0, corr_normal=0.0, corr_inverted=0.0,
            inverted=False, warnings=["signal too short or silent"],
        )
    a, b = x[:common], y[:common]
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt(np.sum(a * a) * np.sum(b * b))
    if denom <= 0.0:
        return PolarityResult(
            polarity=0, corr_normal=0.0, corr_inverted=0.0,
            inverted=False, warnings=["zero-variance signal"],
        )
    corr_normal = float(np.sum(a * b) / denom)
    corr_inverted = float(np.sum(a * (-b)) / denom)
    if corr_inverted - corr_normal >= margin:
        return PolarityResult(-1, corr_normal, corr_inverted, True)
    if corr_normal - corr_inverted >= margin:
        return PolarityResult(1, corr_normal, corr_inverted, False)
    return PolarityResult(
        0, corr_normal, corr_inverted, False,
        warnings=["polarity undecided (correlations too close)"],
    )
