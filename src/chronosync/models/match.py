"""Coarse-match result models (Layer 2 of the pipeline).

Offset sign convention (ADR-003)::

    offset = t_target - t_reference

``offset > 0`` means the corresponding event occurs *later* in ``target``
than in ``reference``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MatchResult:
    """Result of one coarse-matching attempt between a reference and a target.

    A coarse match must never return only a bare float: it reports whether a
    match was found, the offset, an interpretable confidence, the method that
    produced it, and an estimate of the overlapping region.
    """

    matched: bool
    offset_samples: float | None  # d = t_target - t_reference, samples @ canonical rate
    offset_seconds: float | None  # same offset in seconds
    confidence: float  # in [0, 1]; evidence sources documented in docs/algorithms.md
    method: str  # "metadata" | "fingerprint" | "envelope" | "transient" | "none"
    overlap_estimate: tuple[float, float] | None = None
    # (start_s, end_s) of the overlapping region measured on the REFERENCE timeline.
    evidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
