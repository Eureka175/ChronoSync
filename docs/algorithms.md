# Algorithms (Phase 1: GCC-PHAT)

## 1. GCC-PHAT mathematical definition

Input: two mono signals (internally float64, optional mean removal + RMS normalization):

```text
nfft = next_fast_len(len(ref) + len(tgt) - 1)     # zero padding → linear correlation, not circular
R = rfft(ref, nfft)                               # real FFT, halved memory
T = rfft(tgt, nfft)
G[k] = conj(R[k]) · T[k] / ( |R[k]|·|T[k]| + ε )  # PHAT whitening
gcc[j] = irfft(G, nfft)  ≈  Σ_n ref[n] · tgt[n + j]    (j ≤ nfft/2)
```

* Negative lag wrapping: `lag = j - nfft` (j > nfft/2).
* Valid lag range: `[-(len(tgt)-1), len(ref)-1]`; the search interval is automatically clipped to that range.
* Direction (ADR-003): `tgt[n] = ref[n-N]` ⇒ the `gcc` peak sits at `+N`.

### Regularized PHAT

```text
ε = ε_rel · max|G| + ε_abs       ε_rel = 1e-3, ε_abs = 1e-12 (defaults, both configurable)
```

A purely absolute floor (ε_rel = 0) whitens the spectral leakage / near-zero-frequency bins of a narrowband signal all the way to unit magnitude, so the GCC of signals such as a pure sine is entirely dominated by leakage (measured peak height 0.34 and wrong location).
The relative floor only whitens bins that carry "enough information" and leaves the remaining bins at their natural magnitude:
a wideband signal loses only about 1% of peak height (measured 0.90 vs theoretical 1.0), while a pure sine degenerates to its ordinary cross-correlation (location correct modulo the period, very small peak height, low confidence — the correct behaviour, see §4).

## 2. Peak policy (fine/peak.py)

"Global maximum = answer" is forbidden. The flow:

1. `scipy.signal.find_peaks` discovers candidates (distance=2); pad the window with `-inf`
   on both sides **before discovery** — scipy does not report peaks at the array edge
   (measured pitfall, fixed); a candidate must be strictly greater than both neighbours
   (eliminating padding-plateau spurious peaks), and prominence is computed on the original window.
2. Candidates are sorted by height descending; primary/secondary are selected by `PeakSelectionConfig`:
   * `exclusion_samples = 8`: the second peak must be ≥ 8 samples away from the primary;
   * optional **prior**: candidates whose height is within `(1 - prior_tolerance)` are
     re-ranked by distance to the prior (used in ambiguous cases such as periodic signals;
     the prior does not fabricate evidence, and confidence still reports measurement quality faithfully).
3. Sub-sample: parabolic interpolation (§3).

## 3. Sub-sample estimation (fine/subsample.py)

```text
delta = 0.5·(y[-1] - y[+1]) / (y[-1] - 2·y[0] + y[+1])   , clipped to [-0.5, +0.5]
peak  = y[0] - 0.25·(y[-1] - y[+1])·delta
```

**Scope statement**: parabolic interpolation is a numerical estimate, not a claim of absolute physical accuracy.
The benchmark (10 s/60 s pure delay, clean white noise) measured an error < 0.001 samples; that figure holds only for those specific conditions. Under noisy/reverberant conditions the error must be taken from the benchmark — the documentation does not promise "0.1 sample absolute accuracy".

## 4. Confidence (interpretable evidence)

`confidence = 0.3·height + 0.5·ratio + 0.2·prominence`, each term ∈ [0,1]:

| Evidence | Definition | Meaning |
| --- | --- | --- |
| height | `log10(v/nf) / log10(1/nf)`, `nf = √(2·ln nfft)/√nfft` (expected peak of a unit-magnitude random-phase spectrum) | how far the peak stands above the noise floor |
| ratio | `(r-1)/(r-1+0.5)`, `r = v/second_peak` | whether the peak is unique (ambiguity) |
| prominence | `prominence / v` | whether the peak is sharp |

ratio carries the largest weight: **peak ambiguity caused by periodic signals / echo chains is the most dangerous failure mode in delay estimation**. `success = v ≥ 2·nf`.

Known behaviours, pinned down by tests:

