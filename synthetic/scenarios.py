"""Named end-to-end synthetic scenarios.

Every scenario returns a :class:`Scenario` with the reference/target pair,
the *expected* offset (ADR-003: ``d = t_target - t_reference``), a tolerance,
and optional confidence bounds so tests can assert more than "a number came
out". All scenarios are deterministic for fixed seeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from chronosync.io.wav import write_wav

from .delay import delay_samples, fractional_delay
from .drift import drift_ppm, piecewise_drift
from .echo import add_echo, schroeder_reverb
from .generators import (
    DEFAULT_SAMPLE_RATE,
    sine_wave,
    transient_train,
    white_noise,
)
from .noise import additive_gaussian

#: The GCC-PHAT implementation targets sub-sample estimates on clean
#: broadband signals, so the default integer-delay tolerance is < 1 sample.
TIGHT_TOLERANCE = 0.5


@dataclass
class Scenario:
    """A reproducible reference/target pair plus its ground truth."""

    name: str
    description: str
    reference: np.ndarray  # float32, canonical 48 kHz
    target: np.ndarray
    sample_rate: int = DEFAULT_SAMPLE_RATE
    expected_offset_samples: float | None = None  # None = "no valid answer"
    expected_offset_tolerance: float = TIGHT_TOLERANCE
    min_confidence: float | None = None  # optional lower bound on confidence
    max_confidence: float | None = None  # optional upper bound (e.g. unrelated)
    warnings: list[str] = field(default_factory=list)

    def write_wavs(self, directory: str | Path, prefix: str = "scenario") -> tuple[Path, Path]:
        """Write reference.wav / target.wav and return their paths."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        ref_path = directory / f"{prefix}_reference.wav"
        tgt_path = directory / f"{prefix}_target.wav"
        write_wav(ref_path, self.reference, self.sample_rate)
        write_wav(tgt_path, self.target, self.sample_rate)
        return ref_path, tgt_path


def _base_signal(duration_s: float, seed: int, sample_rate: int) -> np.ndarray:
    n = int(duration_s * sample_rate)
    return white_noise(n, seed=seed)


def scenario_fixed_delay(
    delay: int = 12_345, duration_s: float = 5.0, seed: int = 0
) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = delay_samples(ref, delay)
    return Scenario(
        name="fixed_delay",
        description=f"target = reference delayed by {delay} samples",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(delay),
        min_confidence=0.8,
    )


def scenario_zero_delay(duration_s: float = 5.0, seed: int = 0) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    return Scenario(
        name="zero_delay",
        description="identical signals",
        reference=ref,
        target=ref.copy(),
        expected_offset_samples=0.0,
        min_confidence=0.8,
    )


def scenario_negative_delay(
    delay: int = 12_345, duration_s: float = 5.0, seed: int = 0
) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = delay_samples(ref, -delay)
    return Scenario(
        name="negative_delay",
        description=f"target = reference shifted EARLIER by {delay} samples "
        "(negative offset per ADR-003)",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(-delay),
        min_confidence=0.8,
    )


def scenario_gain_difference(
    gain_db: float = -40.0, delay: int = 2_500, duration_s: float = 5.0, seed: int = 0
) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = delay_samples(ref, delay) * (10.0 ** (gain_db / 20.0))
    return Scenario(
        name="gain_difference",
        description=f"target attenuated by {-gain_db} dB (PHAT is gain-invariant)",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(delay),
        min_confidence=0.8,
    )


def scenario_additive_noise(
    snr_db: float = 10.0, delay: int = 2_500, duration_s: float = 5.0, seed: int = 0
) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = additive_gaussian(delay_samples(ref, delay), snr_db, seed=seed + 1)
    return Scenario(
        name="additive_noise",
        description=f"target = delayed reference + noise at SNR {snr_db} dB",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(delay),
        min_confidence=0.5,
    )


def scenario_echo(
    delay: int = 5_000, taps: list[tuple[int, float]] | None = None,
    duration_s: float = 5.0, seed: int = 0,
) -> Scenario:
    taps = taps if taps is not None else [(3_000, 0.6), (7_000, 0.35)]
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = add_echo(delay_samples(ref, delay), taps)
    return Scenario(
        name="echo",
        description="target = delayed reference + attenuated echo taps",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(delay),
        expected_offset_tolerance=1.0,
        min_confidence=0.6,
    )


def scenario_reverb(
    delay: int = 5_000, rt60_s: float = 0.8, wet: float = 0.25,
    duration_s: float = 5.0, seed: int = 0,
) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = schroeder_reverb(delay_samples(ref, delay), rt60_s=rt60_s, wet=wet)
    return Scenario(
        name="reverb",
        description="target = delayed reference through synthetic reverb "
        f"(RT60 {rt60_s} s, wet {wet})",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(delay),
        expected_offset_tolerance=1.0,
        min_confidence=0.5,
    )


def scenario_periodic(
    freq: float = 440.0, delay: int = 100, duration_s: float = 3.0, seed: int = 0
) -> Scenario:
    """Pure tone: GCC peaks repeat every ``sample_rate / freq`` samples.

    All peaks are equally valid, so the expected offset is only defined
    modulo the period — tests assert ``found ≡ delay (mod period)`` and a
    LOW confidence (ambiguity must be reported, not hidden).
    """
    ref = sine_wave(int(duration_s * DEFAULT_SAMPLE_RATE), freq)
    tgt = delay_samples(ref, delay)
    return Scenario(
        name="periodic",
        description=f"pure {freq} Hz sine, delay {delay} samples "
        "(ambiguous: peaks repeat every period)",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(delay),
        expected_offset_tolerance=DEFAULT_SAMPLE_RATE / freq,
        max_confidence=0.6,
        warnings=[f"period_samples={DEFAULT_SAMPLE_RATE / freq:.4f}"],
    )


