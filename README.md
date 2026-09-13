# ChronoSync

**v0.1.0-beta** · MIT · Python 3.12+ · [中文文档](README.zh-CN.md)

> Multi-track audio **timebase estimation**, **automatic alignment** and
> **clock-drift correction** for independent recorders, multi-camera location
> sound and long-duration recordings.

ChronoSync is not "yet another tool that finds the offset between two WAVs".
Its core object is not an offset but a **TimeMap**:

```text
T_global = f_i(T_i)
```

Every recording is a mapping from the device's local timeline onto a unified
reference timeline — the simplest case being `T = a·t + b` (`a` = clock
scale/drift, `b` = fixed offset), with piecewise-linear maps covering
segmented drift and local discontinuities. Fixed offsets, clock drift and
CLOCK_DISCONTINUITY are all expressed through one abstraction.

```text
independent recorders → find shared content / overlap → coarse locate
→ local high-precision alignment → estimate clock drift → per-track time map
→ multi-track global constraint solve → detect anomalies / discontinuities /
unreliable measurements → validate → unified timeline → DAW project export
```

## Status: Phases 1–7 complete

Delivered: Phase 1 (skeleton / GCC-PHAT / CLI), Phase 3 (features / cache /
coarse cascade), Phase 4 (drift estimation / TimeMap / correction),
**Adobe Audition SESX export**, **Phase 5 (overlap/segments)**,
**Phase 6 (multi-track graph solver)**, **Phase 7 (validation & confidence)**,
JSON/CSV export, the `batch` multi-track CLI, and a dedicated **MP4
wireless-microphone channel-sync pipeline**.

| Component | Status |
| --- | --- |
| Prior-art research (AudioAlign/Aurio/audalign/alignaudio/WhisperSync/audio stack/SESX) | ✅ `docs/research/` |
| Core data models (AudioTrack/MatchResult/GCCResult/DriftModel/TimeMap/AlignmentEdge/AlignmentGraph/TrackAlignment) | ✅ `src/chronosync/models/` |
| I/O (probe / decode / SoXR resampling / streaming chunks) | ✅ `src/chronosync/io/` |
| Synthetic framework (seeded, 15 scenarios) | ✅ `synthetic/` |
| GCC-PHAT (regularized whitening, peak policy, search prior, sub-sample, **polarity-aware**, interpretable confidence) | ✅ `src/chronosync/fine/` |
| Features + feature cache (ADR-006) | ✅ `features/` + `cache/` |
| Coarse-matching cascade (ADR-008) | ✅ `src/chronosync/coarse/` |
| Drift estimation + SoXR correction (ADR-009) | ✅ `src/chronosync/drift/` |
| Overlap / segment detection (recording gaps → multiple segments) | ✅ `src/chronosync/overlap/` |
| Multi-track graph solver (WLS/IRLS, connectivity, residuals, per-track confidence, ADR-011) | ✅ `src/chronosync/global_alignment/` |
| Validation (residual GCC / coherence / polarity / evidence-based confidence, ADR-012) | ✅ `src/chronosync/validation/` |
| Export: SESX (ADR-010) + JSON + CSV | ✅ `src/chronosync/export/` |
| Multi-track orchestration (`batch_align`: all-pairs → graph solve → export) | ✅ `src/chronosync/pipeline.py` |
| MP4 wireless-mic channel sync (measure → fix → remux → verify) | ✅ `src/chronosync/mp4sync/` |
| Unit / integration tests (**202 pytest + 16 standalone**) | ✅ `tests/`, `handoff/` |
| Benchmarks (gcc / features / drift / solve) | ✅ `benchmarks/` |
| CLI (`info` / `gcc` / `align` / `batch` / `mp4-sync` / `test-gcc` / `benchmark` / `--json`) | ✅ `chronosync` |
| External-tool handoff package (numpy+scipy only) | ✅ `handoff/mp4_channel_sync/` |
| Reaper RPP export / large-scale real-world benchmark | ⏳ Phase 8–9 |

## Install

```bash
pip install -e ".[io,dev]"     # Python 3.12+
```

Dependencies: numpy, scipy (required); soundfile + soxr (optional, recommended
for I/O); pytest, psutil (dev/benchmark). FFmpeg (any modern build) is needed
only for the MP4 pipeline and the corresponding integration tests.

