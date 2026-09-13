# ADR-012: Validation and explainable confidence

**Status:** Accepted (2025, Phase 7)
**Impact:** validation/, fine/gcc_phat.py

## Decision

A validation quartet + evidence aggregation:

1. **Residual GCC**: run GCC again after correction, in theory close to
   0 samples; silent windows are skipped (GCC cannot measure silence) and GCC
   failures are skipped — a NaN is never treated as evidence;
2. **coherence (MSC)**: Welch-averaged periodogram, mean over 80-8000 Hz;
3. **polarity**: compare `corr(x,y)` against `corr(x,-y)`; inversion is
   declared only when the inverted correlation coefficient is **clearly
   higher** (margin 0.1) — **low MSC is NOT inversion** (measured and pinned:
   unrelated content shows MSC<0.05 yet polarity=0);
4. **confidence = evidence-weighted** (coarse 0.25 / drift R² 0.20 / residual
   0.25 / coherence 0.15 / polarity 0.15); missing evidence is dropped and the
   weights renormalized, with a warning.

## Details

* **GCC polarity awareness** (a Phase 7 prerequisite, changed in
  fine/gcc_phat.py): the correlation peak of an inverted pair is **negative** —
  when |negative peak| > positive peak×1.2 the correlation-surface analysis is
  flipped and `polarity=-1` plus a warning is returned. Without it, drift
  estimation on inverted pairs fails wholesale (coarse matching is an amplitude
  fingerprint so it passes, while every drift window fails — measured).
* **Validation runs on the "corrected" signal**: on a raw pair with drift still
  present, coherence collapses naturally (>277 Hz fully decorrelated at
  120 ppm/30 s; measured MSC≈0.026) — drift smoothing is not evidence of
  mismatch. validate_pair therefore renders through correct_track (SoXR)
  first and measures afterwards, so the evidence semantics are correct.

## Consequences

* the evidence dictionary is emitted with the report (JSON-serializable), with
  no magic-number confidence;
* inversion is caught by both the drift and the validation layers: a GCC
  warning → a POLARITY INVERSION line in the validation report;
* the coherence/polarity checks on the corrected rendering cover both linear
  and piecewise maps (flat segments emit silence, which coherence reflects
  naturally).
