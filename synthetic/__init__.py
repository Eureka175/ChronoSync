"""Synthetic test-data framework.

The most important infrastructure of ChronoSync: every synthetic generator
is deterministic (seeded) and follows the project-wide offset convention
(ADR-003), so tests and benchmarks are reproducible by construction.

Modules:

* :mod:`synthetic.generators` — base signals (noise, tones, chirps, transients)
* :mod:`synthetic.delay` — integer / fractional time shifts
* :mod:`synthetic.noise` — additive noise
* :mod:`synthetic.echo` — echo taps and synthetic reverb
* :mod:`synthetic.drift` — clock drift, piecewise drift, discontinuities
* :mod:`synthetic.scenarios` — named end-to-end test scenarios
"""

from __future__ import annotations

from . import delay, drift, echo, generators, noise, scenarios
from .delay import delay_samples, fractional_delay
from .drift import drift_ppm, piecewise_drift, drop_samples, insert_samples
from .echo import add_echo, schroeder_reverb
from .generators import (
    bandlimited_noise,
    chirp,
    harmonic_stack,
    sine_wave,
    speech_like,
    transient_train,
    white_noise,
)
from .noise import additive_gaussian, gaussian_noise
from .scenarios import Scenario

__all__ = [
    "Scenario",
    "add_echo",
    "additive_gaussian",
    "bandlimited_noise",
    "chirp",
    "delay",
    "delay_samples",
    "drift",
    "drift_ppm",
    "drop_samples",
    "echo",
    "fractional_delay",
    "gaussian_noise",
    "generators",
    "harmonic_stack",
    "insert_samples",
    "noise",
    "piecewise_drift",
    "scenarios",
    "schroeder_reverb",
    "sine_wave",
    "speech_like",
    "transient_train",
    "white_noise",
]
