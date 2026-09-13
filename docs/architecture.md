# Architecture (Phase 1)

## Core idea

ChronoSync is not "a tool that finds the offset between two WAVs". The core
object of the system is the **TimeMap**: every recording is a mapping from the
device's local timeline onto a unified reference timeline

```text
T_global = f_i(T_i)
```

Fixed offset, clock drift and local discontinuities are all unified as a TimeMap
(identity / constant_offset / linear / piecewise_linear).
Business code depends on the `TimeMap` interface and never manipulates
offset / alpha / beta directly.

## Logical layers

```text
Layer 0  Input / Decode / Canonicalization     io/          ✅ Phase 1
Layer 1  Feature Extraction / Cache            features/    ✅ Phase 3
                                                 cache/       ✅ Phase 3 (ADR-006)
Layer 2  Coarse Matching                       coarse/      ✅ Phase 3 (ADR-008)
Layer 3  Fine Alignment (GCC-PHAT)             fine/        ✅ Phase 1 (+polarity-aware, ADR-012)
Layer 4  Drift / TimeMap Estimation            drift/       ✅ Phase 4 (ADR-009)
Layer 5  Multi-track Global Optimization       global_alignment/ ✅ Phase 6 (ADR-011)
         Overlap / Segmentation                overlap/     ✅ Phase 5
Layer 6  Validation / Confidence / Anomaly     validation/  ✅ Phase 7 (ADR-012)
Layer 7  Export                                export/      ✅ SESX + JSON/CSV (ADR-010); RPP ⏳
```

The layers are conceptual; module boundaries are authoritative in the code, and
files are not split artificially just to fill a "seven-layer" scheme.

## Data flow (implemented part)

```text
WAV/BWF/RF64/FLAC/...
        │  io.probe (metadata, no decoding)
        ▼
io.read_canonical ──► DecodedAudio          (float32 @ 48 kHz, channel-weighted mono_mix)
        │  long files: io.iter_chunks streaming chunks
        ▼
features/  envelope · spectral flux/transient · constellation fingerprint
        │  cache/  SQLite index + .npy arrays (ADR-006)
        ▼
coarse/   metadata(prior) → fingerprint → envelope → transient short-circuit cascade
        │  MatchResult (matched/offset/confidence/method/overlap/evidence)
        ▼
drift/    windowed GCC (adaptive shrink 30s→0.5s) → robust regression → change-point detection/classification
        │  DriftEstimate → TimeMap (constant/linear/piecewise)
        ▼
pipeline.py  batch_align: all-pairs measurement → AlignmentGraph
        ▼
global_alignment/  WLS solve (reference track = 0, independent connected components, edge residuals, per-track confidence, IRLS)
        ▼
overlap/    TrackContent spans → overlap Segment (recording gaps → multiple segments)
validation/ residual GCC · coherence · polarity · interpretable confidence aggregation
        ▼
export/sesx.py non-destructive multi-track timeline (integer samples)
export/json.py + csv.py  alignment report
drift/correct_track  optional render (SoXR asynchronous resampling onto the global timeline)
```

## Package layout (src layout)

```text
src/chronosync/
├── models/       data models (the single data-exchange contract)
│   ├── audio.py      AudioTrack / DecodedAudio / canonical format constants
│   ├── match.py      MatchResult
│   ├── alignment.py  AlignmentEdge / AlignmentGraph / TrackAlignment
│   ├── drift.py      OffsetMeasurement / DriftModel
│   └── timemap.py    TimeMap family (core abstraction)
├── io/           Layer 0: probe / decoder / resampler / wav
├── features/     Layer 1: envelope / spectral / fingerprint (versioned)
├── cache/        Layer 1: SQLite index + file-backed arrays (ADR-006)
├── coarse/       Layer 2: cascade (ADR-008)
├── fine/         Layer 3: gcc_phat (polarity-aware) / peak / subsample
├── drift/        Layer 4: windows / regression / estimator / timemap
├── global_alignment/  Layer 5: solver (WLS/IRLS, ADR-011) + robust
├── overlap/      Layer 5: segments / detector (no ADR assigned, see algorithms §10)
├── validation/   Layer 6: residual / coherence / polarity / confidence (ADR-012)
├── export/       SESX (ADR-010) + JSON / CSV
├── pipeline.py   multi-track orchestration (align_pair / batch_align)
└── cli/          command-line entry point (info/gcc/align/batch/test-gcc/benchmark)

synthetic/        reproducible synthetic data framework (top-level package, seeded)
benchmarks/       benchmarks (gcc/features/drift/solve, wall/CPU/peak memory + accuracy)
tests/            unit / integration
docs/             architecture / algorithms / offset_convention / research / adr
```

## Long files and cache design (implemented, ADR-006)

* Short files: loaded into RAM in one piece (`read_canonical`);
* Long files: `iter_chunks` streaming + SQLite index + `.npy/.npz` file-backed
  feature cache
  (large arrays must never go into SQLite BLOBs; keys include path/size/mtime/optional hash/algorithm version/feature version).
* A single full-length GCC is O(N log N) with memory ≈ 16 B/sample × several FFT
  buffers — files longer than a few minutes must use windowed GCC (the drift
  estimator mode); the benchmark is designed accordingly
  (see benchmarks/benchmark_gcc.py).

## Dependency policy

```text
Python 3.12+            (this project is developed and verified on 3.14)
numpy / scipy           core (scipy.fft, scipy.signal)
soundfile / libsndfile  decoding (WAV/BWF/RF64/FLAC, chunked reads)
soxr                    high-quality resampling (fallback: scipy.signal.resample_poly + warning)
pytest                  tests
psutil                  benchmark peak memory
```

* `np.interp` is forbidden as an audio resampling method (ADR-002);
* Numba / pybind11 / C++ are introduced only after profiling proves them
  necessary (ADR-001).

## Next steps (Phase 8+)

1. Phase 8: real-recording benchmark (end-to-end evaluation on on-location
   multi-camera footage: accuracy/duration/memory);
2. Phase 9: Reaper RPP export (carrying variable-speed maps that SESX cannot
   express) + TimeMap composition between pairs that were not measured directly;
3. Phase 10: GUI.
