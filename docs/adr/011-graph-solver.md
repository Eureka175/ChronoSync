# ADR-011: Multi-track global graph solve

**Status:** Accepted (2025, Phase 6)
**Impact:** global_alignment/, pipeline.py, export/

## Decision

```text
tracks = nodes; measurements = weighted directed edges (ADR-003)
min Σ w_ij (t_i - t_j - d_ij)^2,  reference track pinned at 0
```

* Reference track: explicitly specified or chosen automatically as the
  "most connected" track (largest Σ of incident-edge confidence);
* **connected components are solved independently**: components not connected
  to the reference track are anchored on their own and **warned about loudly**
  — the solver never silently mixes unrelated timelines;
* every edge reports a residual; edges with |residual| > 3×robust sigma
  (MAD scale) are flagged as outliers;
* per-track confidence = the (confidence-weighted) agreement of the incident
  edges: `agreement = 1 - |residual|/(3σ)`, and the reference track is always
  1;
* optional **IRLS** (`irls_iterations > 0`): Huber-style reweighting
  iterations, in which outlier edges lose their influence; measured, the IRLS
  solution is significantly better than plain WLS under outlier-edge
  contamination. Beyond Huber/IRLS (RANSAC and friends) is deliberately
  deferred — the first version does not over-engineer.

## Details

* The normal equations are built per component: free nodes A·t = b, with the
  reference-track terms moved to the RHS; a singular system falls back to
  least squares with a warning;
* tracks without measurement edges **do not appear in the graph** — the
  pipeline reports them explicitly ("matched nothing; excluded") and never
  places them silently;
* tracks not measured directly against the reference track are placed using
  the solved constant offset, with a warning (composing TimeMaps across
  unmeasured pairs is documented future work).

## Consequences

* Edge direction/sign follows ADR-003; the solver performs no direction
  inference of its own;
* benchmark: WLS solve over 50 tracks / 1225 edges ≈ 12 ms — multi-track scale
  is not the bottleneck;
* residuals and per-track confidence flow directly into the Phase 7 evidence
  chain and the JSON/CSV export.
