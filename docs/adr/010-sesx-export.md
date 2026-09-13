# ADR-010: Adobe Audition SESX export

**Status:** Accepted (2025, Phase 3+, explicit user requirement)
**Basis:** docs/research/notes/sesx_format.md, audition_import_paths.md

## Decision

Implement a **hand-written .sesx export** (export/sesx.py). Research verdict
(high confidence):

* SESX is **plain XML without checksum or signature**; the community already
  has two production-grade MIT writers
  (`outhud/audition-ses-to-sesx-converter`, verified sample-by-sample in
  Audition 2025; `nurdism/audition`, used by a production bot);
* **all time fields (startPoint/endPoint/sourceInPoint/sourceOutPoint/
  duration) are integer sample counts at the session sample rate**
  (confirmed four ways: the official Adobe scripting API, three independent
  codebases and arithmetic on real files), not seconds and not ticks;
* minimal structure: `sesx/session(tracks(audio tracks+masterTrack)+sessionState)
  + files table`; component/fade/channelMap/xmp and the rest can all be
  omitted;
* retained: `<!DOCTYPE sesx>`, masterTrack, trackOutput→master routing,
  `mediaHandler="AmioWav"`, `defaultPanModeLogarithmic` (keeps centred tracks
  at unity gain).

## Details

### Fidelity rules (honest disclosure, written into the module docstring and tests)

* identity / constant-offset → a single exact clip (integer samples);
* linear drift → a **stair-step approximation** of the clip (configurable
  granularity, default 10 s per block): an Audition clip cannot change
  playback rate, so continuous drift cannot be expressed exactly inside SESX;
  the per-block step error is ≤ ppm·chunk_seconds samples. Exact correction
  must go through `drift.correct_track` rendering;
* piecewise (breakpoints) → one clip per interval between knots; flat segments
  (drop gaps / insert repeats) become timeline gaps — lost content is never
  fabricated;
* a negative global start point is trimmed automatically (the clip starts at 0
  and the source in-point moves forward).

## Consequences

* The export core remains offsets + TimeMap + segments (non-destructive
  timeline); audio rendering is optional;
* Audition cannot express a variable-rate timeline or a variable-tempo
  mapping — the future Reaper RPP work (Phase 9) carries the richer mappings;
  CSV/JSON reports always remain the fallback;
* there is no official schema: format details are benchmarked against the
  research report plus two verified MIT implementations, and the XML structure
  is pinned by tests (elements, units, ID links, escaping).
