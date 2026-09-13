# WhisperSync — Research Notes

> Research target: a project named **"WhisperSync"** described as using *Whisper speech anchors → clock-drift estimation with piecewise correction → GCC refinement → DAW export* for multi-track timebase estimation of independent recordings.

---

## 0. Verdict (read this first)

**No public project with the exact name "WhisperSync" matching the described feature set could be confirmed.** (High confidence — multiple targeted searches were run; nothing matching the full description exists.)

What I actually found:

1. **"WhisperSync" (whispersync.unicornplatform.page)** — a commercial SaaS/API that *refines Whisper's word-level timestamps* using forced alignment. It is **not** a multi-track audio/clock-drift alignment tool and has **no** GCC refinement or DAW export. It is the only thing I found actually calling itself "WhisperSync" in a speech-timing context.
2. **jasalt/WhisperSync** (GitHub) — a Django web app for YouTube **subtitling** via the Whisper API. Unrelated to audio alignment.
3. **The closest real open-source analog** to the *described feature set* is **kaushikgopal/podsync** (Rust): multi-track "double/triple-ender" podcast alignment with VAD, cross-correlation, drift measurement, and DAW-ready WAV output — but it uses **MFCC cross-correlation, not Whisper, not GCC-PHAT, and it reports drift rather than piecewise-correcting it**.
4. The *exact technique* described in the spec (force-align all channels to a master transcript, then linear-best-fit the drift) is documented in **patents**, not open source — see the Descript patents below.

**Bottom line for ChronoSync:** the spec's "WhisperSync" is almost certainly a *composite* of (a) a Whisper forced-alignment/word-timestamp tool and (b) a multi-track audio aligner. Both halves exist separately; the combined "Whisper-anchored, GCC-refined, piecewise-drift, DAW-export" tool does not exist publicly.

---

## 1. Repo URL, language, license, activity status

### 1a. Projects actually named "WhisperSync"

| Project | URL | Language | License | Activity |
|---|---|---|---|---|
| WhisperSync (commercial API) | <https://whispersync.unicornplatform.page/> | n/a (hosted SaaS; API gateway at `whisper-aligned-main-111013c.zuplo.app`) | **Proprietary / commercial** | Site live; blog dated 2024-07-01 |
| jasalt/WhisperSync (a.k.a. WhisperSubs) | <https://github.com/jasalt/WhisperSync> | Python (Django) | **MIT** | Inactive (0 stars; created 2023-10, no recent push) |

### 1b. Closest matches to the described feature set

| Project | URL | Language | License | Activity |
|---|---|---|---|---|
| kaushikgopal/podsync | <https://github.com/kaushikgopal/podsync> | **Rust** | **none stated** (all rights reserved → not directly reusable) | Active (created 2026-02, pushed 2026-03) |
| ellite/anchor-sub-sync ("Anchor") | <https://github.com/ellite/anchor-sub-sync> | Python | **AGPL-3.0** (copyleft) | Active (pushed 2026-06, 21 stars) |
| EtienneAb3d/WhisperTimeSync | <https://github.com/EtienneAb3d/WhisperTimeSync> | **Java** (Python port: SRT-Sync) | **none stated** | Dormant (last push 2024-05, 167 stars) |
| RomainPastureau/find_delay | <https://github.com/RomainPastureau/find_delay> | Python | **GPL-3.0** (copyleft) | Dormant (pushed 2025-08) |

### 1c. Related libraries (technique building blocks)

