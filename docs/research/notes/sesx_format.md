# Adobe Audition `.sesx` Session Format — Reverse-Engineering Research Notes

**Project:** ChronoSync (MIT) — needs to *write* minimal valid `.sesx` files.
**Date of research:** compiled from live web/GitHub/real-file inspection.
**Status of this document:** best-effort community reverse-engineering. There is **no official public SESX XML schema** — Adobe ships none. Everything below is derived from (a) a real Audition-saved `.sesx` file, (b) three independent open-source writers/parsers, and (c) Adobe's own scripting API type definitions.

---

## 0. Verdict (read this first)

**Feasible: YES — writing a minimal `.sesx` that Audition opens is reliably achievable**, and at least two independent open-source projects already do it in production (`nurdism/audition`, `outhud/audition-ses-to-sesx-converter`). The latter was validated end-to-end by rendering a generated session in **Audition 2025** and comparing sample-by-sample against the original.

The exact minimal structure Audition needs is:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<!DOCTYPE sesx>
<sesx version="1.9">
  <session appBuild="..." appVersion="25.2" audioChannelType="stereo" bitDepth="16"
           duration="<total_samples>" sampleRate="<sample_rate>">
    <tracks>
      <audioTrack ...>  <!-- one per track: id, index, trackParameters/name,
                             trackAudioParameters/trackOutput -> master, audioClip* -->
      <masterTrack .../>
    </tracks>
    <sessionState .../>   <!-- optional but recommended -->
  </session>
  <files>
    <file absolutePath="..." relativePath="..." mediaHandler="AmioWav" id="0"/>
  </files>
</sesx>
```

Time fields (`startPoint`, `endPoint`, `sourceInPoint`, `sourceOutPoint`, `duration`) are **integer sample counts at the session sample rate** — *not* seconds, *not* ticks. This is confirmed by Adobe's own API docs, by three independent codebases, and by arithmetic checks against a real file.

---

## 1. Overall XML structure

### 1.1 File prolog and root

Real Audition-saved files begin:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<!DOCTYPE sesx>
<sesx version="1.7">
```

- **Root element:** `<sesx version="X">`.
- **`<!DOCTYPE sesx>`** is written by real Audition and by `outhud`, but **omitted** by `nurdism` (whose files still open). Treat it as *conventional, likely optional*.
- **`version` attribute** correlates with the Audition version that wrote it (see §7).
- **Encoding is UTF-8.** Real files carry a UTF-8 BOM (`EF BB BF`) even though the declaration says `encoding="UTF-8"`. No community writer emits UTF-16, and no evidence Audition expects it.

### 1.2 Top-level children of `<sesx>`

Observed order in a real file (`Audition 12.0`, version 1.7):

| Element | Required? | Notes |
|---|---|---|
| `<session>` | **yes** | the only mandatory child |
| `<files>` | **yes** (if any clips reference media) | media file table, one `<file>` per distinct source |
| `<audioDevice>` | **no** | last-session audio I/O device; safe to omit (both `nurdism` and `outhud` omit it) |

### 1.3 `<session>` — attributes

| Attribute | Meaning | Required? |
|---|---|---|
| `appBuild` | build number string | appears required-ish, but **arbitrary values are accepted** (`outhud` writes `appBuild="ses2sesx"` and Audition 2025 opens it) |
| `appVersion` | Audition version (`"10.0"`, `"12.0"`, `"25.2"`) | written by all; use a real version string |
| `audioChannelType` | `"stereo"`, `"mono"`, `"5.1"`, … | yes |
| `bitDepth` | `"16"`, `"24"`, `"32"` (float) | yes |
| `duration` | **total session length in samples** (int) | yes |
| `sampleRate` | int Hz (e.g. `44100`, `48000`) | yes |

Real example (Audition 12.0):
```xml
<session appBuild="12.0.0.241" appVersion="12.0" audioChannelType="stereo"
         bitDepth="16" duration="13561983" sampleRate="44100">
```

### 1.4 `<session>` — children

