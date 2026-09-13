"""Coarse matching (Layer 2).

Short-circuit cascade: metadata (prior only) -> fingerprint -> envelope
correlation -> transient/event matching -> No Match.
"""

from __future__ import annotations

from .cascade import CoarseConfig, cascade, coarse_match, coarse_match_paths
from .envelope import EnvelopeMatchConfig, envelope_match
from .fingerprint import FingerprintMatchConfig, fingerprint_match
from .metadata import metadata_match, overlap_estimate
from .transient import TransientMatchConfig, transient_match

__all__ = [
    "CoarseConfig",
    "EnvelopeMatchConfig",
    "FingerprintMatchConfig",
    "TransientMatchConfig",
    "cascade",
    "coarse_match",
    "coarse_match_paths",
    "envelope_match",
    "fingerprint_match",
    "metadata_match",
    "overlap_estimate",
    "transient_match",
]
