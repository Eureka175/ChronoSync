# Adobe Audition Session/Timeline Import Paths — Research Notes

Project: **ChronoSync** (MIT). Goal: export a non-destructive multitrack timeline
(offsets + time maps + segments) that a user can open in Adobe Audition.

Date of research: 2026-04-21. All claims are annotated with a confidence level and
`Unknown / 需要进一步验证` where the claim could not be verified from a primary source.

> **Cross-reference — read together with the sibling notes in this directory:**
> - [`sesx_format.md`](./sesx_format.md) — the authoritative deep-dive on the `.sesx`
>   XML structure (this note is the ranked *overview* of ALL import paths; that note
>   is the format spec + minimal-template + pitfall reference).
> - [`BAS131_Session.sesx`](./BAS131_Session.sesx) — a real Audition 12.0 session
>   file used as a structural reference.
> The `.sesx` portion of this note (§3) is a summary; the full, validated detail
> lives in `sesx_format.md`.

## 0. TL;DR — Recommended ranking

| Rank | Approach | Verdict |
|------|----------|---------|
| 1 | **(a) Hand-written `.sesx`** (native XML session) | **Best fit.** Directly maps ChronoSync's offsets + segments (`startPoint`/`endPoint`/`sourceInPoint`/`sourceOutPoint`/`fileID`). Structure is fully documented by two independent open-source implementations and a Python pydantic model already exists. |
| 2 | **(b) ExtendScript/CEP automation** | Viable, but needs a live Audition install + CEP panel. Can place clips at sample-accurate times (`AudioClip.startTime`), but **cannot set per-clip source offset** through the typed 2018 API. More moving parts; Windows/macOS only. |
| 3 | **(c) AAF / OMF / XML interchange** | **Weak.** OMF import works but OMF is legacy and Python writers are immature; **AAF import in Audition is unreliable**; Audition *exports* FCP XML / Premiere XML but does **not import** them. |
| 4 | **(d) CSV/JSON report + manual placement** | Zero-risk fallback and good as a companion to (a)/(b), but manual. |

**Recommendation for ChronoSync:** implement (a) hand-written `.sesx` as the primary
export (using the structure documented in §3 / `sesx_format.md`, validated against a
real Audition install), and always emit a human-readable CSV/JSON placement report
(d) as a fallback. Optionally offer (b) ExtendScript as a "live" import path for
users who already have Audition open. **One caveat:** `.sesx` flattens the timeline
to samples and carries only a single BPM + timecode metadata (§3.4) — if a variable
tempo map must survive, the already-planned Reaper RPP path is the better carrier.

---

## 1. Native formats Audition can import/open for sessions/timelines

### 1.1 `.sesx` — native XML multitrack session (CC and later)

- `.sesx` is the current native Audition multitrack session format: a plain UTF-8
  XML file (no XML namespace), introduced with Audition CC (2013). **Confidence: high.**
