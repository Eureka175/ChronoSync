# ChronoSync Documentation Index

**Version: v0.1.0-beta** (PEP 440: `0.1.0b0`) · [Project README](../README.md) · [中文说明](../README.zh-CN.md)

## Core documents

| Document | Content |
|---|---|
| [../README.md](../README.md) | Project overview, install, quick start, roadmap |
| [../CHANGELOG.md](../CHANGELOG.md) | Release history |
| [architecture.md](architecture.md) | Layered architecture, data flow, package layout, dependency policy |
| [algorithms.md](algorithms.md) | All algorithms: GCC-PHAT / peak policy / confidence / coarse cascade / drift estimation / SESX / overlap / graph solve / validation |
| [offset_convention.md](offset_convention.md) | Project-wide offset sign and unit convention (ADR-003 in practice) |

> Detailed documents and ADRs are currently written in Chinese; the English
> translation is in progress.

## Architecture decision records (ADR)

| ADR | Decision |
|---|---|
| [001](adr/001-python-first.md) | Python-first stack (no premature C++/Numba) |
| [002](adr/002-canonical-audio-format.md) | Canonical audio format: 48 kHz / float32 / weighted mono_mix |
| [003](adr/003-offset-sign-convention.md) | Global offset sign convention `d = t_target − t_reference` |
| [004](adr/004-gcc-phat.md) | GCC-PHAT as the fine-alignment core (regularized whitening, peak policy) |
| [005](adr/005-time-map.md) | TimeMap abstraction (the system's core object) |
| [006](adr/006-cache-design.md) | Feature cache design (SQLite index + file-based arrays) |
| [007](adr/007-existing-project-analysis.md) | Prior-art analysis and reuse decisions (including licence red lines) |
| [008](adr/008-coarse-cascade.md) | Short-circuit coarse-matching cascade |
| [009](adr/009-drift-estimation.md) | Drift estimation (window shrink, changepoint detection, classification) |
| [010](adr/010-sesx-export.md) | Adobe Audition SESX export |
| [011](adr/011-graph-solver.md) | Multi-track global graph solver (WLS/IRLS) |
| [012](adr/012-validation-confidence.md) | Validation and interpretable confidence (incl. GCC polarity awareness) |

## Prior-art research (Phase 0)

| Document | Content |
|---|---|
| [research/existing_projects.md](research/existing_projects.md) | Prior-art difference matrix + reuse / re-implement decisions |
| [research/notes/audioalign_aurio.md](research/notes/audioalign_aurio.md) | AudioAlign / Aurio (C#, AGPL) |
| [research/notes/audalign_alignaudio.md](research/notes/audalign_alignaudio.md) | audalign (Python, MIT) / alignaudio (C, GPL) |
| [research/notes/whispersync.md](research/notes/whispersync.md) | WhisperSync verification (finding: no such public project) |
| [research/notes/audio_stack.md](research/notes/audio_stack.md) | FFmpeg/PyAV/SoXR/soundfile and their licences |
| [research/notes/sesx_format.md](research/notes/sesx_format.md) | SESX format reverse engineering (time unit = integer samples) |
| [research/notes/audition_import_paths.md](research/notes/audition_import_paths.md) | Audition import path evaluation |

> Third-party reference material (Adobe API type definitions, a broadcaster's
> `.sesx` sample) is not redistributed because of unclear ownership; the
> original URLs are preserved in the research notes.

## Real-world cases

| Document | Content |
|---|---|
| [mp4_wireless_delay_case.md](mp4_wireless_delay_case.md) | Measured wireless-microphone delay case study (19 4K MP4 files) |
| [../handoff/mp4_channel_sync/README.md](../handoff/mp4_channel_sync/README.md) | External handoff package: pure algorithm (numpy+scipy) + integration guide |

## Repository layout

```text
src/chronosync/     io · features · cache · coarse · fine · drift ·
                    overlap · global_alignment · validation · export ·
                    mp4sync · pipeline · cli
synthetic/          reproducible synthetic data (seeded, 15 scenarios)
tests/              unit (pure) / integration (ffmpeg-dependent cases auto-skip)
benchmarks/         gcc · features · drift · solve (wall/CPU/peak RSS + accuracy)
handoff/            external handoff package (with independent self-test)
scripts/            demo material generation and dedicated MP4 sync tooling
```