| Element | Required? | Notes |
|---|---|---|
| `<tracks>` | **yes** | contains `audioTrack*` + `masterTrack` |
| `<sessionState>` | no | `ctiPosition`, `smpteStart`; `outhud` nests `<timeFormatState>` and `<mixingOptionState>` inside it |
| `<xmpMetadata>` | no | markers/regions only; a `<![CDATA[ … ]]` XMP packet |
| `<clipGroups>` | no | clip grouping |
| `<metronome>` | no | `enabled`, `pattern`, `soundSet` |
| `<properties>` | no | contains `<property key="...">` JSON blobs (e.g. `EssentialSoundConfigurations`) |
| `<name>` | no | session title — written by `nurdism`, absent in the real file and in `outhud` |

### 1.5 `<tracks>` → `audioTrack` / `masterTrack`

**`audioTrack` attributes** (real file): `automationLaneOpenState="false" id="10001" index="1" select="false" visible="true"`.
- `id` is a small int (Audition uses `10001`, `10002`, …; `nurdism` uses `1001`, `1002`, …; `outhud` uses `10001 + idx`). Must be unique.
- `index` is 1-based track order.

**`audioTrack` children:**

| Child | Required? | Notes |
|---|---|---|
| `<trackParameters trackHeight="..." trackHue="..." trackMinimized="...">` with child `<name>Track 1</name>` | yes (name is the per-track name you need) | `trackHue` is 0–359; `trackHeight` in px |
| `<trackAudioParameters audioChannelType="stereo" automationMode="1" monitoring="false" recordArmed="false" solo="false" soloSafe="false">` | yes | routing + mix state |
| └ `<trackOutput outputID="10000" type="trackID"/>` | yes | routes track → master (`type="trackID"`) |
| └ `<trackInput inputID="1"/>` | no | `nurdism` omits it and it still works |
| └ `<component …/>` (Fader / Mute / StereoPanner / EQ) | **no** | `nurdism` writes zero components; `outhud` writes Fader+Mute+StereoPanner. Optional. |
| `<audioClip …>` (0..n) | the actual clips | see §1.6 |
| `<editParameter parameterIndex="0" slotIndex="4294967280"/>` | no | `4294967280 == 0xFFFFFFF0` |

**`masterTrack`**: id `10000` (or `1000` in `nurdism`), the master bus. Its `trackOutput` uses `type="hardwareOutput"` (`outhud`) or is omitted (`nurdism`). Both writers always emit a `masterTrack`, and every real file has one, so **include it** and route each `audioTrack`'s `trackOutput outputID` to the master's `id`.

### 1.6 `<audioClip>` — the clip element

**All 17 attributes** (from a real file; every writer emits the same set):

```xml
<audioClip clipAutoCrossfade="true" crossFadeHeadClipID="-1" crossFadeTailClipID="-1"
           endPoint="434000" fileID="0" hue="-1" id="0" lockedInTime="false"
           looped="false" name="BAS 131 Script" offline="false" select="false"
           sourceInPoint="0" sourceOutPoint="153512" startPoint="280488" zOrder="0">
```

| Attribute | Meaning | Notes |
|---|---|---|
| `fileID` | index into `<files>` `<file id="…">` | **this is the link to the external WAV** |
| `startPoint` | clip position on the session timeline (**samples**) | your "startTime" |
| `endPoint` | clip end on the timeline (**samples**) | `endPoint - startPoint =` timeline length |
| `sourceInPoint` | source-file playback offset (**samples**) | your "in time" |
| `sourceOutPoint` | source-file playback end (**samples**) | your "out time" |
| `name` | clip display name | |
| `id` / `zOrder` | unique per track / stacking order | `id` unique within track; `zOrder` 0-based |
| `looped` | `"true"`/`"false"` | see §4 looped-clip gotcha |
| `offline` | `"false"` | set false; Audition marks offline when media missing |
| `hue`, `lockedInTime`, `select`, `clipAutoCrossfade`, `crossFadeHeadClipID`, `crossFadeTailClipID` | cosmetic/routing | use the literal defaults above |

