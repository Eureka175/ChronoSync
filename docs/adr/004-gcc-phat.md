# ADR-004: GCC-PHAT as the core of local fine alignment

**Status:** Accepted (2025, Phase 1)
**Impact:** fine/, drift/ (Phase 4), validation/ (Phase 7)

## Decision

The core tool for local high-precision alignment is GCC-PHAT:

```text
G[k] = conj(R[k])·T[k] / ( |R[k]|·|T[k]| + ε )
gcc  = irfft(G)
```

* Zero padding (nfft ≥ len(ref)+len(tgt)-1) guarantees **linear** correlation;
* The search interval is configurable and clipped to valid lags; the peak policy
  (height/prominence/second peak/ratio/prior) is documented in
  docs/algorithms.md §2;
* Sub-sample: parabolic interpolation (a numerical estimate, with no promise of
  absolute physical accuracy);
* `GCCResult` returns delay/peak/second_peak/prominence/confidence/search_range
  /success/warnings, never just a single float.

## Key parameters (all configurable, testable and sourced)

| Parameter | Default | Description |
| --- | --- | --- |
| `epsilon_rel` | 1e-3 | Relative whitening floor (×max|G|), suppresses the leakage whitening of narrowband signals |
| `epsilon_abs` | 1e-12 | Absolute divide-by-zero guard |
| `_MIN_PEAK_FLOOR_RATIO` | 2.0 | success = peak height ≥ 2× noise floor √(2·ln nfft)/√nfft |
| confidence weights | 0.3/0.5/0.2 | height / ratio / prominence (ambiguity carries the largest weight) |
| `exclusion_samples` | 8 | Minimum separation between the second peak and the primary |
| `prior_tolerance` | 0.2 | Height tolerance for prior re-ranking |

## Measured findings (pinned as tests)

1. `scipy.signal.find_peaks` **does not report peaks at the edges of the
   array** — when the search boundary is exactly the true peak it is missed; the
   implementation pads with `-inf` before peak finding and uses strict two-sided
   comparison to discard spurious peaks.
2. A purely absolute epsilon lets the GCC of a pure sine be dominated by
   truncation leakage (peak 0.34, wrong position); with a relative epsilon of
   1e-3 the peak height of broadband signals loses only ~1%, and the sine
   degrades correctly (success=False, position correct modulo the period, low
   confidence).
3. Periodic signals have a sparse spectrum, and PHAT votes with equal weight per
   frequency bin ⇒ the peak height is naturally ≈ (number of occupied
   bins)/nfft. The honest behaviour of GCC is to **report ambiguity and low
   confidence** rather than pretend success; the prior can give an exact
   position but does not raise confidence.
4. With white noise + 200 ppm drift, full-length GCC goes blind (drift
   decorrelates the spectrum); the drift layer must use short windows (Phase 4).

## Consequences

* drift/ and validation/ reuse the same GCC kernel and `GCCResult`;
* Thresholds must not be scattered around as magic constants — they all go
  through `PeakSelectionConfig` / named constants;
* Changing the confidence formula or the peak policy = changing this ADR +
  docs/algorithms.md + rerunning the benchmarks.
