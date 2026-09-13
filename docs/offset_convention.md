# Offset sign convention (project-wide API specification)

**The single offset definition used throughout ChronoSync:**

```text
d = t_target - t_reference
```

**Semantics:**

* `d > 0`: the same event occurs **later** in `target` (target lags).
* `d < 0`: the same event occurs **earlier** in `target` (target leads).
* `d = 0`: the two are aligned.

**Units:** internally the unit is always **samples at the canonical 48 kHz
sample rate** (`samples`); when physical time is needed, divide by 48000 to get
seconds (`seconds`). Wherever an API exposes both `*_samples` and `*_seconds`
fields, the two must satisfy
`seconds = samples / 48000`.

## Relationship to the GCC-PHAT mathematical definition

The GCC implementation in this project computes
(see ADR-004 / docs/algorithms.md for details):

```text
gcc[j] = IFFT( conj(FFT(reference)) · FFT(target) )[j] ≈ Σ_n ref[n] · tgt[n + j]
```

If `tgt[n] = ref[n - N]` (target lags by N samples), `gcc` peaks at `j = +N`,
so `delay_samples = +N`, consistent with the convention above.

Note: the internal direction of `scipy.signal.correlate(a, v)` is opposite to
this project's — its peak appears at `-d` (the test
`test_matches_plain_cross_correlation_on_broadband_signal`
explicitly verifies this).

## Meaning per layer

| Layer | Object | Field | Direction |
| --- | --- | --- | --- |
| Coarse matching | `MatchResult` | `offset_samples` | `t_target - t_reference` |
| Fine alignment | `GCCResult` | `delay_samples` | `t_target - t_reference` |
| Drift | `DriftModel` | `d(t) = alpha_ppm·1e-6·t + beta_samples` | `t_target - t_reference` |
| Graph | `AlignmentEdge` | `offset_samples` | `t_target - t_source` |
| Global | `TrackAlignment` | `offset_samples` | relative to the graph reference track (the reference track is always 0) |
| Time mapping | `TimeMap` | `T_global = f(T_local)` | local → global |

## Enforcement of sign consistency

* Every model docstring references ADR-003;
* All JSON / CSV / CLI output reuses the model fields directly and defines no
  direction of its own;
* Tests assert the direction explicitly (e.g. `test_sign_antisymmetry`:
  `gcc(ref, tgt).delay ≈ -gcc(tgt, ref).delay`);
* The `delay_samples(x, n)` semantics of the synthetic data framework are
  `y[n+k] = x[k]` (for n > 0 the content appears later), strictly consistent
  with the convention.

**No new module may define its own offset direction; if a definition conflict is
found, this document is authoritative and the conflicting module must be fixed.**
