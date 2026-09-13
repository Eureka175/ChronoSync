# ADR-005: TimeMap time-mapping abstraction

**Status:** Accepted (2025, Phase 1, models first)
**Impact:** models/timemap.py, drift/ (Phase 4), export/ (Phase 9), all business code

## Decision

Every recording is not an offset but a mapping:

```text
T_global = f_i(T_i)      # unit: seconds (both sides)
```

* `identity`: T_global = T_local
* `constant_offset`: T_global = T_local + offset_seconds
* `linear`: T_global = scale·T_local + offset_seconds (scale = 1 + ppm·1e-6)
* `piecewise_linear`: piecewise linear over (t_local, t_global) knots, with linear extrapolation beyond the end knots

Business code depends on the `TimeMap` interface (to_global / to_local / to_dict /
from_dict / is_identity) and **must not** manipulate offset / alpha / beta directly.

## Rationale

Fixed offset, clock drift, local discontinuities (CLOCK_DISCONTINUITY) and
segmented drift are different complexity forms of the same kind of thing. Once
they are unified as a TimeMap, drift estimation, graph solving, export and
correction rendering all face a single abstraction.

## Details

* Sample ↔ second conversion happens only at the boundary (`to_global_samples` /
  `to_local_samples`, canonical sample rate 48 kHz);
* piecewise knots must have strictly increasing t_local and monotonically
  non-decreasing t_global (which guarantees invertibility);
* serialization through `to_dict`/`from_dict` supports JSON export and caching;
* `DriftModel` (d(t) = alpha_ppm·1e-6·t + beta_samples) is the measurement-layer
  model and converts losslessly into
  `LinearTimeMap(scale=1+alpha_ppm·1e-6, offset=beta/sr)`;
* segmented drift/discontinuities are not forced into the linear model — the
  model kind (linear vs piecewise) is decided by the Phase 4 estimator from the
  residual structure.

## Consequences

* New mapping types in the future (e.g. splines) only need to implement the
  interface + extend the from_dict dispatch;
* DAW export emits the non-destructive timeline of TimeMap/segments (Phase 9);
* correction rendering (an optional feature) is TimeMap-driven and performs
  high-quality asynchronous resampling; no phase vocoder by default.