- Adobe's own docs describe sessions saved "in the native SES format" and, for
  CC-era mixes, the `.sesx` XML format
  ([Audition CC 2014 reference, archive](https://help.adobe.com/archive/es/audition/cc/2014/audition_reference.pdf)).
- Opening path: `File > Open` / double-click a `.sesx`. Fully supported; this is
  the format Audition itself writes.
- Structure is **not officially documented** by Adobe, but is publicly known and
  independently re-implemented (see §3 and `sesx_format.md`). The root element is
  `<sesx version="…">`.
- Known `version` → Audition-era pairings (from `sesx_format.md`): `1.1`→CS5.5,
  `1.3`/`appVersion 10.0`→CS6, `1.7`/`12.0`→CC2019, `1.9`/`25.2`→CC2025. Newer
  Audition opens older `version` values. **Confidence: high (observed pairings);
  the exact tolerance logic is `Unknown / 需要进一步验证`.**

### 1.2 `.ses` — legacy binary multitrack session (Cool Edit Pro → Audition 3.0)

- `.ses` is the older (Cool Edit Pro / Audition ≤ 3.0) multitrack session format.
  Audition CC still opens `.ses` sessions, but with a documented caveat:
  "SES session files from Audition 3.0 or earlier are not supported" in current
  releases ([Audition CC 2014 reference, archive](https://help.adobe.com/archive/jp/audition/cc/2014/audition_reference.pdf)).
  **Confidence: medium — the exact version cutoff needs verification.**
- `.ses` is a binary format, harder to hand-write than `.sesx`; not a recommended
  export target. **Confidence: high (it's not text/XML).**

### 1.3 OMF (Open Media Framework)

- Audition **can import OMF** (e.g., OMF exported from Premiere Pro / Final Cut 7).
  Community reports confirm importing `.omf` from Premiere
  ([Adobe community thread](https://community.adobe.com/t5/audition-discussions/why-does-audition-create-two-seperate-channels-when-i-import-omf-from-premiere/m-p/13553543)).
  Audition also **exports** OMF (`File > Export > OMF`).
  **Confidence: medium-high (import works; channel/linking quirks reported).**
- OMF is an Avid-derived legacy interchange container (OMFI1/OMFI2); media is often
  embedded. Python tooling to *write* OMF is immature, so it is a poor generation
  target for ChronoSync. **Confidence: medium.**
- FCP 7 → Audition is documented via OMF
  ([Larry Jordan: FCP 7 → Audition using OMF](https://larryjordan.com/articles/fcp7-to-audition/)).

### 1.4 AAF (Advanced Authoring Format)

- **Audition AAF import is unreliable in practice.** Multiple independent reports
  state it is broken/absent despite marketing claims:
  - "AAF Import — Adobe says yes, reality says no" ([Creative COW](https://creativecow.net/forums/thread/aaf-import-adobe-says-yes-reality-says-no/))
  - "Audition AAF Import" ([Adobe community](https://community.adobe.com/t5/audition-discussions/audition-aaf-import/td-p/10634849))
  - "Using AAF files in Premiere & Audition CC 2015" ([Creative COW](https://creativecow.net/forums/thread/using-aaf-files-in-premiere-audition-cc-2015/))
- The Adobe official "Supported import formats" page is the authority here; the
  exact current AAF status should be re-checked there:
  [helpx.adobe.com/audition/using/supported-file-formats.html](https://helpx.adobe.com/audition/using/supported-file-formats.html)
  (`Unknown / 需要进一步验证` against the latest Audition version).
- Verdict: **do not target AAF** for Audition import.

### 1.5 Final Cut Pro XML (fcpxml / FCP 7 XML)

- Audition **exports** FCP XML (`File > Export > FCP XML`, command
  `COMMAND_FILE_EXPORT_FCXML`), but **does not import** FCP XML as a timeline.
  **Confidence: high.**
- FCP → Audition workflows instead route through **OMF** or the third-party
  **XtoCC** converter
  ([Larry Jordan: FCP X → Audition](https://larryjordan.com/articles/workflow-apple-final-cut-pro-x-to-adobe-audition-and-back/),
  [XtoCC on the App Store](https://apps.apple.com/app/xtocc/id487899517)).
  **Confidence: high.**

### 1.6 Premiere Pro interchange

- Audition **exports** a Premiere Pro XML sequence (`COMMAND_FILE_EXPORT_EXPORTTOADOBEPREMIEREPRO`),
  and Premiere Pro can send a sequence to Audition via **"Edit in Audition"**
  (a Premiere-driven Dynamic-Link handoff, not a file Audition opens).
  **Confidence: high.**
- Audition does **not** import a Premiere `.prproj` or Premiere XML as a timeline.
  **Confidence: high.**

### 1.7 Reaper `.rpp`

- Audition has **no native Reaper `.rpp` import**. Reaper ↔ Audition interop is
  done via third-party converters (AATranslator, etc.)
  ([Cockos forum: "Any Audition compatibility?"](https://forum.cockos.com/showthread.php?t=164090),
  [AATranslator](https://www.aatranslator.com.au/)).
  **Confidence: high.**
- Practical consequence: ChronoSync's planned RPP exporter does **not** give a
  direct Audition path. AATranslator (commercial) can convert RPP→sesx/ses as a
  fallback, but generating `.sesx` directly is cleaner.

### 1.8 Media (audio/video) import — not timeline interchange

- Audition imports many audio containers (WAV, AIFF, MP3, FLAC, OGG, etc.) and can
  open video containers (MP4, MOV, AVI, MXF) for audio-to-picture work. These open
  as **waveform files / multitrack media**, not as an aligned multi-track timeline,
  so they are not a timeline interchange path. **Confidence: high.**
  (See [Adobe supported file formats](https://helpx.adobe.com/audition/using/supported-file-formats.html).)

---

## 2. Scripting: ExtendScript / CEP automation

### 2.1 Does Audition have script automation? — **Yes.**

- Adobe Audition supports **CEP (Common Extensibility Platform)** extensions:
  HTML/JavaScript panels that call ExtendScript (Adobe's JavaScript dialect) via
  `evalScript`. Host ID is `AUDT`.
  ([Adobe: Enabling CEP extensions](https://helpx.adobe.com/audition/using/enabling-cep-extensions.html),
  [Adobe-CEP Samples — Audition](https://github.com/Adobe-CEP/Samples/tree/master/Audition),
  [Adobe developer portal: Audition](https://developer.adobe.com/audition/)).
- The ExtendScript **object model** (DOM) is captured in community TypeScript
  type definitions: `Types-for-Adobe/Audition/2018/index.d.ts`
  ([GitHub](https://github.com/docsforadobe/Types-for-Adobe/tree/master/Audition/2018)).
  A cached copy was saved to `_audition_api.d.ts` in this directory during research.
  **Confidence: high.**
- There is **no official Adobe API reference document** for Audition ExtendScript;
  users rely on these community type defs
  ([Adobe community: "ExtendScript for Audition: is there an API reference?"](https://community.adobe.com/t5/audition-discussions/extendscript-for-audition-is-there-an-api-reference/m-p/12768683)).
  **Confidence: high.**

### 2.2 Relevant API surface (from the 2018 type definitions)

Confirmed classes/members relevant to building a multitrack timeline:

- `Application`
  - `openDocument(openParameter: DocumentOpenParameter): Document`
  - `invokeCommand(command: string): boolean` — command IDs include:
    `COMMAND_FILE_NEWSESSION`, `COMMAND_FILE_IMPORTFILE`,
    `COMMAND_MULTITRACK_IMPORTANDINSERTFILESASCLIPS`, plus track-add commands
    (`COMMAND_MULTITRACK_ADDMONOAUDIOTRACK`, `…_ADDSTEREOAUDIOTRACK`, etc.).
  - `activeDocument`, `documents`.
- `MultitrackDocument` — `audioTracks: MixedAudioTrackCollection`,
  `playheadPosition` (read/write, samples), `duration`, `sampleRate`,
  `addMarker()`, `activate()`.
- `MixedAudioTrackCollection` — `audioClipTracks`, `audioBusTracks`,
  `masterTrack`, `add(layout, trackType)`, `getAudioTrack(name)`, `remove(track)`.
- `AudioTrack` — `audioClips: AudioClipCollection`, `name` (read/write), `mute`,
  `solo`, `armed`, `type`, `id`.
- `AudioClipCollection.add(AudioClip/document, sourceChannelRouting)` — *"Add new
  clip to the track based on the passed in document or move the passed in clip to
  this track."*
- `AudioClip` — **`startTime: number` (read/write, samples)**, `endTime`
  (read-only), `link` (read/write — source document), `sourceChannelRouting`,
  `name`, `id`, `audioFormat`.
- `AudioChannelLayout` / `AudioFormat` — for declaring track channel layouts.

**Confidence: high** (these are verbatim from the community type definitions).

### 2.3 Can a script place WAV files at specific times? — **Yes, with one caveat.**

- Workflow (theoretical, from the API surface):
  1. `var doc = app.openDocument(new DocumentOpenParameter("C:/.../file.wav"))` for each source WAV.
  2. Create a multitrack session (`invokeCommand(COMMAND_FILE_NEWSESSION)`).
  3. Add tracks: `session.audioTracks.add(layout, AudioTrack.AUDIOTRACKTYPE_CLIP)`.
  4. Insert clips: `track.audioClips.add(waveDoc, sourceChannelRouting)`.
  5. Position: `clip.startTime = sampleOffset;` (samples at session rate).
- **Caveat — source offset (slip) is NOT exposed:** the typed `AudioClip` has
  `startTime`/`endTime` but **no** `sourceInPoint`/`sourceOutPoint`. So ExtendScript
  can place full WAV files at arbitrary times, but **cannot natively set a clip's
  in-source offset** (trimmed segment start). For ChronoSync's "segments" you would
  need to pre-render trimmed WAVs, or use `.sesx` (which fully supports
  `sourceInPoint`/`sourceOutPoint`). **Confidence: high (API limitation), medium
  (whether a newer API added offset support — `Unknown / 需要进一步验证`).**
- **Caveat — creating/obtaining a session handle:** the 2018 type defs expose no
  `createSession()`; a new session must be created via `invokeCommand(COMMAND_FILE_NEWSESSION)`
  and then the `MultitrackDocument` obtained from the active document. The Flue
  project probes `app.activeSession` (not present in the 2018 defs), suggesting
  version drift here. **`Unknown / 需要进一步验证` on the cleanest way to get the
  session object.**

### 2.4 Open examples

- **Flue** (MIT) — a shell→app bridge with an `audition_adapter` that runs
  ExtendScript inside Audition via a CEP panel + `evalScript`, with a Python
  stdin/stdout bridge
  ([GitHub: SFKislev/Flue — adapters/audition_adapter](https://github.com/SFKislev/Flue)).
  Its `docs/api-index.txt` is generated mechanically from the same
  `Types-for-Adobe` definitions (41 classes / 888 properties / 82 methods).
- A public ExtendScript example automates multitrack **mixdown/export**, confirming
  the scripting environment works end-to-end
  ([Qiita: Audition multitrack ExtendScript mixdown export](https://qiita.com/NTak_indies/items/b1a66b4b4805211e8763)).
- No widely-known open example does exactly "import WAVs + place at arbitrary
  sample offsets" via ExtendScript — **`Unknown / 需要进一步验证`** whether the
  `audioClips.add()` + `startTime` sequence works as theorized; it should be
  prototyped on a real install before committing.

---

## 3. Community knowledge of minimal `.sesx` writing

**Verdict: hand-writing a minimal `.sesx` that Audition opens is a solved problem.**
At least two independent MIT open-source projects generate `.sesx` in production,
and one is validated end-to-end in Audition 2025. Full detail (structure, minimal
templates, pitfalls, version map) is in the sibling note [`sesx_format.md`](./sesx_format.md);
this section is the summary.

### 3.1 Existing open-source writers & parsers

| Project | Lang | License | Writes `.sesx`? | Notes |
|---|---|---|---|---|
| [outhud/audition-ses-to-sesx-converter](https://github.com/outhud/audition-ses-to-sesx-converter) | Python (stdlib) | MIT | **YES** | **Best reference.** Emits a minimal `.sesx`; README documents a sample-by-sample render comparison in **Audition 2025**. |
| [nurdism/audition](https://github.com/nurdism/audition) | JS (Node) | MIT | **YES** | Production bot; ultra-minimal `.sesx` (omits `<!DOCTYPE>`, sessionState, components, fades, channelMap, audioDevice) still opens. |
| [scnerd/pydantic_adobe_audition](https://github.com/scnerd/pydantic_adobe_audition) | Python | *none declared* | model/parse (round-trips) | Full `pydantic`+`pydantic-xml` schema of the format (PyPI: `pydantic-adobe-audition`). |
| [atmosfar/audition_session_to_reaper_project_converter](https://github.com/atmosfar/audition_session_to_reaper_project_converter) | Python | MIT | parse → Reaper RPP | Confirms field semantics against real files. |
| [rawktron/sesx2rpp](https://github.com/rawktron/sesx2rpp) | Python | MIT | parse | |
| [epistemex/sesx2pl](https://github.com/epistemex/sesx2pl) | JS (Node) | *none declared* | parse → m3u/cue | |

**Commercial:** [AATranslator](https://www.aatranslator.com.au/) (incl.
[`ses2sesx`](https://www.aatranslator.com.au/ses2sesx.html)) productizes `.ses`→`.sesx`
and RPP→sesx conversion — further proof the format is writable without Adobe.

### 3.2 Minimal structure (summary)

Confirmed across the real `BAS131_Session.sesx` file, Adobe's scripting API type
defs, and all the writers above (full detail in `sesx_format.md`):

- Root: `<?xml version="1.0" encoding="UTF-8" standalone="no" ?>` + `<!DOCTYPE sesx>`
  + `<sesx version="…">` (no XML namespace; UTF-8, BOM tolerated; `<!DOCTYPE>`
  likely optional).
- `<session appBuild appVersion audioChannelType bitDepth duration sampleRate>` →
  `<tracks>` (`audioTrack*`, `masterTrack`), optional `sessionState`, `xmpMetadata`,
  `clipGroups`, `metronome`, `properties`.
- `<files>` → `<file id absolutePath relativePath mediaHandler importerPrivateSettings>`.
  `mediaHandler="AmioWav"` for WAV.
- `<audioClip>` (17 attributes) — the fields ChronoSync needs are:
  `fileID` (→ `<file id>`), `startPoint` / `endPoint` (timeline, **samples**),
  `sourceInPoint` / `sourceOutPoint` (source offset, **samples**), `name`, `id`,
  `zOrder`, `looped`, `offline`.
- **All time values are integer sample counts at the session sample rate** — not
  seconds, not ticks (ticks exist only in the legacy binary `.ses`).

### 3.3 Key mapping to ChronoSync's model

| ChronoSync concept | `.sesx` field |
|--------------------|---------------|
| Segment start on timeline | `audioClip@startPoint` (samples) |
| Segment end / length | `audioClip@endPoint` (samples) |
| Source offset (slip/trim) | `audioClip@sourceInPoint` / `@sourceOutPoint` (samples) |
| Source file reference | `audioClip@fileID` → `files/file@id` + `absolutePath`/`relativePath` |
| Track name | `audioTrack/trackParameters/name` |
| Clip/track gain & pan | `component[@componentID='Audition.Fader'/'Audition.StereoPanner']` + `parameter` |
| Markers / regions | XMP inside `<xmpMetadata>` (`xmpDM:Tracks` → "CuePoint Markers") |

### 3.4 Time maps — **important limitation**

- `.sesx` stores a **fixed timebase only**: session `sampleRate`, `smpteStart`
  (SMPTE offset), and `timeFormatState` (single `beatsPerMinute`, `beatsPerBar`,
  `timeCodeFrameRate`, `timeCodeDropFrame`, `timeFormat`). It does **not** carry a
  variable tempo/time map; "ticks" are a `.ses`-only concept.
  **Confidence: high** (see `sesx_format.md` §2 and §7).
- **Consequence for ChronoSync:** offsets and segments map 1:1, but a *variable*
  tempo/musical-time map cannot be round-tripped through `.sesx` — only the flat
  sample timeline plus a single BPM + frame-rate/timecode metadata survive. If a
  faithful tempo map matters more than sample-accurate alignment, that is an
  argument for the Reaper RPP path (already planned) over `.sesx`.

### 3.5 Remaining unknowns (`Unknown / 需要进一步验证`)

- The **exact** `version`/`appVersion`/`appBuild` validation Audition applies
  (proven: `appBuild` accepts arbitrary strings; older `version` opens in newer
  Audition; see the version table in `sesx_format.md` §7).
- Whether strict **element ordering** is required (no rejection reports exist; all
  writers keep Audition's order — safest to do the same).
- `pydantic_adobe_audition` **license is undeclared** — verify before vendoring code.

---

## 4. Ranking of approaches

### (a) Hand-written `.sesx` — **RECOMMENDED (rank 1)**

- **Pros:** native, opens via plain `File > Open`; fully non-destructive (references
  existing WAV files by absolute/relative path); directly models offsets + segments
  + source offsets + track names + gain/pan; pure Python (no Adobe install needed to
  *generate*); structure is documented, independently confirmed, and **already
  validated to open in Audition** (§3, `sesx_format.md`).
- **Cons:** format is proprietary and undocumented by Adobe; no official spec
  guarantee (compatibility drift risk); **no variable tempo/time map** (only fixed
  sample timebase + single BPM + timecode metadata, §3.4).
- **Effort:** low (a minimal writer for ChronoSync's subset is small; the MIT
  `outhud` converter is a ready reference template).

### (b) ExtendScript/CEP automation — **rank 2**

- **Pros:** drives the real app (no format guesswork — Audition itself builds the
  session); sample-accurate placement via `AudioClip.startTime`.
- **Cons:** requires an installed, licensed Audition + a CEP panel; **no
  per-clip source offset** in the typed API (would force pre-rendered trimmed WAVs);
  more moving parts and platform constraints; API is community-documented only.
- **Effort:** medium (CEP panel + JSX + a local bridge, cf. Flue).

### (c) AAF / OMF / XML interchange — **rank 3**

- OMF import works but OMF is legacy, media-embedding-centric, and has immature
  Python writers. AAF import in Audition is unreliable. FCP XML / Premiere XML are
  Audition *export-only*. Net: poor generation targets.

### (d) CSV/JSON report + manual placement — **rank 4 (but always ship it)**

- Zero-risk, human-readable, works everywhere. Best as a companion/fallback to (a).

**Hybrid recommendation:** (a) `.sesx` primary + (d) CSV/JSON always; (b) optional
"live import" later. Skip (c). Caveat: if ChronoSync's timeline carries a *variable*
tempo map, `.sesx` flattens it to samples + a single BPM (the RPP path preserves it),
so prefer RPP in that case — see §3.4.

---

## 5. License / legal notes

- `.sesx` / `.ses` are **proprietary, undocumented** Adobe formats, but they are
  plain **data files** (`.sesx` is readable XML). Writing a data file that another
  program can parse is, in practice, **not** "reverse engineering" Adobe's software
  in the prohibited sense: it copies no Adobe code, breaks no encryption/DRM, and
  uses no undocumented API at runtime. File formats are generally not protected by
  copyright; a text format embodied in countless public files is a weak trade-secret
  claim. **Confidence: medium-high (practical/legal consensus), but this is not
  legal advice.**
- Precedent: multiple third parties read/write Audition session formats without an
  Adobe license — AATranslator (commercial) and the MIT open-source projects
  `outhud`, `nurdism`, `atmosfar`, plus `scnerd/pydantic_adobe_audition`.
  **Confidence: high.**
- No Adobe license is required *to generate* a compatible file; an Adobe Audition
  license is required only *by the end user* who opens it (and to run ExtendScript).
  **Confidence: high.**
- Reusing third-party code: `atmosfar` converter is **MIT**; Flue is **MIT**;
  `pydantic-adobe-audition` has **no license declared** in its METADATA — do not
  vendor its code until licensing is confirmed; using it only as a structural
  reference is low-risk. **`Unknown / 需要进一步验证` (pydantic-adobe-audition license).**
- Practical risk is compatibility drift, not legal: Adobe changed `ses → sesx`
  before and could change again; treat the exporter as best-effort and validate on
  real Audition versions.

---

## 6. Per-claim confidence summary

| # | Claim | Confidence |
|---|-------|-----------|
| 1 | `.sesx` is the native XML session format; `File > Open` works | High |
| 2 | `.sesx` is namespace-less XML; `<sesx version>` root | High |
| 3 | Full `.sesx` element/attribute tree | High (real file + ≥4 OSS sources, see `sesx_format.md`) |
| 4 | Minimal `.sesx` opens in Audition | **High** (`outhud` validated in Audition 2025; `nurdism` in production) |
| 5 | `sesx version` → Audition-era mapping | Medium (observed `1.1`–`1.9` pairings; exact tolerance logic Unknown) |
| 6 | `.ses` legacy binary session; opened by CC with version caveat | Medium |
| 7 | Audition imports OMF | Medium-high |
| 8 | Audition imports AAF reliably | **Low / contradicted by reports** (need current doc check) |
| 9 | Audition imports FCP XML | **No** (export-only) — high |
| 10 | Audition imports Premiere XML / `.prproj` | **No** (export-only) — high |
| 11 | Audition imports Reaper `.rpp` | **No** — high |
| 12 | ExtendScript/CEP automation exists (host `AUDT`) | High |
| 13 | `AudioClip.startTime` is writable (sample placement) | High (typed API) |
| 14 | `audioClips.add(document, routing)` inserts a clip | High (typed API) |
| 15 | ExtendScript can set per-clip source offset | **No** (not in typed API) — high for 2018 API |
| 16 | Cleanest way to create + grab a new session object in JSX | **Unknown / 需要进一步验证** |
| 17 | End-to-end "import WAVs → place at offsets" JSX example exists publicly | **Unknown / 需要进一步验证** |
| 18 | `pydantic-adobe-audition` is a viable sesx writer | Medium (early, license undeclared) |
| 19 | Variable tempo/time map is representable in `.sesx` | **No** — fixed timebase only (single BPM + frame rate + SMPTE offset); high |
| 20 | Writing `.sesx` is legally low-risk (data format, no code copying) | Medium-high (not legal advice) |

---

## Appendix — sources

Primary / most-cited:

- Adobe — Supported file formats: https://helpx.adobe.com/audition/using/supported-file-formats.html
- Adobe — Enabling CEP extensions: https://helpx.adobe.com/audition/using/enabling-cep-extensions.html
- Adobe developer — Audition: https://developer.adobe.com/audition/
- Adobe-CEP Samples (Audition, host `AUDT`): https://github.com/Adobe-CEP/Samples/tree/master/Audition
- Types-for-Adobe — Audition 2018 `index.d.ts` (cached locally as `_audition_api.d.ts`): https://github.com/docsforadobe/Types-for-Adobe/tree/master/Audition/2018
- outhud — ses→sesx converter (MIT, `.sesx` writer, Audition-2025-validated): https://github.com/outhud/audition-ses-to-sesx-converter
- nurdism — audition (MIT, `.sesx` writer): https://github.com/nurdism/audition
- scnerd — pydantic_adobe_audition (sesx schema model; PyPI `pydantic-adobe-audition`): https://github.com/scnerd/pydantic_adobe_audition
- atmosfar — sesx→rpp converter (MIT): https://github.com/atmosfar/audition_session_to_reaper_project_converter
- Flue — audition adapter (MIT): https://github.com/SFKislev/Flue (path `adapters/audition_adapter`)
- AATranslator — ses2sesx: https://www.aatranslator.com.au/ses2sesx.html
- AAF import reports: https://creativecow.net/forums/thread/aaf-import-adobe-says-yes-reality-says-no/ , https://community.adobe.com/t5/audition-discussions/audition-aaf-import/td-p/10634849
- OMF import (from Premiere): https://community.adobe.com/t5/audition-discussions/why-does-audition-create-two-seperate-channels-when-i-import-omf-from-premiere/m-p/13553543
- FCP→Audition via OMF / XtoCC: https://larryjordan.com/articles/fcp7-to-audition/ , https://apps.apple.com/app/xtocc/id487899517
- Reaper interop: https://forum.cockos.com/showthread.php?t=164090
- Audition CC 2014 reference (archive; `.ses` version caveat): https://help.adobe.com/archive/jp/audition/cc/2014/audition_reference.pdf
- ExtendScript API reference discussion: https://community.adobe.com/t5/audition-discussions/extendscript-for-audition-is-there-an-api-reference/m-p/12768683
- AAF writer library (Python, for completeness): https://github.com/jkirkcaldy/pyaaf2
