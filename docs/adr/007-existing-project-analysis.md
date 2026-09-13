# ADR-007: Analysis of existing projects and reuse decisions

**Status:** Accepted (2025, Phase 0/1)
**Impact:** component selection for all subsequent phases
**Basis:** docs/research/existing_projects.md and the four research sub-reports under notes/

## Decision

1. **Do not port any existing alignment project** (AudioAlign/Aurio are C#/AGPL;
   alignaudio is C/GPL; the WhisperSync class has no public implementation).
2. **Reusable objects**: audalign (MIT, pip) as a coarse-matching reference
   implementation and benchmark; numpy/scipy carry all DSP; soundfile + soxr +
   PyAV carry I/O and resampling.
3. **Self-developed list** (missing or insufficient in existing projects):
   GCC-PHAT + peak policy + sub-sample; the drift estimator (windowed GCC →
   regression → drift/discontinuity/bad-measurement classification); multi-track
   graph solving (WLS + connectivity + residuals); interpretable confidence;
   Overlap/Segment; DAW timeline export.
4. **Design borrowing (concepts only)**: AudioAlign's Match{Similarity,Source}
   provenance, TimeWarpCollection piecewise linear + variable-rate resampling,
   ConvertToIntervals discontinuity splitting, locked reference track;
   alignaudio's chunked-offset → least-squares ppm fitting pipeline;
   podsync's dual-window cross-corroboration.
5. **Whisper positioning**: an optional speech-anchor evidence source (Phase 8+);
   the signal path (VAD + GCC + drift regression) must remain independently
   usable — ChronoSync does not build a WhisperSync clone.

## Licence red lines

* Libraries that are merged in or linked must be MIT/BSD/ISC or LGPL (dynamic
  linking + notices preserved);
* merging in GPL/AGPL components is **forbidden** (aeneas, anchor-sub-sync,
  find_delay, the code of AudioAlign/Aurio/alignaudio);
* fingerprinting algorithms (Haitsma-Kalker/Wang/Echoprint) carry patent risk —
  evaluate them separately when selecting for Phase 3, preferring
  implementations with no patent risk;
* libsoxr is LGPL-2.1 (not BSD) — the README/licence notices must state this
  truthfully.

## Consequences

* Phase 3 coarse matching uses audalign as a cross-check, not as a dependency;
* Phase 4 drift correction is implemented with soxr.ResampleStream
  (variable rate), not alignaudio-style sample dropping;
* the APIs of all self-developed modules follow this project's ADR-001..006
  (Python-first, canonical format, offset convention, GCC policy, TimeMap,
  cache).