| Project | URL | Language | License | Activity | Role |
|---|---|---|---|---|---|
| openai/whisper | <https://github.com/openai/whisper> | Python | **MIT** | Active (108k+ stars) | Base ASR + word/segment timestamps |
| m-bain/whisperX | <https://github.com/m-bain/whisperX> | Python | **BSD-2-Clause** | Active (23.8k stars) | Whisper + wav2vec2 forced alignment → accurate word timestamps |
| jianfch/stable-ts | <https://github.com/jianfch/stable-ts> | Python | **MIT** | **Archived** (2.3k stars) | Stabilized/forced-aligned Whisper timestamps |
| nyrahealth/CrisperWhisper | <https://github.com/nyrahealth/CrisperWhisper> | Python | license auto-detection = **NOASSERTION** (verify manually) | Active (1.4k stars) | Controllable transcription with word timestamps |
| readbeyond/aeneas | <https://github.com/readbeyond/aeneas> | Python/C | **AGPL-3.0** (copyleft) | Active repo (2.9k stars) | Classic forced alignment (audio↔text, DTW) |
| faster-whisper (SYSTRAN) | <https://github.com/SYSTRAN/faster-whisper> | Python | **MIT** | Active | CTranslate2 re-implementation of Whisper (fast, int8) |
| whisper.cpp (ggerganov) | <https://github.com/ggerganov/whisper.cpp> | C/C++ | **MIT** | Active | CPU-focused, quantized Whisper inference |

---

## 2. Purpose and scope

- **WhisperSync (commercial)**: a hosted API that takes Whisper's transcript and *re-aligns it to the audio* to produce word-level timestamps accurate to ~50 ms, across 10+ languages. Scope = timestamp precision for subtitling / video editing / dubbing. **No multi-track, no drift, no DAW export.**
- **jasalt/WhisperSync**: generate `.srt` subtitles for YouTube videos via the Whisper API. Scope = subtitling only.
- **kaushikgopal/podsync**: the closest scope match to ChronoSync — align *multiple independently-recorded tracks* (a merged "master" plus per-participant local tracks) so they line up in a DAW. Finds per-track offset, reports clock drift, pads/trims, emits 44.1 kHz / 24-bit WAV.
- **ellite/anchor-sub-sync ("Anchor")**: subtitle synchronization (Whisper) + context-aware translation (NLLB). Hardware-accelerated CLI. Scope = subtitle timing, single reference, not multi-track audio.
- **EtienneAb3d/WhisperTimeSync**: synchronizes Whisper's *timestamps* onto an existing high-quality *text transcript* (SRT↔text). Scope = subtitle timestamp correction for lyrics/karaoke.

---

## 3. Core algorithms

### 3a. Anchor extraction
- **Whisper native**: segment-level timestamps only; word-level timestamps require the `word_timestamps=True` path (attention/cross-attention or DTW alignment on the decoder) — well-known to be *unreliable* out of the box (this is exactly the problem the commercial WhisperSync markets against). High confidence.
- **Forced alignment (the reliable approach)**: run Whisper for the *text*, then align that text back to the audio with a phoneme/character-level aligner:
  - **whisperX** uses a **wav2vec2.0** model to force-align to word boundaries.
  - **stable-ts** uses DTW on Whisper's own cross-attention weights / an external aligner.
  - **aeneas** uses DTW on MFCC features between audio and a forced-synthesis of the text.
  - **CrisperWhisper** re-decodes for verbatim vs. intended text with word timestamps.
- **VAD as anchor pre-filter**: podsync uses **WebRTC VAD** to find contiguous speech regions (up to 3 candidates) before cross-correlation. WhisperX / faster-whisper also use VAD to segment long audio into speech chunks.

