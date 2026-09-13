# ADR-003: Global offset sign convention

**Status:** Accepted (2025, Phase 1)
**Impact:** docstrings, type names, JSON, CSV, tests, CLI and documentation of every module

## Decision

The one project-wide offset definition:

```text
d = t_target - t_reference
```

`d > 0` ⇔ the same event occurs **later** in the target.

## Rationale

Sign direction is the most insidious source of systematic bugs (an alignment
result reversed wholesale, a drift slope with the wrong sign, a diverging graph
solve). Define it centrally once, and have every other module reference it.

## Details

* The GCC implementation uses `gcc[j] = IFFT(conj(R)·T)[j] ≈ Σ ref[n]·tgt[n+j]`,
  keeping `delay_samples` consistent with the definition (+N ⇔ target lags by N).
  Note that `scipy.signal.correlate(a, v)` points the opposite way; the tests
  pin that contrast explicitly.
* `TimeMap` (ADR-005) uses `T_global = f(T_local)`, in seconds; sample
  conversion is performed only at the boundaries, using the canonical sample
  rate.
* The synthetic framework's `delay_samples(x, n)` with the semantics
  `y[n+k] = x[k]` agrees strictly with the convention.
* Unit tests pin the direction: `gcc(ref,tgt).delay ≈ -gcc(tgt,ref).delay`.

## Consequences

* No new module may define its own direction; in case of conflict this ADR
  prevails and the conflicting module is fixed.
* External outputs (CLI/JSON/CSV) reuse the model fields directly, avoiding any
  second interpretation.
