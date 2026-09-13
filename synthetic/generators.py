"""Deterministic signal generators.

Every generator that uses randomness accepts a ``seed`` argument and draws
from ``numpy.random.default_rng(seed)``, so all tests are reproducible.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

DEFAULT_SAMPLE_RATE = 48_000


def white_noise(n: int, seed: int = 0, amplitude: float = 1.0) -> np.ndarray:
    """White Gaussian noise, float32."""
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) * float(amplitude)).astype(np.float32)


def sine_wave(
    n: int,
    freq: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    phase: float = 0.0,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Pure sine tone."""
    t = np.arange(n) / sample_rate
    return (amplitude * np.sin(2.0 * np.pi * freq * t + phase)).astype(np.float32)


def harmonic_stack(
    n: int,
    freqs: list[float],
    amps: list[float],
    phases: list[float],
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> np.ndarray:
    """Sum of sine partials (e.g. a periodic, non-sinusoidal drone)."""
    out = np.zeros(n, dtype=np.float64)
    for f, a, p in zip(freqs, amps, phases):
        out += a * np.sin(2.0 * np.pi * f * np.arange(n) / sample_rate + p)
    return out.astype(np.float32)


def chirp(
    n: int,
    f0: float,
    f1: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    method: str = "linear",
) -> np.ndarray:
    """Frequency sweep from f0 to f1."""
    t = np.arange(n) / sample_rate
    if method == "linear":
        phase = 2.0 * np.pi * (f0 * t + 0.5 * (f1 - f0) / t[-1] * t * t)
    elif method == "log":
        phase = 2.0 * np.pi * f0 * (t[-1] / np.log(f1 / f0)) * (
            np.power(f1 / f0, t / t[-1]) - 1.0
        )
    else:
        raise ValueError(f"unknown chirp method: {method!r}")
    return np.sin(phase).astype(np.float32)


def bandlimited_noise(
    n: int,
    low_hz: float,
    high_hz: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    seed: int = 0,
    order: int = 4,
) -> np.ndarray:
    """Broadband noise shaped to a frequency band (Butterworth band-pass)."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    sos = signal.butter(
        order, [low_hz, high_hz], btype="band", fs=sample_rate, output="sos"
    )
    y = signal.sosfilt(sos, x)
    y /= np.max(np.abs(y)) + 1e-12
    return y.astype(np.float32)


def transient_train(
    n: int,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    interval_s: float = 0.25,
    jitter_s: float = 0.05,
    decay_s: float = 0.02,
    seed: int = 0,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Trains of decaying impulses (clicks/percussion-like)."""
    rng = np.random.default_rng(seed)
    out = np.zeros(n, dtype=np.float64)
    t = 0.0
    decay = np.exp(-np.arange(int(decay_s * sample_rate)) / (decay_s * sample_rate / 5.0))
    while t < n / sample_rate:
        pos = int(t * sample_rate)
        if pos < n:
            m = min(len(decay), n - pos)
            sign = 1.0 if rng.random() < 0.5 else -1.0
            amp = amplitude * rng.uniform(0.5, 1.0)
            out[pos : pos + m] += sign * amp * decay[:m]
        t += interval_s + rng.uniform(-jitter_s, jitter_s)
    out /= np.max(np.abs(out)) + 1e-12
    return out.astype(np.float32)


def speech_like(
    n: int,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    seed: int = 0,
    burst_rate: float = 3.5,
    amplitude: float = 0.8,
) -> np.ndarray:
    """Pseudo-speech: band-limited noise gated by random syllable bursts.

    Good stand-in for speech for alignment tests: broadband content plus a
    strongly time-varying envelope.
    """
    rng = np.random.default_rng(seed)
    carrier = bandlimited_noise(n, 100.0, 4000.0, sample_rate, seed=seed + 1)

    envelope = np.zeros(n, dtype=np.float64)
    t = 0.0
    while t < n / sample_rate:
        start = int(t * sample_rate)
        dur = rng.uniform(0.08, 0.4)
        m = int(dur * sample_rate)
        if start < n and m > 0:
            k = np.arange(min(m, n - start))
            tau = dur * sample_rate / 3.0
            env = rng.uniform(0.4, 1.0) * np.exp(-k / tau)
            envelope[start : start + len(k)] += env
        t += rng.uniform(0.15, 0.6) + dur
    envelope = np.minimum(envelope, 1.0)

    out = amplitude * carrier * envelope.astype(np.float32)
    out /= np.max(np.abs(out)) + 1e-12
    return out.astype(np.float32)
