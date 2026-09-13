# Research Notes: AudioAlign & Aurio (Mario Guggenberger)

> Prepared for the **ChronoSync** project (multi-track audio timebase estimation / auto-alignment / clock-drift correction).
> All facts below are sourced from the public GitHub repositories, the author's project pages, and the actual source code
> fetched from `github.com/protyposis/*` on the `main` branch. Items that could not be verified are explicitly marked
> **Unknown / 需要进一步验证**.

---

## 1. AudioAlign

### 1.1 Repo, language/platform, license, activity, maturity

| Field | Value | Confidence |
| --- | --- | --- |
| Repo URL | <https://github.com/protyposis/AudioAlign> | High |
| Language / platform | C# / .NET (WPF desktop GUI), targets .NET SDK 6.0, Visual Studio 2022 | High |
| License | **GNU Affero General Public License v3 (AGPL-3.0)** — "Copyright (C) 2010-2023 Mario Guggenberger" | High |
| Stars / forks | 206 / 21 (as of research date) | High |
| Last push | **2024-01-30** (release v1.7.0) | High |
| Archived | No | High |
| Open issues | 18 | High |
| Maturity | **Mature research tool, in maintenance/dormant mode.** Developed since 2010 (master's thesis), published at IEEE ISM 2012 ([DOI 10.1109/ISM.2012.79](http://dx.doi.org/10.1109/ISM.2012.79)); the underlying library was published at ACM MM 2015 ([DOI 10.1145/2733373.2807408](http://dx.doi.org/10.1145/2733373.2807408)). | High |

License exact text (README): *"This project is released under the terms of the GNU Affero General Public License."* See `LICENSE`.
Source: [AudioAlign README](https://github.com/protyposis/AudioAlign), [GitHub API metadata](https://api.github.com/repos/protyposis/AudioAlign), [CHANGELOG](https://github.com/protyposis/AudioAlign/blob/main/CHANGELOG.md).

### 1.2 Purpose and scope

AudioAlign is a **research tool (GUI) for automatic and semi-automatic synchronization of audio/video recordings** that were
recorded in parallel at the same event or share the same aural content — including recordings that suffer from **clock drift**.
Per the author's project page: *"It uses audio fingerprinting to determine overlapping intervals in recordings and refines
them with dynamic time warping. The tool can be used to synchronize hundreds of clips and offers an interactive timeline for
manual inspection and refinement. The synchronized result can be exported as EDL (Sony Vegas) for post-production."*
([protyposis.net/projects/audioalign](https://protyposis.net/projects/audioalign/))

Scope:
- Multitrack timeline GUI: drag & drop audio/video files as multiple tracks (or `SHIFT` to concatenate as one track), playback, zoom, track selection, manual horizontal repositioning.
- Use cases: multicamera cuts, event coverage, replacing bad audio/video tracks, detecting "interesting moments" (many simultaneous recordings), mashups, comparing live performances/cover versions, voice dubbing, ground-truth creation, fingerprinting-algorithm evaluation.
- It is explicitly a thin GUI over **Aurio** ("designed as a GUI for the Aurio library").

### 1.3 Core algorithms (as supported by sources)

#### Coarse alignment / matching strategy
- **Audio fingerprinting** is the coarse matching strategy (not metadata, not raw cross-correlation search). Confirmed by the project page and source (`Models/*FingerprintingModel.cs`, `MatchingWindow.xaml.cs`).
- Four fingerprint algorithms are exposed in the UI and implemented in Aurio:
  1. **Haitsma & Kalker 2002** ("A highly robust audio fingerprinting system", ISMIR 2002)
  2. **Wang 2003** ("An Industrial Strength Audio Search Algorithm" / Shazam-style constellation, ISMIR 2003)
  3. **Echoprint** (Ellis/Whitman/Porter 2011)
  4. **Chromaprint / AcoustID**
- Each fingerprint is a **subfingerprint = hash + temporal index** (`SubFingerprint`, `SubFingerprintHash`, `FingerprintGenerator`, `FingerprintStore`). Matching = hash-collision lookup between tracks → produces a list of `Match` objects (`Track1`, `Track2`, `Track1Time`, `Track2Time`, `Similarity`, `Source`). A match's initial `Source` is `"FP"` (fingerprint); after cross-correlation refinement it becomes `"CC"`.
- The Haitsma-Kalker default profile: `SampleRate = 5512`, `FrameSize = 2048`, `FrameStep = 64` (hash time step ≈ 64/5512 ≈ **11.6 ms**), 33 logarithmically-spaced frequency bands 300–2000 Hz, `FlipWeakestBits = 3` (`Matching/HaitsmaKalker2002/DefaultProfile.cs`).
- The Wang 2003 default profile: `SamplingRate = 11025`, `WindowSize = 512`, `HopSize = 256`, `PeaksPerFrame = 3`, `PeakFanout = 5`, target zone 30 frames × 63 bins (`Matching/Wang2003/DefaultProfile.cs`).

#### Fine alignment
- **Normalized cross-correlation (time-domain), not GCC-PHAT.** `Aurio.Matching.CrossCorrelation` implements Pearson-style cross-correlation (mean-subtracted, normalized by √(Σx²·Σy²)) swept over a delay range, and picks the **integer-sample lag with maximum absolute correlation coefficient**.
- Audio is first **downmixed to mono, converted to IEEE float, and resampled to 11050 Hz** at `ResamplingQuality.Medium` (`CrossCorrelation.PrepareStream`).
- `CrossCorrelation.Adjust(match, …)` refines a single fingerprint match using a **1-second window** around the matched position, with `maxdelay = sampleRate * seconds / 4` (i.e. ±25% of the window). It returns a new match whose `Track2Time` is shifted by the CC offset and whose `Similarity = result.AbsoluteMaxValue` (the correlation coefficient), `Source = "CC"`.
- **No subsample/parabolic interpolation was observed** in `CrossCorrelation.cs` — the peak is at integer sample lag, so fine-alignment precision ≈ 1 sample @ 11050 Hz ≈ **~90 µs**. (Subsample interpolation: **Unknown / not present in the code inspected** — see §1.7.)

#### Clock drift handling
- Drift is handled by **piecewise-linear time warping with variable-rate resampling**, not a single global scaling constant.
- Pipeline (from `MatchProcessor.cs` and `MatchingWindow.xaml.cs`):
  1. Multiple fingerprint matches between a track pair are sorted and `ConvertToIntervals()` groups consecutive matches whose offset differences stay below a threshold (default **1000 ms**) into intervals — this also detects the case where one track contains two separate excerpts of another.
  2. Each interval / anchor becomes a **`TimeWarp`** mapping (`From` → `To` source↔target time positions).
  3. `TimeWarpStream` wraps a source stream with a `TimeWarpCollection`; between two consecutive mappings it runs a `ResamplingStream` at `ResamplingQuality.VariableRate` with a per-segment `SampleRateRatio`, i.e. it **resamples the audio** to correct the local clock-rate mismatch.
- A manual **"Drift calculation"** UI exists: select two matches between two tracks → it reports `driftPercentage = 100 / d1 * d2` from the time differences.
- The author also maintains a *separate* Android app **ClockDrift** and a **GPS-calibrated drift-measurement** guide (Spectrum Lab + Garmin GPS 18x LVC 1PPS) for *measuring* device drift; these are measurement tools, not part of AudioAlign's correction path. ([Clock Drift intro](https://protyposis.net/clockdrift/), [GPS guide](https://protyposis.net/clockdrift/high-precision-audio-drift-measurements-with-gps/))

#### Multi-track handling
- **Pairwise + reference-track anchoring.** `MatchProcessor.GetTrackPairs()` generates **all track pairs**; `DetermineMatchGroups()` groups tracks into connected components (`MatchGroup`); `AlignTracks(matchPairs)` sets each track's `Offset` from matches.
- A track can be **`Locked`**, which acts as the reference/anchor: `MatchProcessor.Align(match, trackToAdjust)` refuses to move a locked track, so unlocked tracks are aligned relative to the locked one. Track offsets are applied cumulatively (`match.Track1.Offset = match.Track2.Offset + match.Track2Time - match.Track1Time`).
- `MatchProcessor.ValidateMatches()` is required before alignment; it rejects overlapping/crossing match sequences.

#### Non-linear time mapping
- **Piecewise linear**, implemented via `TimeWarpCollection` (ordered, non-overlapping `TimeWarp` mappings with per-interval `SampleRateRatio`) + `TimeWarpStream` (which crops each segment and resamples it at the segment's ratio, advancing segment-by-segment). Mapping arithmetic is kept in bytes internally (`ByteTimeWarp`) to avoid TimeSpan↔byte rounding errors.
- In addition, the GUI offers a **DTW / OLTW** refinement (`TimeWarpType.DTW` / `TimeWarpType.OLTW`, Dixon 2005 "Live tracking…" on-line time warping) that computes a dense warp path between two tracks and converts it into filtered/smoothed matches (default: `TimeWarpFilterSize = 100` points, optional smoothing, `TimeWarpSearchWidth = 10 s`).
- The DTW/OLTW feature is a **spectral-difference frame** (`Matching/Dixon2005/FrameReader.cs`): STFT window 2048 @ 44100 Hz (≈46 ms), hop 882 (≈20 ms), Hamming, magnitudes-squared → 84-dim log-frequency frame (17 linear bins to 370 Hz + 66 log bins 370 Hz–12.5 kHz + 1 bin above 12.5 kHz), then **half-wave-rectified first-order difference** and L1 normalization — i.e. the MATCH/Dixon-style onset-difference representation, not chroma.

#### Validation / confidence measures
- Per-match **`Similarity`** value: fingerprint match strength for `"FP"` matches, or the **normalized cross-correlation coefficient** (`AbsoluteMaxValue`) for `"CC"` matches.
- Match filtering modes: `MatchFilterMode.Best | First | Mid | Last`; `WindowFilter` applies a sliding window (default **30 s**) and keeps the best match per window.
- `MatchProcessor.ValidateMatches` / `ValidatePairOrder` / `FilterDuplicateMatches` / `FilterCoincidentMatches` clean up and validate the match set before alignment.
- A separate **`Analysis`** module (`AnalysisMode.CrossCorrelationOffset | Correlation | Interference | FrequencyDistribution`) sweeps windowed pairs of tracks and computes an alignment-quality **score** (e.g. correlation / destructive-interference measurement) — used for inspecting/validating how well tracks line up over time.
- Export of matches to **CSV** (`ExportMatchesCSV`) exposes per-match similarity/offset for external validation.

#### DAW export
- **Sony Vegas EDL** (proprietary text format) — `Project.ExportEDL()` ("Exports a project timeline to Sony Vegas' proprietary EDL text file format"), written by `File → Export Vegas EDL` (`MainWindow.xaml.cs`). This is the only DAW-oriented export found.
- **Sync XML** (`Project.ExportSyncXML`) — recordings (name + offset) and syncpoints (recording1/recording2 + times); matches the JikuMVD synchronization ground-truth format used by the author.
- **Matches CSV** (`Project.ExportMatchesCSV`) — for analysis/validation.
- **Audio export**: mixed-down audio, and per-track audio export (`CommandBinding_FileExportAudioMix`, `CommandBinding_FileExportSelectedTracks`).

#### Audio I/O and resampling
- Decoders: **NAudio** (PCM WAV, managed, MIT), **FFmpeg** (`Aurio.FFmpeg`, very wide container/codec range, Windows+Linux, LGPL), MP3 via Windows ACM (`Aurio.Windows`).
- Resamplers (selectable via a global `ResamplerFactory`):
  - `Aurio` core: managed **NAudio WDL resampler** (cross-platform, MIT)
  - `Aurio.LibSampleRate`: native **libsamplerate** (Secret Rabbit Code), Windows-only binary, BSD
  - `Aurio.Soxr`: native **SoX Resampler**, Windows-only binary, LGPL
  - All three advertise **variable-rate support** (needed for time-warping); quality levels include `ResamplingQuality.Low / Medium / High / VariableRate`.
- **AudioAlign's GUI sets the resampler to SoX by default** (`ResamplerFactory.Factory = new Aurio.Soxr.ResamplerFactory();` in `MainWindow.xaml.cs`).

### 1.4 Data structures / architecture (how sync is represented)

- **`Aurio.Project`** is the shared model consumed by the AudioAlign GUI:
  - `Project` — serializes to **XML** (`FormatVersion = 2`): `AudioTracks` (each with `offset`, `mute/solo/volume/balance/invertedphase/locked`, and `<timewarps>` list of `from`/`to` ticks), `Matches` (track indices + `track1time`/`track2time`/`similarity`/`source`), `mastervolume`.
  - `AudioTrack : Track` — `Offset`, `Locked`, `TimeWarps` (`TimeWarpCollection`), `Volume`, `Mute`, `Solo`, `Balance`, `InvertedPhase`, `MonoDownmix`; `CreateAudioStream(warp: true)` wraps the decoded source in a `TimeWarpStream` to apply offsets + warp mappings on read.
  - `Match` — `Track1/Track2`, `Track1Time/Track2Time`, `Similarity` (float), `Source` (string, e.g. `"FP"`, `"CC"`); `Offset` computed as `(Track1.Offset + Track1Time) - (Track2.Offset + Track2Time)`.
- **Aurio stream graph** — see §2.4; AudioAlign rides on it (each track is a stream that is decoded → IEEE float → downmix → resample → warp).

### 1.5 Performance notes

- No public end-to-end sync benchmarks were found for AudioAlign itself. **Unknown / 需要进一步验证** for "N files in T seconds" figures.
- Cross-correlation runs at 11050 Hz on 1-second windows (cheap); `CrossCorrelation.Adjust` schedules CC operations (`improve scheduling of many CC operations` in CHANGELOG 1.5.0).
- Peak files (`.aapeaks`) and **proxy files** cache waveform/decoded data for UI responsiveness (see Aurio §2.5).
- See Aurio FFT/fingerprint benchmark tools in §2.5 (they are the concrete performance numbers that exist).

### 1.6 Reuse potential for ChronoSync (Python)

- **Copy conceptually (not code — it is C#/.NET):**
  1. **Two-stage pipeline**: fingerprinting → coarse overlapping intervals → per-match normalized cross-correlation refinement → piecewise-linear time-warping to fix drift.
  2. **`Match` model with `Similarity` + `Source` provenance** (track which stage produced each anchor and with what confidence).
  3. **`TimeWarpCollection` / `TimeWarpStream`**: ordered, non-overlapping piecewise-linear mappings, each segment resampled at its own `SampleRateRatio` — a clean, reusable model for clock-drift correction.
  4. **`ConvertToIntervals`** (offset-jump threshold to split multiple excerpts) and **`WindowFilter`** (best-match per sliding window) as post-processing primitives.
  5. **Reference-track semantics** via a "locked" track + pairwise graph of matches (connected components = match groups).
  6. **Confidence = normalized cross-correlation coefficient**, plus validation that rejects overlapping/crossing match sequences.
- **Call Python libraries instead:**
  - I/O & decode: `soundfile`/`librosa`/`pydub`/`ffmpeg` (subprocess or `ffmpeg-python`).
  - FFT/STFT/chroma: `numpy` + `scipy.signal` (`stft`, `resample_poly`), `librosa`.
  - Cross-correlation / GCC: `scipy.signal.correlate` / `fftconvolve` (and `gcc_phat` recipes); high-quality variable-rate resampling via `soxr` / `libsamplerate` Python bindings (`samplerate`, `soxr`).
  - Fingerprinting: `pyacoustid`/`chromaprint`, or `dejavu`, or `Panako`.
  - Existing Python alignment package: **`audalign`** (see §1.7).
- **Python port note:** the `audalign` project (benfmiller) is conceptually parallel to AudioAlign — fingerprinting for coarse alignment + cross-correlation for fine alignment + `fine_align` for relative/drift refinement — but I could **not** confirm an explicit "inspired by AudioAlign" attribution in its README/wiki. Treat the "inspired by" claim as **Unknown / 需要进一步验证**; the *technique overlap* is real and verified.

### 1.7 Limitations / open issues / dead-project risks

- **AGPL-3.0 copyleft** (network clause). Relevant if any code/derivative is reused; the author offers commercial/licensing alternatives for Aurio ("can be built to be free of any copyleft requirements; get in touch").
- **Windows-only GUI**: WPF UI, Visual Studio toolchain; Aurio *core* is cross-platform (Linux build via CMake/Ninja), but AudioAlign's GUI is Windows-centric. **Unknown / 需要进一步验证** whether the GUI builds on Linux/macOS.
- **Effectively dormant since Jan 2024** (v1.7.0); 18 open issues; not archived but no recent activity. Low risk of breaking changes, but little active support.
- **Patent warning** (from Aurio README): Haitsma & Kalker, Wang, and Echoprint fingerprinting methods may be patent-encumbered; usage "may therefore be severely limited."
- **Fine alignment has no subsample interpolation** in the inspected code (integer-sample CC peak at 11050 Hz ≈ 90 µs). For timebase estimation that may be coarser than a GCC-PHAT + parabolic-fit approach would give. (Confirm against any newer code path before relying on it.)
- **Native accelerators are Windows-only binaries** (libsamplerate, Soxr, FFTW, PFFFT "Linux binary not integrated yet" per README); on Linux one is limited to the managed NAudio resampler + Exocortex FFT unless you build natives yourself.

---

## 2. Aurio

### 2.1 Repo, language/platform, license, activity, maturity

| Field | Value | Confidence |
| --- | --- | --- |
| Repo URL | <https://github.com/protyposis/Aurio> | High |
| Language / platform | C# / .NET library (.NET Standard 2.0 lineage → .NET 6), with C native backends; Windows + Linux | High |
| License | **AGPL-3.0** ("Copyright (C) 2010-2023 Mario Guggenberger"), with an explicit note that *"the library can be built to be free of any copyleft requirements; get in touch if the AGPL does not suit your needs."* (i.e. a dual-licensing offer). Component backends carry their own licenses (MIT/BSD/LGPL/GPL/FFTPACK). | High |
| Stars / forks | 164 / 29 (as of research date) | High |
| Last push | **2025-11-28** (latest release v4.2.2, 2025-11-19) | High |
| Archived | No | High |
| Open issues | 1 | High |
| Maturity | **Active, mature library** — the backbone of AudioAlign; published at ACM MM 2015 ([DOI 10.1145/2733373.2807408](http://dx.doi.org/10.1145/2733373.2807408)). | High |

Source: [Aurio README](https://github.com/protyposis/Aurio/blob/main/README.md), [GitHub API metadata](https://api.github.com/repos/protyposis/Aurio), [CHANGELOG](https://github.com/protyposis/Aurio/blob/main/CHANGELOG.md).

### 2.2 Purpose and scope

An **open-source .NET audio library for stream processing, analysis, and retrieval**. Feature set (from README):
- 32-bit floating-point **audio stream processing engine**.
- File I/O (NAudio, FFmpeg).
- FFT / iFFT (Exocortex.DSP, FftSharp, FFTW, PFFFT).
- Resampling (NAudio, libsamplerate, Soxr).
- Windowing, overlap-add, STFT, iSTFT.
- **Chroma**.
- **Dynamic Time Warping** and **On-line Time Warping** (Dixon, "Live tracking of musical performances using on-line time warping", DAFx 2005).
- **Fingerprinting**: Haitsma & Kalker 2002, Wang 2003, Echoprint, AcoustID Chromaprint.
- Audio playback and UI widgets (WPF).
- Explicit claim: *"All audio processing (incl. fingerprinting) is stream-based and supports processing of arbitrarily long streams at constant memory use."*

Originally developed for AudioAlign; "it uses most functionality of Aurio and its sources can also be used as an implementation reference."

### 2.3 Core algorithms

- **Fingerprinting** (the core retrieval feature): four generators, all producing `SubFingerprint` (hash + index) streams into a `FingerprintStore`; matching via hash-collision `ICollisionMap` (`DictionaryCollisionMap`, `SQLiteCollisionMap`).
  - Haitsma-Kalker 2002 and Wang 2003 profile parameters: see §1.3 (they live in Aurio).
- **Matching & refinement**: `CrossCorrelation` (normalized CC, §1.3), `MatchProcessor` (pairing, filtering, windowing, interval conversion, alignment), `Analysis` (alignment-quality measurement modes).
- **Time warping**: `TimeWarp` / `TimeWarpCollection` / `TimeWarpStream` piecewise-linear variable-rate resampling (§1.3); `Dixon2005` `DTW`, `OLTW`, `OLTW2` with the `FrameReader` spectral-difference feature.
- **Chromaprint** port included (`Matching/Chromaprint/` with `Classifier`, `IntegralImage`, `Quantizer`, `Filter`, etc.).

### 2.4 Data structures / architecture (audio graph, IAudioStream)

- **`IAudioStream`** is the central abstraction (seekable, `Position`/`Length`/`Read`), with **`AudioProperties`** (`Format`, `Channels`, `SampleRate`, sample block size).
- Streams compose as **wrappers** (`AbstractAudioStreamWrapper`) around a source:
  `IeeeStream` (to 32-bit float) → `SurroundDownmixStream` / `MonoStream` → `ConcatenationStream` → `VolumeControlStream` → `MixerStream` → `CropStream` → `VolumeClipStream` → `ResamplingStream` → `TimeWarpStream` → sink (`MemoryWriterStream`, `NAudioSinkStream`). (See the README "Stream Processing" example.)
- **Factories for pluggability**: `AudioStreamFactory` (decoder selection by file), `ResamplerFactory` (one global resampler), `FFTFactory` (one global FFT). This makes the resampler/FFT/decoder swappable without changing client code.
- **`AudioTrack`** is Aurio's project-level representation of a file (decoder + optional `TimeWarpStream` + peak/proxy caching); `TrackList<T>` manages the multitrack timeline.
- **`STFT` / `InverseSTFT`** expose frame-wise processing (`ReadFrame`/`WriteFrame`) with configurable window/hop and COLA support.

### 2.5 Performance notes

- **FFT benchmarks** (README + `Aurio.Test.FFTBenchmark`): Exocortex.DSP = "fastest managed FFT" (recommended cross-platform); FFTW = "much faster than the managed implementations" (native, Windows binary, GPL, forward-only); **PFFFT = "even faster than FFTW, recommended for high-performance use"** (native, Windows binary, forward+inverse, FFTPACK license).
- **Fingerprinting benchmark** (`Aurio.Test.FingerprintingBenchmark`) measures per-algorithm throughput.
- **Streaming / constant memory** is a stated design goal and applies to fingerprinting and processing of arbitrarily long streams.
- **Caching**: peak files (`.aapeaks`) for waveform display; CHANGELOG mentions "direct audio proxy file writing" (v4.2.0) and proxy-file correctness fixes (v4.2.2) — i.e. decoded audio proxies are used to speed up repeated access.

### 2.6 Reuse potential for ChronoSync (Python)

- **Reuse design only** (C#/.NET; AGPL). The transferable ideas:
  - A composable **stream/pipe graph** with swappable backend **factories** (resampler, FFT, decoder) — mirrors a Python pipeline built from `numpy`/`scipy`/`soundfile`/`soxr`.
  - **Fingerprint + store + collision-map** design; the four fingerprint choices with their profiles (especially the Haitsma-Kalker 11.6 ms hash step and Wang 2003 11025 Hz constellation parameters) as reference defaults.
  - **Piecewise-linear `TimeWarp` + variable-rate resampling** as the drift-correction primitive.
  - **Normalized cross-correlation refinement** at a reduced (11050 Hz) sample rate for cheap fine alignment.
- **Python equivalents to call instead of porting**: `scipy.signal`/`numpy` (FFT/STFT/correlate/resample_poly), `librosa` (chroma, onset), `soxr`/`samplerate` (variable-rate resampling), `soundfile`/`ffmpeg` (I/O), `chromaprint`/`pyacoustid`/`dejavu` (fingerprinting), `audalign` (all-in-one alignment).
- **Python port**: no direct port of Aurio/AudioAlign was found; `audalign` is the closest conceptual equivalent (see §1.6/§1.7).

### 2.7 Limitations / open issues / dead-project risks

- **AGPL-3.0** (dual-licensing offered). Sub-components carry varied licenses (MIT/BSD/LGPL/GPL/FFTPACK) — a mixed-license tree.
- **Patent warning** for fingerprinting algorithms (Haitsma & Kalker, Wang, Echoprint).
- **Native backends are Windows-only binaries** ("Linux binary not integrated yet" for libsamplerate, Soxr, FFTW, PFFFT); Linux users fall back to managed NAudio resampler + Exocortex FFT unless they build natives.
- **Documentation "not available yet"** (README), so algorithm details must be read from source/examples.
- Active (2025 commits) but essentially a one-maintainer research project; bus-factor risk for a project that would depend on it long-term. For ChronoSync this is moot since it is C# and would not be called from Python directly.

---

## 3. Sources

- [AudioAlign GitHub](https://github.com/protyposis/AudioAlign) · [AudioAlign README](https://raw.githubusercontent.com/protyposis/AudioAlign/master/README.md) · [CHANGELOG](https://github.com/protyposis/AudioAlign/blob/main/CHANGELOG.md)
- [Aurio GitHub](https://github.com/protyposis/Aurio) · [Aurio README](https://raw.githubusercontent.com/protyposis/Aurio/main/README.md) · [CHANGELOG](https://github.com/protyposis/Aurio/blob/main/CHANGELOG.md)
- [AudioAlign project page](https://protyposis.net/projects/audioalign/) · [Clock Drift introduction](https://protyposis.net/clockdrift/) · [ClockDrift app user guide](https://protyposis.net/clockdrift/user-guide/) · [GPS drift measurement guide](https://protyposis.net/clockdrift/high-precision-audio-drift-measurements-with-gps/)
- IEEE ISM 2012 paper: [AudioAlign – Synchronization of A/V-Streams Based on Audio Data](http://dx.doi.org/10.1109/ISM.2012.79) · ACM MM 2015 paper: [Aurio: Audio Processing, Analysis and Retrieval](http://dx.doi.org/10.1145/2733373.2807408)
- Aurio source (fetched, `main`): `Matching/CrossCorrelation.cs`, `Matching/MatchProcessor.cs`, `Matching/Match.cs`, `Matching/Analysis.cs`, `Matching/Dixon2005/FrameReader.cs`, `Matching/HaitsmaKalker2002/DefaultProfile.cs`, `Matching/Wang2003/DefaultProfile.cs`, `Streams/TimeWarp.cs`, `Streams/TimeWarpCollection.cs`, `Streams/TimeWarpStream.cs`, `Project/Project.cs`, `Project/AudioTrack.cs`, `Project/Track.cs`
- AudioAlign source (fetched, `main`): `MainWindow.xaml.cs`, `MatchingWindow.xaml.cs`
- [audalign (Python) GitHub](https://github.com/benfmiller/audalign) · [audalign README](https://raw.githubusercontent.com/benfmiller/audalign/main/README.md) · [audalign wiki: Recognition Techniques Discussion](https://github.com/benfmiller/audalign/wiki/Recognition-Techniques-Discussion)