## Quick start

```bash
# Build an acceptance pair (target = reference delayed by 12345 samples)
python scripts/generate_demo_pair.py demo

# Metadata / local GCC-PHAT
chronosync info demo/reference.wav
chronosync gcc demo/reference.wav demo/target.wav

# Full two-track pipeline: coarse → drift → TimeMap → SESX (optional)
chronosync align demo/reference.wav demo/target.wav --json
chronosync align demo/reference.wav demo/target.wav --sesx session.sesx

# Multi-track: all-pairs measurement → graph solve → JSON/CSV/SESX
chronosync batch a.wav b.wav c.wav --json --csv align.csv --sesx session.sesx

# MP4 wireless-mic channel sync (per-file delays + optional fix/remux with verification)
chronosync mp4-sync --folder D:\footage --json delays.json --csv delays.csv
chronosync mp4-sync clip.MP4 --fix --remux --out-dir fixed

# Self-check and benchmarks
chronosync test-gcc
chronosync benchmark --suite all        # gcc / features / drift / solve
```

Multi-track output example:

```text
Status:     success
Reference:  a.wav
  a.wav                 offset        0.0 samples  conf 1.000  map identity
  b.wav                 offset     2003.4 samples  conf 0.961  map linear
  c.wav                 offset    -2998.1 samples  conf 0.940  map constant_offset
```

## Project conventions (mandatory)

* **Offset sign (ADR-003)**: `d = t_target - t_reference`; `d > 0` means the
  event occurs later in the target. Applied consistently across docstrings,
  JSON, CSV, tests and the CLI.
* **Canonical audio format (ADR-002)**: 48 kHz / float32 / quality-weighted
  `mono_mix` (left/right retained); resampling only via SoXR (`np.interp` is
  forbidden for audio).
* **GCC peak policy (ADR-004)**: never "global maximum = answer"; confidence
  comes from interpretable evidence (peak height / peak ratio / prominence),
  and every threshold is configurable.
* **TimeMap (ADR-005)**: business code depends on the mapping interface, never
  on raw offset/alpha fields.
* **Testing discipline**: define the mathematical behaviour → write the test →
  implement → benchmark; tests are never weakened to hide a defect.

## Documentation

| Document | Content |
| --- | --- |
| `docs/README.md` | Documentation index |
| `docs/architecture.md` | Layered architecture, data flow, package layout, dependency policy |
| `docs/algorithms.md` | All algorithms: GCC-PHAT, peak policy, confidence, coarse cascade, drift estimation, SESX, overlap, graph solve, validation |
| `docs/offset_convention.md` | Project-wide offset sign and unit convention |
| `docs/research/existing_projects.md` | Prior-art matrix and reuse/re-implement decisions |
| `docs/mp4_wireless_delay_case.md` | Real-footage wireless-mic delay case study |
| `docs/adr/` | ADR 001–012 (design decisions) |
| `handoff/mp4_channel_sync/README.md` | Standalone algorithm package for external tools |

> Most detailed documents are currently written in Chinese; an English
> translation is in progress. Issues/PRs in English are welcome.

## Roadmap

```text
Phase 0  Prior-art research                        ✅
Phase 1  Skeleton + models + synthetic + GCC       ✅
Phase 2  GCC-PHAT refinement + benchmarks          ✅ (merged into Phase 1)
Phase 3  Features + cache + coarse cascade         ✅
Phase 4  Drift estimation + SoXR correction        ✅
Phase 5  Overlap / segment detection               ✅
Phase 6  Multi-track graph solver                  ✅
Phase 7  Validation / confidence                   ✅
         SESX export (Adobe Audition)              ✅ (ADR-010)
         JSON/CSV export + multi-track batch CLI   ✅
         MP4 wireless-mic channel sync             ✅
Phase 8  Large-scale real-world benchmark
Phase 9  Reaper RPP export + TimeMap composition
Phase 10 GUI
```

## License

MIT — see [`LICENSE`](LICENSE). Third-party libraries keep their own licenses
(numpy/scipy BSD; SoXR and libsndfile are LGPL, dynamically linked, notices
preserved).
