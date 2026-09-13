# Changelog

All notable changes to this project are documented in this file.
Versions follow [PEP 440](https://peps.python.org/pep-0440/) (`0.1.0b0` is
released as `v0.1.0-beta`).

## [v0.1.0-beta.1] — 2026-09-03

CI-verified build: adds the two MP4 multi-stream robustness fixes that CI
(Linux / FFmpeg 6) exposed and that were then located and fixed. Green on
Python 3.12 and 3.13 (202 tests each).

### Fixed

1. **Per-stream MP4 head trimming biasing delay measurements.** Some FFmpeg
   versions change a stream's content start when muxing/decoding multichannel
   PCM into MP4 (measured: 305 samples), which silently skews "small delay"
   conclusions. Extraction now always passes `-ignore_editlist 1`, and the
   container `start_time` is reported as information only (never added to the
   delay, to avoid double counting).
2. **Container anomaly detection.** `measure_file` now verifies that all
   streams of one recording decode to equal sample counts; unequal lengths are
   reported as a container anomaly with the warning "bias = trimmed samples"
   on every channel instead of returning a shifted number silently.
3. Integration tests restructured into a container-agnostic three-layer
   validation (invariants + comparison against an independent scipy
   cross-correlation reference + absolute assertions only when the container
   preserved the fixture), so muxing differences are no longer mistaken for
   algorithm defects.

### Handoff package

`handoff/mp4_channel_sync/` (pure numpy+scipy algorithm package) documents the
new integration requirements: decode with `-ignore_editlist 1` and verify that
all streams decode to equal sample counts before trusting the measured delays.

## [v0.1.0-beta] — 2026-09-03

First public beta: from prior-art research to the complete Phase 1–7
implementation, including a real-footage-validated wireless-microphone channel
sync pipeline.

### Added — core algorithms

* **Layer 0 · I/O**: `probe` / canonical decoding (48 kHz float32,
  clip-weighted channel downmix) / SoXR resampling / streaming chunks
* **Layer 1 · Features & cache**: RMS envelope, spectral flux + transients,
  constellation fingerprint (chunked == single-shot, absolute dB scale,
  gain-invariant); SQLite index + `.npy` file-based feature cache (ADR-006)
* **Layer 2 · Coarse cascade**: metadata (prior) → fingerprint → envelope →
  transient short-circuit cascade returning a full `MatchResult` (ADR-008)
* **Layer 3 · Fine alignment**: GCC-PHAT (regularized whitening, peak policy,
  search prior, parabolic sub-sample, **polarity-aware**) and interpretable
  confidence (ADR-004 / ADR-012)
* **Layer 4 · Drift**: windowed GCC (adaptive shrink 30 s → 0.5 s) → robust
  weighted regression → changepoint detection / classification (clock_drift /
  constant_offset / piecewise_drift / discontinuity / no_overlap) → TimeMap +
  SoXR correction render (ADR-009)
* **Layer 5 · Multi-track**: overlap / segment detection (recording gaps →
  multiple segments); global graph solver WLS/IRLS (reference pinned at 0,
  independent connected components, edge residuals, per-track confidence,
  ADR-011)
* **Layer 6 · Validation**: residual GCC, coherence, polarity (low MSC ≠
  polarity inversion), evidence-weighted confidence (ADR-012)
* **Layer 7 · Export**: Adobe Audition **SESX** (integer-sample time units,
  stair-step approximation, non-destructive, ADR-010), JSON, CSV

### Added — tooling and deliverables

* CLI: `info` / `gcc` / `align` / `batch` / `mp4-sync` / `test-gcc` / `benchmark`
* `chronosync.mp4sync`: multi-stream MP4 wireless-mic delay measurement,
  sample-accurate correction, remux and re-verification
* **`handoff/mp4_channel_sync/`**: standalone algorithm package for external
  tools (numpy+scipy only) with full documentation and an independent self-test
* Synthetic framework: seeded data (delay / drift / echo / reverb / noise /
  transients / pseudo-speech + 15 scenarios)
* Benchmarks: GCC / features / drift / graph solve (wall / CPU / peak RSS +
  accuracy)

### Testing

* **202 pytest** (unit + integration) green; the handoff package has 16
  additional standalone assertions
* Real-footage validation: 19 4K MP4 files (4×mono PCM); per-file wireless-mic
  delay measured at 19.7–29.5 ms (constant within a file, varying across
  files); post-correction verification residual < 0.05 ms

### Documentation

* `docs/architecture.md`, `docs/algorithms.md`, `docs/offset_convention.md`
* `docs/research/`: prior-art difference matrix + 6 sourced research notes
  (AudioAlign, Aurio, audalign, alignaudio, WhisperSync, audio stack, SESX)
* `docs/adr/001`–`012`: Python-first, canonical audio format, offset sign
  convention, GCC-PHAT, TimeMap, cache design, prior-art analysis, coarse
  cascade, drift estimation, SESX export, graph solver, validation & confidence
* `docs/mp4_wireless_delay_case.md`: real wireless-mic delay case study

### Known limitations

* TimeMap composition between tracks that were not measured directly is not
  implemented yet (a constant solved offset is used, with a warning)
* Reaper RPP export is not implemented (SESX cannot express a variable-rate
  timeline)
* Large-scale real-world benchmark (Phase 8) is still pending
