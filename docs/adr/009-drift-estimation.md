# ADR-009: Drift estimation method

**Status:** Accepted (2025, Phase 4)
**Impact:** drift/, models/timemap.py

## Decision

```text
windowed GCC (the target window is placed at the coarse offset → measure the residual, the prior resolves ambiguity)
→ a sequence of OffsetMeasurement (recording the complete d(t) = residual + d0)
→ robust weighted regression (MAD outlier rejection)
→ changepoint detection → classification → TimeMap
```

## Details

1. **Window placement and residual measurement**: the target window is placed at
   `center + d0` and GCC measures the residual (numerically more stable);
   `OffsetMeasurement.offset_samples` records the **complete** d(t)
   (internal implementation details never leak out).
2. **Adaptive window shrinking**: PHAT votes with equal weight per frequency
   bin — for noise-like content, once the drift inside the window exceeds
   ~1 coherence length the windowed GCC goes blind (measured: a single window
   over 60 s of white noise @150 ppm fails completely). The default starts at
   30 s and, if fewer than 12 usable windows are found, halves down to a
   0.5 s floor.
3. **Changepoint detection = weighted SSE improvement + effect-size gate**: a
   split is made only when the SSE improvement of the two-segment fit is
   ≥ 25% and (the step is ≥ 100 samples or the slope change is ≥ 4 ppm). A
   pure SSE criterion false-splits on correlated noise from 50%-overlapping
   windows (measured: a constant-offset pair was cut into 3 segments). Steps
   and slope changes are detected uniformly: CLOCK_DISCONTINUITY (step) vs
   piecewise_drift (slope change).
4. **Sign and units**: `d(t) = α·t + β` (ADR-003, β in samples);
   `T_global = τ/(1+α) − β/(sr(1+α))`; in the constant case offset_seconds =
   −β/sr (measured; this fixed a sign error).
5. **TimeMap modelling at breakpoints**: at a breakpoint the two segments map
   to the same global instant → a flat segment (the gap of a drop or the
   repeated interval of an insert), rendered as silence/skipping during
   correction; a negative local jump (lost content) raises an explicit
   warning.
6. **Correction = SoXR asynchronous resampling** (the variable-rate capability
   of ADR-002), not a phase vocoder; content before global 0 is discarded with
   a warning.

## Consequences

* `correct_track` is an optional rendering step; the default output is still
  the TimeMap (non-destructive);
* the classification result (no_overlap/constant/clock_drift/piecewise/discontinuity)
  enters the evidence-weighted confidence chain (Phase 7);
* the short-window requirement for white-noise-like content is a physical
  constraint, pinned in tests through an explicit config.