* Clean wideband signal: conf ≈ 0.95+, success ✓;
* SNR 0 dB: conf ≈ 0.6, location still accurate;
* Periodic signal (sparse comb spectrum): PHAT gives every bin an equal-weight vote ⇒ the
  peak height is naturally tiny (≈ occupied bins/nfft), `success=False` + conf < 0.6 +
  an "ambiguous" warning, but the location is still correct modulo the period; given a
  prior the location becomes exact (≈ ground truth) while confidence does not rise.
  — This is **correct, honest behaviour**: when GCC cannot resolve the ambiguity it must not
  pretend to succeed; the coarse matching / transient layer takes over.

## 5. Windowed measurement of drift (Phase 4 preview, pinned down by tests)

With white noise + 200 ppm drift, a single full-length GCC is **blind** to the drift (drift decorrelates the spectra
`R[k]` and `T[k] = R[k(1+p)]`, peak height ≈ 0.007, location random).
This is exactly why the drift layer must use short windows: while the within-window drift is < 2 samples,
`d(n) = ppm·1e-6·n` is measurable (the test `test_drift_ppm_gcc_sees_local_offset_in_short_windows`
measured an error < 1 sample in an 8192-sample window). The full flow of 30-60 s windows + 50% overlap → local
offset(t) → fit → TimeMap is implemented in Phase 4.

## 6. Key semantics of the synthetic framework

* `delay_samples(x, n)`: `y[n+k] = x[k]`, out-of-range content discarded, the other side
  zero-padded (the physical semantics of "the recording started later");
* `fractional_delay`: windowed sinc FIR (taps must be **odd** — an even-length kernel with
  `np.convolve(mode="same")` introduces a taps/2-sample shift, a measured pitfall, fixed)
  + integer shift; approximate at the boundaries, exact only in the interior;
* `drift_ppm(x, ppm)`: high-quality resampling by `(1+ppm·1e-6)` (soxr);
  ppm > 0 ⇒ the target clock is faster ⇒ `d(n) = ppm·1e-6·n`;
* `piecewise_drift`: each segment keeps its **natural drift length** (physically correct), with 5 ms cross-fades at the seams;
* every random draw is seeded, everything is reproducible.

---

## 7. Coarse cascade (Phase 3, coarse/)

Cascade order and short-circuit policy (every stage returns a `MatchResult`, never a bare float):

```text
metadata (only supplies a prior, never claims matched)
    → fingerprint (constellation landmark hashing + offset voting histogram)
    → envelope (decimated RMS envelope → 100 Hz decimation → normalized cross-correlation)
    → transient (offset voting histogram of spectral-flux transient events)
    → No Match
```

* **metadata**: file mtime difference as the search prior; duration/sample rate as evidence;
  never matched=True (BWF timecode parsing is left for later).
* **fingerprint** (features/fingerprint.py): STFT (11025 Hz working rate,
  fft 1024/hop 512) → **absolutely dB-calibrated** log-magnitude spectrum (input normalized to unit RMS,
  divided by window energy, a full-energy frame ≈ 0 dB — comparable across chunks and across files, gain-invariant) →
  2-D local maxima (21×11 neighbourhood, -45 dB threshold) → pairing within the target region
  (f1, f2, Δt) hashing → offset voting histogram + parabolic sub-frame refinement.
  * Chunked processing is **hash-for-hash identical** to a single-pass computation (±5 frames of context at block boundaries, measured fix).
  * Confidence = 0.7·vote-share score + 0.3·peak ratio, then multiplied by the min(1, votes/5) vote gate.
  * Accuracy: ±0.5 frame (@11025 Hz ≈ ±23 ms) — this is "coarse" localization; the drift layer refines it.
* **envelope**: envelope extracted to ~100 Hz (the envelope is already a smooth energy signal; block-mean
  decimation is not audio resampling and does not violate ADR-002) → scipy normalized
  cross-correlation (**note the direction: the scipy correlate peak = −d**, pinned down by measurement) → parabolic sub-sample.
* **transient**: spectral flux (chunked STFT, hop-aligned so that chunked == single-pass) → peaks
  → 10 ms bin weighted voting histogram.
* Cascade contract: return as soon as any stage is `matched` with `confidence ≥ accept_confidence`;
  on total failure return the best evidence + matched=False (never disguise success below the acceptance threshold).

## 8. Drift estimation (Phase 4, drift/)

```text
window schedule (reference timeline, 30-60 s default, 50% overlap, adaptive shrinking)
    → GCC per window (target window placed by the coarse offset → measure the residual; prior resolves ambiguity)
    → OffsetMeasurement sequence (records the full d(t))
    → robust weighted regression (MAD outlier rejection = "bad measurement")
    → changepoint detection (weighted SSE improvement of a two-segment fit ≥25% and step ≥100 samples or slope change ≥4 ppm)
    → classification: clock_drift / constant_offset / piecewise_drift /
             discontinuity / no_overlap
    → TimeMap (linear / constant / piecewise, flat segments modelled at the breakpoints)
```

