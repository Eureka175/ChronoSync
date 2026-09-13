"""Feature extraction (Layer 1).

* :mod:`chronosync.features.envelope` — RMS energy envelope
* :mod:`chronosync.features.spectral` — spectral flux + transient detection
* :mod:`chronosync.features.fingerprint` — constellation fingerprinting

Every feature is versioned (``ALGO_VERSION`` / ``FEAT_VERSION``) so the
feature cache (ADR-006) can invalidate entries when the algorithm or the
feature definition changes.
"""

from __future__ import annotations

from .envelope import EnvelopeConfig, decimate_envelope, envelope, envelope_rate
from .fingerprint import (
    Fingerprint,
    FingerprintConfig,
    FingerprintMatch,
    compute_fingerprint,
    match_fingerprints,
)
from .spectral import SpectralConfig, spectral_flux, transient_map

ENVELOPE_ALGO_VERSION = "envelope@1"
ENVELOPE_FEAT_VERSION = 1
FLUX_ALGO_VERSION = "flux@1"
FLUX_FEAT_VERSION = 1
TRANSIENT_ALGO_VERSION = "transient@1"
TRANSIENT_FEAT_VERSION = 1
FINGERPRINT_ALGO_VERSION = "fingerprint@1"
FINGERPRINT_FEAT_VERSION = 1

__all__ = [
    "EnvelopeConfig",
    "decimate_envelope",
    "envelope",
    "envelope_rate",
    "Fingerprint",
    "FingerprintConfig",
    "FingerprintMatch",
    "compute_fingerprint",
    "match_fingerprints",
    "SpectralConfig",
    "spectral_flux",
    "transient_map",
    "ENVELOPE_ALGO_VERSION",
    "ENVELOPE_FEAT_VERSION",
    "FLUX_ALGO_VERSION",
    "FLUX_FEAT_VERSION",
    "TRANSIENT_ALGO_VERSION",
    "TRANSIENT_FEAT_VERSION",
    "FINGERPRINT_ALGO_VERSION",
    "FINGERPRINT_FEAT_VERSION",
]