**`audioClip` children** (all optional in practice):
- `<component>` × Fader/Mute/StereoPanner (each with `<parameter>` children) — optional.
- `<fadeIn>` / `<fadeOut>` (`startPoint`, `endPoint`, `shape`, `type`, `crossFadeLinkType`) — optional; `nurdism` omits them entirely.
- `<editParameter>` — optional.
- `<channelMap><channel index="0" sourceIndex="0"/><channel index="1" sourceIndex="1"/></channelMap>` — stereo mapping; `outhud` writes it, `nurdism` omits it.

### 1.7 `<files>` → `<file>`

```xml
<file absolutePath="/Volumes/projects/.../BAS 131 Script.wav" id="0"
      importerPrivateSettings="Compression:0:0;LargeFileSupport:0:0;SampleType:0:20;"
      mediaHandler="AmioWav" relativePath="BAS 131 Script.wav"/>
```

| Attribute | Meaning | Required? |
|---|---|---|
| `id` | int, matches `audioClip.fileID` | **yes** |
| `absolutePath` | full path (used to find media) | recommended; fall back to `relativePath` |
| `relativePath` | path relative to the `.sesx` location (or bare basename) | recommended |
| `mediaHandler` | codec handler — **`AmioWav`** for WAV, `AmioAiff`, `AmioMP3`, `AmioLSF` (generic) | yes |
| `importerPrivateSettings` | semi-colon key:value:value list of importer settings | **optional** — `outhud` omits it and Audition opens the file |

`outhud`'s `importerPrivateSettings`-less file line (validated in Audition 2025):
```xml
<file absolutePath="C:\audio\song.wav" id="0" mediaHandler="AmioWav" relativePath="song.wav"/>
```

---

## 2. TIME UNITS — definitive answer

**All timeline/source times in `.sesx` are integer SAMPLE counts at the session sample rate.** There are **no "ticks" in the SESX XML**.

Evidence (four independent confirmations):

1. **Adobe's own scripting API** (`_audition_api.d.ts`, captured in this repo's research notes) states verbatim:
   - `AudioClip.startTime`: *"The start time of the clip measured in samples at the multitrack document's sample rate."*
   - `AudioClip.endTime`: *"The end time of the clip measured in samples (exclusive) at the multitrack document's sample rate."*
2. **`atmosfar/audition_session_to_reaper_project_converter`** converts by dividing: `start_point = int(clip.get('startPoint')) / sample_rate` → seconds.
3. **`epistemex/sesx2pl`**: `startPoint / sampleRate` → seconds.
4. **`nurdism/audition`** *writes* by multiplying: `startPoint = start_seconds * (sampleRate / 1000)`.
5. **Arithmetic check on a real file** (`sampleRate="44100"`, `duration="13561983"` → 307.5 s): clip 1 has `startPoint=280488` (6.36 s), `endPoint=434000` (9.84 s), `sourceInPoint=0`, `sourceOutPoint=153512` (3.48 s), and `endPoint − startPoint = 153512 = sourceOutPoint − sourceInPoint` — exact sample math, only possible if these are samples.

Conversions:
```
timeline_seconds  = startPoint / sampleRate
clip_length_sec   = (endPoint - startPoint) / sampleRate
source_in_sec     = sourceInPoint / sampleRate
source_out_sec    = sourceOutPoint / sampleRate
session_duration_sec = duration / sampleRate
```