**Key physical constraint (pinned down by measurement)**: PHAT whitening gives every frequency bin an equal-weight
vote; when the within-window drift exceeds about one coherence length, the spectra of noise-like signals
`R[k]` and `T[k]=R[k(1+p)]` decorrelate and the long-window GCC peak is washed out (a 60 s white-noise window @150 ppm is completely blind). Therefore:

* white-noise-like content needs short windows with `T < 1/(ppm·f_max)` (measured: 8192 samples @150 ppm
  → α error < 1 ppm);
* the estimator **shrinks the window adaptively** (default 30 s → halved → lower bound 0.5 s) until enough
  windows pass the confidence gate;
* 30 s windows + speech-like content (120 ppm) measured α error < 5 ppm, R² > 0.98.

**Drift vs breakpoint vs bad measurement vs no overlap**: an offset that varies over time does not automatically
equal clock drift — changepoint detection distinguishes steps (CLOCK_DISCONTINUITY, measured jump size accurate to
the sample) from slope changes (piecewise_drift, measured 250/-100 ppm two-segment α accurate to <1 ppm);
MAD outlier rejection reports bad windows separately; too few windows → no_overlap.

**Correction (optional rendering)**: `correct_track` uses SoXR asynchronous resampling to render the track onto the
global timeline (not a phase vocoder, not musical time-stretching); breakpoint flat segments output
silence; content before global 0 is discarded with a warning. Measured: for 150 ppm white noise the residual
GCC after correction is < 2 samples.

## 9. Adobe Audition SESX export (Phase 3+, export/sesx.py)

Research conclusions (docs/research/notes/sesx_format.md, community reverse engineering + validation against two
MIT production-grade writers): SESX is **checksum-free plain XML**; **all time fields are integer samples at the
session sample rate**; clips reference external WAVs through the `<files>` table (non-destructive).

Fidelity rules (honest statement):

* identity/constant-offset TimeMap → a single exact clip (integer samples);
* linear drift → stair-step approximation clips at a configurable granularity (Audition clips **cannot change
  speed**; the step error per chunk is ≤ ppm·chunk_seconds samples; exact correction goes through
  correct_track rendering);
* piecewise maps (breakpoints) → one clip per node interval, with flat segments becoming timeline gaps
  (missing content is not fabricated);
* negative global start points are trimmed automatically (the clip starts at 0, the source in-point moves forward).

## 10. Overlap / segment detection (Phase 5, overlap/)

A track's content = the **image set** of its TimeMap on the local timeline. Key distinction: the same timeline
≠ the same duration — a track with recording gaps is modelled as a **list of spans**
(each span = a local interval + an affine map; a gap cannot be expressed by a single monotonic local→global
function without fabricating content). Intersecting the image sets of two tracks → overlap segments.

* Official example (Track A 0-60 min; Track B records 0-10/20-40/50-60) → 3
  segments, each carrying both sides' local intervals (pinned down by tests);
* flat segments (drops) are excluded from the recorded spans; a local hole caused by a drop does not produce a global
  hole (content coverage stays continuous — a measured correction of an intuitive mistake).

## 11. Multi-track global solve (Phase 6, global_alignment/, ADR-011)

`min Σ w_ij (t_i - t_j - d_ij)²`, reference track = 0; normal equations solved per connected component;
residuals, outlier edges (>3×robust sigma), per-track confidence; optional IRLS (Huber reweighting,
measured to be significantly better than plain WLS under outlier-edge contamination). 50 tracks/1225 edges solve in ~12 ms.

## 12. Validation and confidence (Phase 7, validation/, ADR-012)

Residual GCC (silent windows skipped) · coherence · polarity (low MSC ≠ inverted polarity —
compare corr(x,y) vs corr(x,-y)) · weighted evidence aggregation (coarse 0.25 / drift R²
0.20 / residual 0.25 / coherence 0.15 / polarity 0.15).

* **GCC polarity-aware** (fine/): the correlation peak of an inverted-polarity pair is negative, and when the negative
  peak is clearly stronger (>1.2×) the correlation surface analysis is flipped and `polarity=-1` is returned — without it,
  drift estimation on inverted-polarity material fails entirely (measured);
* **validation runs on the corrected signal**: raw drift makes coherence collapse naturally
  (120 ppm/30 s measured MSC≈0.026), and a washed-out drift peak is not evidence of a mismatch.
