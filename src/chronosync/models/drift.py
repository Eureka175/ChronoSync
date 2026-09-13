"""Clock-drift models (Layer 4 of the pipeline).

Linear drift model (ADR-003 sign convention)::

    d(t) = alpha_ppm * 1e-6 * t + beta_samples

where ``d(t) = t_target - t_reference`` and ``t`` is measured in samples at
the canonical sample rate. ``alpha_ppm > 0`` means the target clock runs
faster: events in the target fall progressively later.

Note: an offset change over time is *not* automatically clock drift. The
estimator (drift/ layer, Phase 4) must distinguish clock drift from
discontinuities, bad measurements and missing overlap.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OffsetMeasurement:
    """One local offset estimate (typically from windowed GCC)."""

    center_samples: float  # window center on the REFERENCE timeline, in samples
    offset_samples: float  # d = t_target - t_reference at the window center
    confidence: float  # in [0, 1]
    window_start_samples: int = 0  # window start, reference timeline, samples
    window_end_samples: int = 0  # window end, reference timeline, samples


@dataclass
class DriftModel:
    """Linear clock-drift estimate fitted on local offset measurements."""

    alpha_ppm: float  # target clock rate offset vs reference, parts per million
    beta_samples: float  # intercept: d(0) in samples
    r2: float  # coefficient of determination of the linear fit
    model_type: str  # "linear" | "piecewise_linear" | "none"
    success: bool
    warnings: list[str] = field(default_factory=list)