def scenario_different_duration(
    ref_duration_s: float = 5.0,
    tgt_duration_s: float = 3.0,
    delay: int = 12_345,
    seed: int = 0,
) -> Scenario:
    """Target is a shorter recording of the same content (partial overlap).

    The target recorded only the first ``tgt_duration_s`` seconds of the
    reference and started ``delay`` samples later, so the expected offset is
    exactly ``+delay`` (ADR-003).
    """
    n_ref = int(ref_duration_s * DEFAULT_SAMPLE_RATE)
    ref = white_noise(n_ref, seed=seed)
    content = ref[: int(tgt_duration_s * DEFAULT_SAMPLE_RATE)]
    tgt = delay_samples(content, delay)
    return Scenario(
        name="different_duration",
        description=f"reference {ref_duration_s} s, target {tgt_duration_s} s "
        f"of the same content, delay {delay}",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(delay),
        min_confidence=0.8,
    )


def scenario_unrelated(duration_s: float = 5.0, seed: int = 0) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = _base_signal(duration_s, seed + 1, DEFAULT_SAMPLE_RATE)
    return Scenario(
        name="unrelated",
        description="two independent recordings (no common content)",
        reference=ref,
        target=tgt,
        expected_offset_samples=None,
        max_confidence=0.4,
    )


def scenario_fractional_delay(
    delay: float = 10.4, duration_s: float = 5.0, seed: int = 0
) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = fractional_delay(ref, delay)
    return Scenario(
        name="fractional_delay",
        description=f"target delayed by {delay} samples (band-limited fractional shift)",
        reference=ref,
        target=tgt,
        expected_offset_samples=delay,
        expected_offset_tolerance=0.15,
        min_confidence=0.8,
    )


def scenario_transients(
    delay: int = 9_876, duration_s: float = 5.0, seed: int = 0
) -> Scenario:
    ref = transient_train(int(duration_s * DEFAULT_SAMPLE_RATE), seed=seed)
    tgt = delay_samples(ref, delay)
    return Scenario(
        name="transients",
        description=f"sparse click train delayed by {delay} samples",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(delay),
        min_confidence=0.8,
    )


def scenario_clock_drift(
    ppm: float = 200.0, duration_s: float = 20.0, seed: int = 0
) -> Scenario:
    """Target clock runs ``ppm`` faster: d(n) = ppm*1e-6 * n.

    A single FULL-window GCC is blind to drift on white noise (drift
    decorrelates the spectrum) — the drift estimator therefore uses short
    windows where d(n) = ppm*1e-6 * n is locally measurable. The expected
    offset is the local offset at the overlap midpoint; tests must probe
    with a short window around it.
    """
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = drift_ppm(ref, ppm)
    mid = (min(len(ref), len(tgt)) / 2.0)
    expected = ppm * 1e-6 * mid
    return Scenario(
        name="clock_drift",
        description=f"target clock +{ppm} ppm over {duration_s} s "
        "(drift is estimated from short GCC windows)",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(expected),
        expected_offset_tolerance=3.0,
    )


def scenario_piecewise_drift(
    ppm1: float = 300.0, ppm2: float = -150.0, duration_s: float = 20.0, seed: int = 0
) -> Scenario:
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    half = duration_s / 2.0
    tgt = piecewise_drift(
        ref, [(0.0, half, ppm1), (half, duration_s, ppm2)]
    )
    return Scenario(
        name="piecewise_drift",
        description=f"+{ppm1} ppm then {ppm2} ppm (piecewise linear time map)",
        reference=ref,
        target=tgt,
        expected_offset_samples=float(ppm1 * 1e-6 * (half * DEFAULT_SAMPLE_RATE / 2)),
        expected_offset_tolerance=48.0,
    )


def scenario_discontinuity(
    jump: int = 4_800, at_s: float = 2.5, duration_s: float = 5.0, seed: int = 0
) -> Scenario:
    """Target drops ``jump`` samples mid-recording (CLOCK_DISCONTINUITY)."""
    ref = _base_signal(duration_s, seed, DEFAULT_SAMPLE_RATE)
    tgt = np.concatenate(
        [ref[: int(at_s * DEFAULT_SAMPLE_RATE)], ref[int(at_s * DEFAULT_SAMPLE_RATE) + jump :]]
    )
    return Scenario(
        name="discontinuity",
        description=f"target drops {jump} samples at t={at_s} s "
        "(Phase 4 must report CLOCK_DISCONTINUITY, not fit a line through it)",
        reference=ref,
        target=tgt,
        expected_offset_samples=0.0,
        expected_offset_tolerance=2.0,
    )


def all_scenarios() -> dict[str, Scenario]:
    """Registry of every scenario (used by tests, docs and demos)."""
    return {
        s.name: s
        for s in [
            scenario_fixed_delay(),
            scenario_zero_delay(),
            scenario_negative_delay(),
            scenario_gain_difference(),
            scenario_additive_noise(),
            scenario_echo(),
            scenario_reverb(),
            scenario_periodic(),
            scenario_different_duration(),
            scenario_unrelated(),
            scenario_fractional_delay(),
            scenario_transients(),
            scenario_clock_drift(),
            scenario_piecewise_drift(),
            scenario_discontinuity(),
        ]
    }