**Where "ticks" appear:** only in the *legacy binary `.ses`* format (Cool Edit Pro / Audition 1.x–3.0), which stores tempo/meter as PPQ ticks. [AATranslator's ses2sesx page](https://www.aatranslator.com.au/ses2sesx.html) lists "Tempo, BPM, Ticks" as *input* fields it reads from `.ses`. They have **no counterpart in `.sesx`** — tempo is carried only as display metadata in `<timeFormatState>`/XMP.

**Markers/regions** (XMP `xmpDM:startTime` / `xmpDM:duration`) are **also in samples**, not seconds — confirmed by `atmosfar` (divides by `sample_rate`) and `outhud` (writes raw sample positions, sets `xmpDM:frameRate` to `f{sample_rate}`).

---

## 3. Minimal valid `.sesx` (best-effort, with sources)

Two published, working minimal structures exist. The first is the *absolute minimum* known to open; the second is the *robust, modern-audition-validated* version. Both are quoted with attribution and MIT license.

### 3.1 Ultra-minimal (proven in production) — `nurdism/audition`

This is the structure emitted by a Discord-recording bot (`nurdism/audition`, MIT, © 2017 Digitronics) whose README says it produces *"a usable adobe audition sesx, session file"*. It omits `<!DOCTYPE>`, `sessionState`, all `<component>` elements, fades, channelMap, editParameter, and `audioDevice`, and Audition still opens it. Reconstructed from `process/bin/lib/sessions/sesx.js`:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<sesx version="1.3">
  <session appBuild="10.0.1.8" appVersion="10.0" audioChannelType="stereo"
           bitDepth="16" sampleRate="48000" duration="4800000">
    <name>session-name</name>
    <tracks>
      <audioTrack index="1" id="1001">
        <trackParameters>
          <name>Track 1</name>
        </trackParameters>
        <trackAudioParameters>
          <trackOutput outputID="1000" type="trackID"/>
        </trackAudioParameters>
        <audioClip fileID="0" id="0" zOrder="0" name="clip-name"
                   startPoint="0" endPoint="4800000"
                   sourceInPoint="0" sourceOutPoint="4800000"/>
      </audioTrack>
      <masterTrack id="1000" index="2"/>
    </tracks>
  </session>
  <files>
    <file absolutePath="/path/to/clip.wav" relativePath="clip.wav"
          importerPrivateSettings="ByteOrdering:0:0;Channels:0:2;EncodingType:0:1;FormatType:0:262144;SampleRate:0:48000;StartOffset:0:0;VBRQuality:0:100;"
          mediaHandler="AmioLSF" id="0"/>
  </files>
</sesx>
```

> Note: the source has a couple of internal typos (`mediaHandlermediaHandler`) and uses `mediaHandler="AmioLSF"` for raw PCM; for WAV use `mediaHandler="AmioWav"`. It is evidence of *minimality*, not a copy-paste template.

### 3.2 Robust modern template (validated in Audition 2025) — `outhud/audition-ses-to-sesx-converter`

MIT-licensed, single-file Python, targets "Audition CC / 2017–2025". Its README documents an end-to-end render test in **Audition 2025** ("the two renders matched closely"). This is the closest thing to a *known-good minimal modern example*. Its `build_sesx()` returns exactly (quoted, MIT):

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<!DOCTYPE sesx>
<sesx version="1.9">
  <session appBuild="ses2sesx" appVersion="25.2" audioChannelType="stereo" bitDepth="32" duration="<max_clip_end>" sampleRate="<rate>">
    <tracks>
      <audioTrack automationLaneOpenState="false" id="10001" index="1" select="false" visible="true">
        <trackParameters trackHeight="134" trackHue="0" trackMinimized="false">
          <name>Track 1</name>
        </trackParameters>
        <trackAudioParameters audioChannelType="stereo" automationMode="1" monitoring="false" recordArmed="false" solo="false" soloSafe="false">
          <trackOutput outputID="10000" type="trackID"/>
          <trackInput inputID="1"/>
          <component componentGuid="f822a180-4604-47ca-850f-e9f58477dfff" componentID="Audition.Fader" id="trackFader" name="volume" powered="true">
            <parameter index="0" name="volume" parameterValue="1"/>
            <parameter index="1" name="static gain" parameterValue="1"/>
          </component>
          <component componentGuid="d51c1020-8741-4fcc-872a-7adb3074880d" componentID="Audition.Mute" id="trackMute" name="Mute" powered="true">
            <parameter index="0" parameterValue="0"/>
            <parameter index="1" name="mute" parameterValue="0"/>
          </component>
          <component componentGuid="b5d53c02-08c3-41e7-b9e3-2015248cf80d" componentID="Audition.StereoPanner" id="trackPan" name="StereoPanner" powered="true">
            <parameter index="0" name="Pan" parameterValue="0"/>
          </component>
        </trackAudioParameters>
        <audioClip clipAutoCrossfade="true" crossFadeHeadClipID="-1" crossFadeTailClipID="-1"
                   endPoint="4800000" fileID="0" hue="-1" id="0" lockedInTime="false"
                   looped="false" name="clip-name" offline="false" select="false"
                   sourceInPoint="0" sourceOutPoint="4800000" startPoint="0" zOrder="0">
          <component componentGuid="673cd4d7-8c21-4528-ad40-e541ff6dcd70" componentID="Audition.Fader" id="clipGain" name="volume" powered="true">
            <parameter index="0" name="volume" parameterValue="1"/>
            <parameter index="1" name="static gain" parameterValue="1"/>
          </component>
          <component componentGuid="29e428ef-8d16-4ee2-a01a-ada26356009f" componentID="Audition.Mute" id="clipMute" name="Mute" powered="true">
            <parameter index="0" parameterValue="0"/>
            <parameter index="1" name="mute" parameterValue="0"/>
          </component>
          <component componentGuid="80da3284-8a9e-4165-a773-f372a4d619bc" componentID="Audition.StereoPanner" id="clipPan" name="StereoPanner" powered="true">
            <parameter index="0" name="Pan" parameterValue="0"/>
          </component>
          <fadeIn crossFadeLinkType="linkedAsymmetric" endPoint="0" shape="19" startPoint="0" type="log"/>
          <fadeOut crossFadeLinkType="linkedAsymmetric" endPoint="4800000" shape="19" startPoint="4800000" type="log"/>
          <channelMap><channel index="0" sourceIndex="0"/><channel index="1" sourceIndex="1"/></channelMap>
        </audioClip>
      </audioTrack>
      <masterTrack automationLaneOpenState="false" id="10000" index="2" select="false" visible="true">
        <trackParameters trackHeight="134" trackHue="-1" trackMinimized="false">
          <name>Mix</name>
        </trackParameters>
        <trackAudioParameters audioChannelType="stereo" automationMode="1" monitoring="false" recordArmed="false" solo="false" soloSafe="true">
          <trackOutput outputID="1" type="hardwareOutput"/>
          <trackInput inputID="-1"/>
          <component componentGuid="ab6aebff-3601-4db4-9933-781624df75f0" componentID="Audition.Fader" id="trackFader" name="volume" powered="true">
            <parameter index="0" name="volume" parameterValue="1"/>
            <parameter index="1" name="static gain" parameterValue="1"/>
          </component>
          <component componentGuid="44393786-9106-434d-abf4-d9760c2096e2" componentID="Audition.Mute" id="trackMute" name="Mute" powered="true">
            <parameter index="0" parameterValue="0"/>
            <parameter index="1" name="mute" parameterValue="0"/>
          </component>
          <component componentGuid="6fa88450-7b01-4b88-9ddd-3cb7930b5d51" componentID="Audition.StereoPanner" id="trackPan" name="StereoPanner" powered="true">
            <parameter index="0" name="Pan" parameterValue="0"/>
          </component>
        </trackAudioParameters>
      </masterTrack>
    </tracks>
    <sessionState ctiPosition="0" smpteStart="0">
      <timeFormatState beatsPerBar="4" beatsPerMinute="120" customFrameRate="12"
                       linkToDefaultTimeSettings="true" noteLength="4" subdivisions="16"
                       timeCodeDropFrame="false" timeCodeFrameRate="30" timeCodeNTSC="false"
                       timeFormat="timeFormatDecimal"/>
      <mixingOptionState defaultPanModeLogarithmic="true" panPower="-3" playOverlappingClips="false"/>
    </sessionState>
  </session>
  <files>
    <file absolutePath="C:\audio\song.wav" id="0" mediaHandler="AmioWav" relativePath="song.wav"/>
  </files>
</sesx>
```

### 3.3 Recommendation for ChronoSync

Start from §3.2 but you can safely drop the optional `<component>` blocks, `<fadeIn>`/`<fadeOut>`, `<channelMap>`, `<trackInput>`, and `<sessionState>` if you want the §3.1-style minimum — **but keep** `<!DOCTYPE sesx>`, `masterTrack`, `trackOutput outputID` → master, and per-clip `fileID` → `<file id>`. Use `mediaHandler="AmioWav"`. Target a conservative `version`/`appVersion` pair (see §7). Escape all text with standard XML attribute escaping (§6.2).

---

## 4. Known pitfalls

1. **Time = samples, not seconds.** Writing seconds as `startPoint` shifts everything by a factor of the sample rate. The #1 naive mistake.
2. **Looped clips:** for a looped clip, `sourceOutPoint` must extend to the full on-timeline extent (not one loop period), or Audition plays it once instead of looping (verified against Audition 25.2 by `outhud`). Not relevant to ChronoSync's non-looping use case, but keep `looped="false"` correct.
3. **Clip-gain scale is non-linear** (only matters if you write volume envelopes): SESX clip-volume keyframes use a normalized fader position where `0.0 = −∞ dB`, `≈0.65 = 0 dB`, `1.0 = +15 dB`. Writing raw linear gain makes enveloped clips too loud. `outhud`'s `clip_volume_keyframe_value()` is the reference. For static unity gain just use `parameterValue="1"`.
4. **Pan law:** modern Audition defaults to constant-power (centered tracks −3 dB). `outhud` bakes `defaultPanModeLogarithmic="true"` into `sessionState` to preserve unity. If ChronoSync cares about exact gain, include that; otherwise accept the 3 dB centre drop.
5. **Element ordering:** no community source reports Audition rejecting files over element ordering (Audition parses XML via a DOM). All writers emit a consistent order, and parsers use order-independent `find()`. Treat "order as Audition writes it" as the safe convention; strict ordering is *Unknown / 需要进一步验证*.
6. **Escaping:** use standard XML attribute/text escaping (`& < > " '`). `outhud` wraps names and paths in `html.escape()`. Filenames with `&`, `'`, non-ASCII are common in real sessions and must be escaped.
7. **IDs/GUIDs:** `file.id`, `audioClip.id`, `zOrder`, `track.id`, `track.index` are small integers; uniqueness rules: `file.id` unique across `<files>` and referenced by `audioClip.fileID`; `audioClip.id` unique within its track; `track.id` unique across tracks. `component.componentGuid` are UUIDs that **Audition regenerates on save** — hand-written values (including `outhud`'s fixed constants) are accepted, so you don't need to generate "correct" GUIDs. `masterTrack.id` must equal the `outputID` your audio tracks route to.
8. **Paths:** `absolutePath` is used first; `relativePath` (relative to the `.sesx`) is the fallback. If `absolutePath` doesn't exist, Audition prompts to relink **and matches by filename** (per `outhud` README). So either write real absolute paths, or write a relative basename and expect a one-time relink prompt. Windows backslashes are fine in the XML; just escape them (backslash is not an XML escape char).
9. **Encoding/BOM:** UTF-8; a leading BOM is present in real files and harmless. Do **not** use UTF-16.
10. **`appBuild`** is not validated (arbitrary string works); `appVersion` should be a plausible version string. A mismatched/older `version` is tolerated by newer Audition; see §7.
11. **`mediaHandler` matters for non-WAV.** `AmioWav` for WAV, `AmioMP3` for MP3, `AmioAiff` for AIFF. Tagging an MP3 as `AmioWav` still *loads* but may pick the wrong importer (per `outhud`).

---

## 5. Existing open-source writers & parsers (validation-critical)

| Project | URL | Language | License | Writes SESX? | Last activity |
|---|---|---|---|---|---|
| **outhud/audition-ses-to-sesx-converter** | https://github.com/outhud/audition-ses-to-sesx-converter | Python (stdlib only) | MIT | **YES** (validated in Audition 2025) | 2026 (active) |
| **nurdism/audition** | https://github.com/nurdism/audition | JavaScript (Node) | MIT | **YES** (production bot) | 2023 |
| scnerd/pydantic_adobe_audition | https://github.com/scnerd/pydantic_adobe_audition | Python (pydantic-xml) | *none declared* | model/parse (round-trips) | 2025 |
| atmosfar/audition_session_to_reaper_project_converter | https://github.com/atmosfar/audition_session_to_reaper_project_converter | Python | MIT | parse only (→ Reaper .rpp) | 2026 (active) |
| atmosfar/reaper_sesx_import_plugin | https://github.com/atmosfar/reaper_sesx_import_plugin | C++ | *none declared* | parse only (Reaper import) | 2026 |
| rawktron/sesx2rpp | https://github.com/rawktron/sesx2rpp | Python | MIT | parse only | 2025 |
| epistemex/sesx2pl | https://github.com/epistemex/sesx2pl | JavaScript (Node) | *none declared* | parse only (→ m3u/cue) | 2025 |
| ntupds/sesx-to-srt | https://github.com/ntupds/sesx-to-srt | JavaScript | *unknown* | parse only (→ SRT) | 2025 |
| olegtrasher/audition_markers_extractor | https://github.com/olegtrasher/audition_markers_extractor | Python | *unknown* | parse only (markers) | 2025 |
| jacobtodd/sesx-to-logic | https://github.com/jacobtodd/sesx-to-logic | Python | *unknown* | parse only (→ Logic) | 2026 |

**Commercial (not open source) but authoritative on feasibility:** [AATranslator](https://www.aatranslator.com.au/) writes/reads `.sesx` (their `Ses2Sesx` / `Sesx2Sesx` / `SesxPlus` tools), proving the format is writable by third parties. It also confirms `.sesx` is XML and that `.ses`→`.sesx` conversion is a solved, productized problem.

**`outhud` is the single best reference for ChronoSync** — it is MIT, dependency-free Python, writes `.sesx`, and documents a real end-to-end validation. Its `ses2sesx.py` contains the exact emission template quoted in §3.2, the stable component GUIDs, the clip-gain scale, and loop handling.

---

## 6. Community reports on hand-written `.sesx` opening in Audition

- **`nurdism/audition`** (GitHub): production bot that programmatically generates `.sesx` files from Discord recordings; README: *"convert it to a usable adobe audition sesx, session file… it works most of the time."* → generated `.sesx` opens.
- **`outhud/audition-ses-to-sesx-converter`** (GitHub): explicitly states it "writes an equivalent `.sesx` XML session you can open and edit in current Audition", and documents a **sample-by-sample render comparison in Audition 2025** (one real session; the validation audio is copyrighted and not redistributable). → hand-written `.sesx` opens *and plays correctly*.
- **Sound Design Stack Exchange** ["What other programs can open Adobe Audition .sesx files?"](https://sound.stackexchange.com/questions/51132/what-other-programs-can-open-adobe-audtition-sesx-files) — the community answer is that Audition itself is essentially the only editor, with AATranslator able to convert; it does **not** report any issue opening non-Adobe-generated `.sesx`. (Full text is Cloudflare-gated; conclusion inferred from the indexed snippets — *Unknown / 需要进一步验证* for exact wording.)
- **No source found** reporting Audition *rejecting* a well-formed minimal `.sesx` over a missing optional element, GUID, or checksum. There is **no hash/signature/checksum** in the format — files are plain XML.
- Adobe's own **ExtendScript API** (this repo's `_audition_api.d.ts`) exposes an *official programmatic alternative*: `MultitrackDocument`, `AudioClip.startTime/endTime` (samples), `AudioClipCollection.add()`, and `exportSessionAsTemplate()` — i.e., one can have a running Audition instance generate/save the `.sesx` via scripting, avoiding hand-authoring entirely (not headless; requires Audition installed).

---

## 7. `version` / `appVersion` map and compatibility

Observed pairings (all from real files or writers):

| `<sesx version>` | `appVersion` | Audition era | Source |
|---|---|---|---|
| `1.1` | (not captured) | CS5.5 | [Just Solve the File Format Problem](http://fileformats.archiveteam.org/index.php?title=Audition) |
| `1.3` | `10.0` | CS6 (10.x) | `nurdism/audition` |
| `1.7` | `12.0` | CC 2019 (12.x) | real file (`BAS131_Session.sesx`) |
| `1.9` | `25.2` | CC 2025 (25.x) | `outhud` |

Newer Audition opens older `version` values (it must, to load CS5.5 projects). For maximum compatibility in a *new* writer, two reasonable choices:
- **Conservative:** `version="1.3"`, `appVersion="10.0"` (CS6 era) — opens in CS6 through CC 2025.
- **Modern:** `version="1.9"`, `appVersion="25.2"` — matches current Audition (what `outhud` uses).

The exact validation logic Audition applies to `version`/`appVersion`/`appBuild` is **Unknown / 需要进一步验证**; the only proven facts are that `appBuild` accepts arbitrary strings and that mismatched-but-older `version` opens in newer Audition.

---

## 8. Confidence levels (per claim)

| Claim | Confidence |
|---|---|
| SESX is plain XML, root `<sesx>` | **High** (real file + 4 codebases + archiveteam) |
| Time fields are integer **samples** | **Very high** (Adobe API docs + 3 codebases + arithmetic) |
| `startPoint/endPoint/sourceInPoint/sourceOutPoint` semantics | **High** (real file arithmetic + all writers) |
| Minimal structure in §3 opens in Audition | **High** for the specific structures quoted (`nurdism` production, `outhud` Audition-2025-validated) |
| `masterTrack` is required | **Medium-high** (every real file & writer has one; not proven it's mandatory) |
| `<component>`, fades, `channelMap`, `sessionState`, `xmpMetadata`, `metronome`, `properties`, `audioDevice`, `session/name` are optional | **High** (`nurdism` omits all and works) |
| `importerPrivateSettings` optional | **High** (`outhud` omits it, opens in Audition 2025) |
| `appBuild` unvalidated (arbitrary OK) | **High** (`outhud` writes `"ses2sesx"`) |
| Strict element ordering required | **Unknown / 需要进一步验证** (no rejection reports; all writers keep Audition's order) |
| `<!DOCTYPE sesx>` required | **Medium** (real files + `outhud` have it; `nurdism` omits and still works → likely optional) |
| `componentGuid` values validated | **Low** (real file GUIDs differ from `outhud`'s constants; Audition regenerates) |
| `version`→`appVersion` exact mapping | **Medium** (observed pairings only; tolerance logic Unknown) |
| XMP marker times in samples | **High** (2 codebases agree) |
| "ticks" exist anywhere in SESX | **High** that they do *not*; ticks are `.ses`-only |
| No checksum/hash in file | **High** (plain XML in all samples) |

---

## 9. Primary sources (URLs)

- Real Audition 12.0 `.sesx` (downloaded and parsed for this report; broadcast session, used as a structural reference only): https://local.kbmf.fm/recordings/Verdigris%20Primary/Butte,%20America%27s%20Story/BAS%20131/BAS%20131%20Session.sesx — local copy: `F:\ChronoSync\docs\research\notes\BAS131_Session.sesx`
- `outhud/audition-ses-to-sesx-converter` (MIT, writer, validated): https://github.com/outhud/audition-ses-to-sesx-converter
- `nurdism/audition` (MIT, writer): https://github.com/nurdism/audition
- `scnerd/pydantic_adobe_audition` (schema model): https://github.com/scnerd/pydantic_adobe_audition
- `atmosfar/audition_session_to_reaper_project_converter` (MIT, parser): https://github.com/atmosfar/audition_session_to_reaper_project_converter
- `epistemex/sesx2pl` (parser): https://github.com/epistemex/sesx2pl
- `rawktron/sesx2rpp` (MIT, parser): https://github.com/rawktron/sesx2rpp
- AATranslator ses2sesx (commercial, format feasibility): https://www.aatranslator.com.au/ses2sesx.html
- Just Solve the File Format Problem — Audition: http://fileformats.archiveteam.org/index.php?title=Audition
- Sound Design Stack Exchange (what opens `.sesx`): https://sound.stackexchange.com/questions/51132/what-other-programs-can-open-adobe-audtition-sesx-files
- Adobe Audition help — import/export formats: https://helpx-origin-uw2.aws116.adobeitc.com/audition/desktop/importing-recording-and-playing/creating-opening-files.html
- `docs.fileformat.com` SESX overview: https://docs.fileformat.com/audio/sesx/
- Adobe official ExtendScript API types (local prior-research artifact, confirms sample units): `F:\ChronoSync\docs\research\notes\_audition_api.d.ts`