**How anchors are matched across recordings** (the spec's core question):
- podsync matches **acoustically** — MFCC features of a candidate speech window from the local track are cross-correlated against the master; a second independent region that agrees on the same offset is used as a corroborating tie-breaker.
- The **Whisper-based** way (in the patents below): each recording is transcribed; the *same word/phrase* in each transcript is an anchor pair (same text, two timestamps — one per device). This is text-mediated matching rather than raw-signal matching.

### 3b. Drift estimation
- **podsync**: measures drift = (offset measured near end of recording) − (offset measured near start). It *reports* this number; it does **not** build a continuous drift model and does **not** piecewise-correct. (High confidence — stated in README/ALGORITHM.)
- **Descript patents** (the technique the spec describes): US20200126583A1 "…the audio drift in the secondary audio track can be reduced by calculating a **linear best fit line**…" and US20200126559A1 "…force-aligning all channels to the timing data associated with the **master transcript**…". This is exactly "transcript anchors → linear drift fit," but it is a **patent**, not released code. (High confidence in the quote; medium confidence in full implementation details — only abstract-level snippets were retrieved.)
- **Linear vs piecewise vs RANSAC**: none of the *open-source* projects implement piecewise drift correction or RANSAC on anchors. Linear fit is the documented approach (patents/podsync). Piecewise correction and RANSAC are *standard techniques* (e.g., `sklearn.linear_model.RANSACRegressor` over (master_time, device_time) anchor pairs) — **Unknown / 需要进一步验证** whether any public repo implements them as described.

### 3c. Fine refinement (GCC-PHAT / cross-correlation)
- **podsync**: **MFCC cross-correlation** (not GCC-PHAT). Long candidates are sub-sampled from start/middle/end; highest-confidence match wins, with cross-region corroboration.
- **find_delay**: plain **cross-correlation** (with optional envelope extraction + band-pass + resampling) to find the delay of one signal inside another. GPL-3.0.
- **GCC-PHAT** (Generalized Cross-Correlation with Phase Transform): a standard, well-documented DSP technique — cross-correlation in frequency domain with magnitude normalized (phase-only), which sharpens the peak and is robust to noise/reverberation. Implementable in a few lines of numpy; **no single canonical library** was found that the described "WhisperSync" uses. (High confidence this is a standard technique; Unknown / 需要进一步验证 whether any named project pairs it with Whisper anchors as described.)

### 3d. Multi-track support
- **podsync**: natively multi-track (1 master + N local tracks). This is the strongest multi-track match.
- **Whisper-anchored multi-track**: only the Descript patents describe it explicitly; no open-source implementation found. (Unknown / 需要进一步验证 for an actual codebase.)

### 3e. Non-linear time mapping / discontinuity handling
- **None of the found open-source tools** implement non-linear (piecewise/curve) time mapping or discontinuity (dropout/gap) handling. podsync only applies a single offset + pad/trim to the end; it does not resample/stretch the middle. (High confidence in what podsync does; the rest is Unknown / 需要进一步验证.)
- The spec's "piecewise correction" implies a piecewise-linear *warp* (time-stretch different segments) or variable-rate resampling — that is the standard approach for clock drift (e.g., via `librosa.effects.time_stretch` or sox/resample at a corrected rate), but no found project ships it.

### 3f. Validation / confidence
- **podsync** reports a per-track **confidence score** (0–1) from the cross-correlation peak and uses a second independent region for corroboration/tie-breaking. Logs offset + confidence + drift per track to a timestamped file. (High confidence.)
- Whisper-anchored approaches do not expose a formal confidence measure in the found repos. (Unknown / 需要进一步验证.)

### 3g. DAW export
- **podsync**: writes **WAV, 44.1 kHz, 24-bit**, length-matched to the master, same directory as input (`{name}-synced.wav`); drop at position 0:00 in any DAW. (High confidence.)
- **WhisperTimeSync / anchor-sub-sync**: export **SRT** (subtitle timeline), not audio. (High confidence.)
- The commercial WhisperSync API: returns **timestamps/JSON**, not DAW audio. (High confidence in "not DAW"; exact response schema Unknown / 需要进一步验证.)

---

## 4. Data structures / API

- **podsync** (CLI): `podsync --master <file> --tracks <f1> --tracks <f2> [--sync-window 120] [--output-suffix synced]`. Internal pipeline: VAD speech regions → MFCC feature vectors → cross-correlation offsets → drift delta → WAV resample/trim/pad. Outputs WAV + a `podsync-<epoch>.log`. No library API (binary CLI). (High confidence.)
- **find_delay** (Python lib): `find_delay(array_or_wav_a, array_or_wav_b) -> delay`; also `find_delays` for multiple excerpts. (High confidence.)
- **WhisperTimeSync** (CLI): `java -jar WhisperTimeSync.jar <srt> <text|srt> <lang>` → aligned SRT.
- **ellite/anchor-sub-sync** (CLI): Whisper transcription + NLLB translation → synced subtitles.
- **WhisperX / stable-ts / faster-whisper / openai-whisper**: Python APIs returning segments with `start`/`end` (and `words` with per-word `start`/`end` when word timestamps enabled). This is the natural "anchor list" data structure for ChronoSync: `[{text, start, end, ...}, ...]`.

---

## 5. Performance (Whisper inference cost; 1–4 hour scalability)

- **Model sizes**: Whisper `tiny`≈39M → `large-v3`≈1.55B params. Word-timestamp/forced-alignment adds an extra alignment pass (wav2vec2 or DTW). (High confidence on sizes.)
- **Speed (approximate, commonly cited — medium confidence, not independently benchmarked here)**:
  - `faster-whisper` (CTranslate2, int8) is typically **~4× faster** than `openai-whisper` with much lower memory; runs large models in near/above real-time on GPU, and on CPU with quantized models.
  - `whisper.cpp` runs quantized models on CPU (ARM/x86), good for edge/long jobs.
  - `openai-whisper` (pure PyTorch fp32/fp16) is the slowest and heaviest of the three.
- **Long audio (1–4 h)**: Whisper is a 30 s-window model; long files must be chunked. VAD-guided chunking (whisperX / faster-whisper's batched `transcribe`) avoids re-transcribing silence and is the recommended path for multi-hour recordings. On a GPU this is minutes; on CPU with int8 it can be roughly real-time or slower. (Medium confidence — order-of-magnitude guidance, environment-dependent.)
- **GCC-PHAT / cross-correlation refinement cost**: negligible vs. Whisper (FFT of a few-second window). VAD+MFCC (podsync path) is near-instant and needs no GPU. (High confidence.)

---

## 6. Reuse potential for ChronoSync

### Recommendation: Whisper as an **optional evidence source**, not a core dependency

The two alignment strategies are complementary and should be pluggable:

1. **Signal-only path (no ML model)** — VAD (WebRTC/Silero) + cross-correlation (MFCC or GCC-PHAT) + linear/piecewise drift fit. Fast, deterministic, license-clean, but requires *the same acoustic content* to be present in all tracks (true for a "double-ender" where a live room mic captures everyone).
2. **Whisper-anchored path** — transcribe each device's track, match identical word/phrase anchors across tracks, fit drift on `(t_master, t_device)` pairs, then GCC-refine near each anchor. Works even when tracks do **not** share raw acoustics (e.g., different mics, far apart), at the cost of a Whisper pass.

### Python libraries to call (with license notes)

| Library | License | Use in ChronoSync |
|---|---|---|
| **faster-whisper** (SYSTRAN) | MIT | Preferred Whisper backend (speed, int8, batched VAD) |
| **whisper.cpp** (ggerganov) | MIT | CPU/edge deployment; bindings via `pywhispercpp` (verify binding license) |
| **openai-whisper** | MIT | Reference implementation; slower, fine for prototyping |
| **whisperX** (m-bain) | BSD-2-Clause | Word-level timestamps via wav2vec2 forced alignment (needs `torchaudio`/`transformers`) |
| **stable-ts** (jianfch) | MIT (archived) | DTW/cross-attention timestamp stabilization; consider fork-pinning |
| **CrisperWhisper** | license = NOASSERTION → **verify before use** | Optional verbatim/intended text control |
| **scipy / numpy** | BSD-3-Clause / BSD-3-Clause | GCC-PHAT / cross-correlation (write it yourself) |
| **librosa** | ISC | time-stretch/resampling for drift correction |
| **WebRTC VAD / Silero VAD** | BSD-3-Clause / MIT | Speech-region detection for the signal path |
| ⚠️ **aeneas** | **AGPL-3.0** | Avoid as a dependency for a proprietary/closed ChronoSync |
| ⚠️ **ellite/anchor-sub-sync** | **AGPL-3.0** | Inspect for ideas; do not vendor into a non-AGPL product |
| ⚠️ **find_delay** | **GPL-3.0** | Reference for delay math; do not link into a closed product |

**License notes:**
- MIT / BSD-2 / BSD-3 / ISC are permissive → safe to bundle or wrap in ChronoSync regardless of ChronoSync's license.
- AGPL / GPL are **copyleft** → using them as a linked dependency can force ChronoSync to be released under the same license. For a closed/commercial project, reimplement the (simple) algorithms instead of importing these.
- **podsync** has **no license** → all-rights-reserved; treat as a *design reference only*, not reusable code.

---

## 7. Limitations

1. **No "WhisperSync" exists with the described feature set.** The spec appears to conflate a forced-alignment service (commercial WhisperSync) with a multi-track audio aligner (podsync) and a patented technique (Descript). Treat the spec's feature list as a *design brief*, not a description of an existing repo.
2. **Whisper word timestamps are unreliable raw** (the commercial WhisperSync exists precisely to fix this); you must add forced alignment (wav2vec2/DTW) to get anchor precision.
3. **Whisper-anchored alignment requires both tracks to contain the same speech** (or at least overlap heavily) and is degraded by music, crosstalk, overlapping speech, and different languages/dialects. It is also useless for instrumental-only audio.
4. **Piecewise/non-linear drift correction is unproven in open source**: only linear fit (patents) and start/end drift reporting (podsync) are documented. Real devices drift roughly linearly but can also glitch/drop samples; the piecewise path needs original R&D.
5. **Licensing traps**: the two most feature-relevant repos (aeneas, anchor-sub-sync) are AGPL; find_delay is GPL; podsync is unlicensed. None can be vendored into a closed product.
6. **Compute cost** for Whisper on multi-hour, multi-track inputs is nontrivial on CPU; GPU or quantized backends (faster-whisper / whisper.cpp) are effectively required for interactive use.
7. **Single-signal cross-correlation (podsync) can mislock** on repeated content (laughter, applause, silence) without the corroborating-window check; confidence scores help but are heuristic.

---

## Sources

- WhisperSync marketing/blog: <https://whispersync.unicornplatform.page/blog/why-whispers-timestamps-are-inaccurate-and-how-whispersync-solves-it/>
- jasalt/WhisperSync: <https://github.com/jasalt/WhisperSync>
- kaushikgopal/podsync (README): <https://github.com/kaushikgopal/podsync>
- ellite/anchor-sub-sync: <https://github.com/ellite/anchor-sub-sync>
- EtienneAb3d/WhisperTimeSync: <https://github.com/EtienneAb3d/WhisperTimeSync>
- RomainPastureau/find_delay: <https://github.com/RomainPastureau/find_delay>
- openai/whisper: <https://github.com/openai/whisper>
- m-bain/whisperX: <https://github.com/m-bain/whisperX>
- jianfch/stable-ts: <https://github.com/jianfch/stable-ts>
- nyrahealth/CrisperWhisper: <https://github.com/nyrahealth/CrisperWhisper>
- readbeyond/aeneas: <https://github.com/readbeyond/aeneas>
- SYSTRAN/faster-whisper: <https://github.com/SYSTRAN/faster-whisper>
- ggerganov/whisper.cpp: <https://github.com/ggerganov/whisper.cpp>
- Descript patents (transcript-anchored multi-channel sync + linear drift fit):
  - US20200126559A1 — <https://patents.google.com/patent/US20200126559A1/en>
  - US20200126583A1 — <https://patents.google.com/patent/US20200126583A1/en>
- OpenAI Whisper discussion on synchronizing subtitles: <https://github.com/openai/whisper/discussions/1770>
