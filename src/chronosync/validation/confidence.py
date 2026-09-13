"""Interpretable confidence aggregation (Phase 7).

Never a mysterious ``confidence = 0.95``: the final confidence is a
documented, weighted combination of EVIDENCE sources, and the full evidence
dict + warnings travel with the result.

Evidence sources (weights sum to 1):

* coarse confidence (0.25)        — did the coarse layer find the content?
* drift regression R^2 (0.20)     — how well does the time model fit?
* residual GCC (0.25)             — does the alignment hold locally?
* coherence (0.15)                — do the signals actually share energy?
* polarity consistency (0.15)     — no undetected phase inversion

Each source maps to [0, 1] with documented rules; missing evidence is
excluded and its weight is renormalized (with a warning).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chronosync.drift import DriftEstimate
from chronosync.fine.gcc_phat import gcc_phat
from chronosync.models.match import MatchResult
from chronosync.models.timemap import TimeMap

from .coherence import mean_coherence
from .polarity import polarity_check
from .residual import ResidualConfig, residual_offsets

_WEIGHTS = {
    "coarse": 0.25,
    "drift_r2": 0.20,
    "residual": 0.25,
    "coherence": 0.15,
    "polarity": 0.15,
}

#: residual <= this many samples counts as "locally aligned"
_RESIDUAL_FULL_SAMPLES = 0.5
_RESIDUAL_FAIL_SAMPLES = 50.0
#: coherence above this counts as "shares content"
_COH_FULL = 0.8
_COH_NONE = 0.1


@dataclass
class ValidationReport:
    """Aggregated validation evidence for one aligned pair."""

    confidence: float  # in [0, 1]
    evidence: dict[str, float]
    warnings: list[str] = field(default_factory=list)
    residual_mean_abs_samples: float | None = None
    residual_max_abs_samples: float | None = None
    coherence: float | None = None
    polarity: int | None = None
    inverted: bool = False
    success: bool = True


def validate_pair(
    reference: np.ndarray,
    target: np.ndarray,
    coarse: MatchResult,
    drift: DriftEstimate | None,
    time_map: TimeMap | None,
    sample_rate: int = 48_000,
    residual_config: ResidualConfig | None = None,
) -> ValidationReport:
    """Validate one aligned pair and aggregate interpretable confidence.

    ``target`` is on its local timeline; ``time_map`` maps it to the
    reference timeline. The target is RENDERED onto the global timeline
    first (SoXR resampling) so that coherence/polarity are judged on
    actually-aligned content — on the raw drifted pair the coherence
    collapses by itself (a drift smear is NOT evidence of misalignment).
    """
    warnings: list[str] = []
    evidence: dict[str, float] = {}
    report = ValidationReport(confidence=0.0, evidence=evidence)

    # 1) coarse
    if coarse is not None:
        evidence["coarse"] = float(np.clip(coarse.confidence, 0.0, 1.0))
    else:
        warnings.append("no coarse evidence available")

    # 2) drift R^2
    if drift is not None and drift.success:
        evidence["drift_r2"] = float(np.clip(max(drift.model.r2, 0.0), 0.0, 1.0))
    else:
        warnings.append("no usable drift model")

    # Render the target onto the global timeline once (optional feature;
    # uses SoXR, not a phase vocoder).
    corrected: np.ndarray | None = None
    if time_map is not None:
        import warnings as _warnings

        from chronosync.drift import correct_track
        from chronosync.models.timemap import IdentityTimeMap

        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            corrected = correct_track(target, time_map, sample_rate)

    # 3) residual GCC on the corrected timeline
    if corrected is not None and corrected.size:
        res = residual_offsets(
            reference, corrected, IdentityTimeMap(), sample_rate, residual_config
        )
        report.residual_mean_abs_samples = res.mean_abs_samples
        report.residual_max_abs_samples = res.max_abs_samples
        if np.isfinite(res.mean_abs_samples):
            m = float(res.mean_abs_samples)
            score = float(
                np.clip(
                    1.0
                    - (m - _RESIDUAL_FULL_SAMPLES)
                    / (_RESIDUAL_FAIL_SAMPLES - _RESIDUAL_FULL_SAMPLES),
                    0.0,
                    1.0,
                )
            )
            evidence["residual"] = score
        else:
            warnings.append("no measurable residual windows")
        warnings.extend(res.warnings)
    else:
        warnings.append("no time map: residual GCC skipped")

    # 4) coherence + 5) polarity on the aligned overlap
    if corrected is not None and corrected.size:
        ref_win, tgt_win = _aligned_windows(reference, corrected)
        if ref_win is not None and ref_win.size > 4096:
            report.coherence = mean_coherence(ref_win, tgt_win, sample_rate)
            evidence["coherence"] = float(
                np.clip(
                    (report.coherence - _COH_NONE) / (_COH_FULL - _COH_NONE), 0.0, 1.0
                )
            )
            pol = polarity_check(ref_win, tgt_win)
            report.polarity = pol.polarity
            report.inverted = pol.inverted
            if pol.inverted:
                evidence["polarity"] = 0.0
                warnings.append("POLARITY INVERSION detected")
            elif pol.polarity == 0:
                warnings.extend(pol.warnings)
                # undecided: partial credit, keep the term honest
                evidence["polarity"] = 0.5
            else:
                evidence["polarity"] = 1.0
        else:
            warnings.append("overlap too short for coherence/polarity checks")
    else:
        warnings.append("no corrected render: coherence/polarity skipped")

    total_w = sum(_WEIGHTS[k] for k in evidence)
    if total_w <= 0.0:
        report.success = False
        report.warnings = warnings
        report.evidence = evidence
        return report
    confidence = sum(_WEIGHTS[k] * evidence[k] for k in evidence) / total_w
    if total_w < 0.99:
        warnings.append(
            "some evidence sources unavailable; weights renormalized "
            f"({total_w:.2f} of 1.00)"
        )
    report.confidence = float(np.clip(confidence, 0.0, 1.0))
    report.warnings = warnings
    report.evidence = evidence
    return report


def _aligned_windows(
    reference: np.ndarray,
    corrected: np.ndarray,
    max_seconds: float = 30.0,
    offset_seconds: float = 1.0,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Two windows on the shared global grid (both already aligned)."""
    span = min(min(reference.size, corrected.size) / 48_000.0, max_seconds)
    if span <= 2.0:
        return None, None
    s = int(offset_seconds * 48_000)
    n = int(span * 48_000)
    ref_win = reference[s : s + n]
    tgt_win = corrected[s : s + n]
    common = min(ref_win.size, tgt_win.size)
    return ref_win[:common], tgt_win[:common]
