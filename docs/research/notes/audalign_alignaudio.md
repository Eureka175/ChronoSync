# audalign + alignaudio 调研报告 (Research Notes)

- **Date of research**: current session (live web + GitHub source inspection).
- **Method**: `web_search` plus direct reads of GitHub raw files, GitHub REST API metadata, and shallow clones of both repos into `F:\ChronoSync\docs\research\_repos\`.
- **Primary sources**:
  - audalign: <https://github.com/benfmiller/audalign> — README.md, pyproject.toml, CHANGELOG.md, and source under `audalign/`.
  - alignaudio: <https://github.com/norihiro/alignaudio> — README.md, `src/alignaudio.c`, `configure.ac`, `Makefile.am`, `.github/workflows/build.yml`, `COPYING`.
- Everything below is stated with a confidence level in the final chat summary. Where a fact could not be confirmed from source, it is written as **Unknown / 需要进一步验证**.

---

# Project 1: audalign (benfmiller/audalign)

## 1. Repo URL, language, license, activity, maturity, Python support

| Item | Value | Confidence |
|------|-------|------------|
| Repo URL | <https://github.com/benfmiller/audalign> (PyPI: <https://pypi.org/project/audalign/>) | High |
| Language | Python | High (GitHub API `language: Python`) |
| License | **MIT** (exact). `pyproject.toml` sets `license = "MIT"`; repo has `LICENSE.md`; GitHub API reports `license: MIT` | High |
| Last activity | Actively maintained. GitHub API: `pushed_at = 2026-05-26`, `updated_at = 2026-08-21` (dates as returned by the API at research time). Latest release tag/version in `pyproject.toml` = **1.3.1**; CHANGELOG top entry `[1.3.1] 2025-02-16` | High (dates are API-reported) |
| Maturity | Mature. Created 2020-05-17, ~6 years of development, 149 stars, 9 open issues, extensive CHANGELOG and test suite | High |
| Python version | `requires-python = ">= 3.8"` (pyproject). CHANGELOG: "Support for python 3.11" added in 1.2.4 (2024-01); "Removed python 3.7 support, added 3.10" in 1.1.0 (2022-04). Support for 3.12/3.13 not explicitly declared → **Unknown / 需要进一步验证** | High for ≥3.8 / 3.11; Medium for 3.12+ |

## 2. Purpose and scope

A Python package for **processing and aligning audio files** using four techniques: audio fingerprinting, raw cross-correlation, spectrogram cross-correlation, and visual (spectrogram-image) alignment. It has two stated purposes (README): (1) accurately align many recordings of the same event, and (2) preprocess audio files prior to alignment.

- Aligns "many recordings of the same event" (multi-track), or a single target against a directory (`target_align`).
- Also does **audio recognition** (dejavu-style: identify a file against a set of pre-fingerprinted files).
- Preprocessing utilities: noise reduction (wrapper around `noisereduce`), "uniform leveling", format conversion, metadata reading, and plotting.
- Outputs: shifted WAV files + a combined "total" mix (optionally as a multi-channel WAV), or just a results dict of shift values.

## 3. Core algorithms in detail

### 3.1 Coarse alignment (FingerprintRecognizer)

Source: `audalign/recognizers/fingerprint/fingerprinter.py`, `.../fingerprint/recognize.py`, `audalign/config/fingerprint.py`.

- **Spectrogram**: `matplotlib.mlab.specgram` with `NFFT = fft_window_size = 4096`, Hann window, `noverlap = int(4096 * 0.5) = 2048`, `Fs = sample_rate = 44100`. Log transform `10 * log2(...)` (note: log2, not dB). Optional `freq_threshold` (Hz) zeroes lower bins.
- **Peak extraction**: 2-D local maxima via `scipy.ndimage.maximum_filter` with a neighborhood from `generate_binary_structure(2,1)` iterated by `peak_neighborhood_size` (default 20), combined with `binary_erosion` of the background (to exclude flat zero regions). Peaks are filtered by `default_amp_min` (default 65).
- **Hashing** (constellation/landmark hashing, SHA1-truncated): peaks are paired/tripled within a fan window (`default_fan_value`, default 15) and a time-delta band (`min_hash_time_delta`/`max_hash_time_delta`), then hashed via `hashlib.sha1(...).hexdigest()[:FINGERPRINT_REDUCTION]` (20 hex chars). Four hash styles (`set_hash_style`):
  - `base` — 2 peaks: `freq1|freq2|t_delta` ("creates many matches but insensitive to noise").
  - `panako` — 3 peaks: 2 freq differences + 2 freq bands + 1 time-delta ratio ("few matches, very resistant to noise").
  - `panako_mod` (default) — 3 peaks: 2 freq differences + 1 time-delta ratio.
  - `base_three` — 3 peaks: 3 frequencies + 2 time deltas.
- **Matching**: hash dict `{hash: [t_offset, ...]}` per file. `find_matches` counts, for each candidate file, every offset difference `a_offset - t_offset` where hashes collide; `align_matches` builds a histogram of `offset → count`. The offset with the most hash votes wins. `locality` (optional) enables a sliding-window variant (`locality_align_matches`/`find_loc_matches`) that returns multiple candidate matches and their local regions. `filter_matches` prunes weak counts; `max_lags` bounds the offset search; `process_results` converts frame offsets to seconds.
- **Time resolution**: one frame = `fft_window_size/sample_rate * DEFAULT_OVERLAP_RATIO = 4096/44100*0.5 ≈ 46.4 ms`. (No sub-frame interpolation in the fingerprint path.)

### 3.2 Fine alignment (CorrelationRecognizer)

Source: `audalign/recognizers/correcognize/correcognize.py`, `audalign/config/correlation.py`.

- **Downsampled raw correlation**: audio decoded to **`sample_rate = 8000` Hz** (vs 44100 for fingerprinting), optional 10th-order Butterworth **highpass** at `freq_threshold` (default 200 Hz), optional normalize. `scipy.signal.correlate(against, target)` computes full cross-correlation; `scipy.signal.correlation_lags` gives the lag axis; `scipy.signal.find_peaks(height=filter_matches)` picks peaks (sorted by height). `max_lags` (seconds) zeroes the correlation outside the lag window.
- **Confidence/scale**: `scaling_factor = max_corr / len(correlation) / SCALING_16_BIT` (65536), normalized per length & 16-bit depth; peak heights are normalized correlation values.
- **Locality mode**: splits both signals into overlapping windows (`LOCALITY_OVERLAP_RATIO = 0.5`) and correlates window pairs, accumulating local offset votes — returns multiple candidate offsets plus per-region tuples (`locality_seconds`).
- **Subsample refinement**: **none beyond sample resolution**. `offset_seconds = offset_samples / sample_rate` (e.g. 0.125 ms at 8 kHz). No parabolic/quadratic peak interpolation and no DTW. (Confidence: High — read directly from source.)

### 3.3 Clock drift handling

- **audalign has no clock-drift correction.** A repo-wide grep for `drift|resample|resampy|warp|tempo|stretch|speed` found only unrelated matches (e.g. `speed_of_sound` helper, comments). There is no resampling loop, no time-stretch, no per-chunk re-estimation of a running offset.
- The model is a **single constant offset per file** (plus, optionally, multiple candidate offsets and "locality" tuples describing locally-different offsets — but these are *not* a continuous drift model, and output writing applies only one shift).
- Confidence: **High** (absence verified by grep across the full source clone). For ChronoSync's drift-correction goal this is the main gap.

### 3.4 Multi-track handling

Source: `audalign/align/__init__.py`.

- **Pairwise/all-to-all recognition**: each file is recognized against every other file (fingerprints are shared in memory; alignment distributes per-file work over a `multiprocessing.Pool`).
- **Reference selection**: `find_most_matches` picks the file with the **most matches** (tie-broken by summed match strength) as the reference (shift 0). Then `find_matches_not_in_file_shifts` adds files that did not match the reference but matched a file that already has a shift (a **2-hop** pass). A source-code TODO explicitly notes: *"refactor into a recursive/graph alignment finding method … without only relying on most matched file."*
- So: **not a full graph/consensus solver** — it is "most-matched reference + one-hop indirect coverage". `target_align` fixes the reference to a user-chosen target file.
- `fine_align` re-aligns the already-shifted files against each other (with `max_lags` defaulting to 2 s) and merges via `combine_fine`.

### 3.5 Non-linear time mapping support

- **Not supported.** Only constant offsets (and piecewise "locality" tuples as evidence). No warping/stretching of the timeline.

### 3.6 Validation / confidence / quality metrics

- **`rankings` key** (1–10) added to every result via `rank_alignment`/`rank_recognition` (`audalign/datalign.py`); heuristic decision tree over top-match confidence, second-match proximity, number of matches, locality. README: *"helps determine the strength of the alignment, but is not definitive proof."*
- Per-recognizer strength fields:
  - Fingerprint: `confidence` = hash-match vote count per offset.
  - Correlation: `confidence` = normalized peak height; `scaling_factor` = length/bit-depth-normalized max correlation.
  - Visual: `ssim` (structural similarity) or `mse` (`VisualConfig.CONFIDENCE = "ssim"`).
- Filters: `filter_matches`, `match_len_filter` (default 30), `close_seconds_filter`, `locality_filter_prop`.

### 3.7 DAW export

- **No Reaper RPP export and no DAW-project export.** Grep for `reaper|rpp` found nothing.
- Related: CHANGELOG 0.7.0 — *"alignments are all positive now. You can easily align the files in a DAW by placing the files at the given time mark"* (i.e. positive shift values intended for manual DAW placement). `write_multi_channel=True` writes a single `multi_channel_total.wav` with one input per channel. Otherwise it writes per-file shifted WAVs + a normalized `total.wav` sum.

## 4. API shape

Top-level module functions (all in `audalign/__init__.py`):

- `align(directory_path, destination_path, write_extension, write_multi_channel, recognizer, write_files_unprocessed)` → dict.
- `align_files(file_a, file_b, *files, ...)` → dict.
- `target_align(target_file, directory_path, ...)` → dict.
- `fine_align(results, destination_path, ..., match_index, recognizer)` → dict.
- `recognize(target_file, against_path=None, recognizer=None)` → dict (or `None`).
- `recalc_shifts(results, key, match_index, ...)`, `write_shifts_from_results(...)`, `write_shifted_file(...)`.
- Preprocessing/IO: `uniform_level_file/directory`, `remove_noise_file/directory`, `convert_audio_file`, `get_metadata`, `plot_peaks`, `pretty_print_results`.

Recognizer classes (each holds a `config` object):

- `FingerprintRecognizer` → `FingerprintConfig` (`.set_accuracy(1..4)`, `.set_hash_style(...)`; also `fingerprint_file`, `fingerprint_directory`, `save_fingerprinted_files`, `load_fingerprinted_files`).
- `CorrelationRecognizer` → `CorrelationConfig`.
- `CorrelationSpectrogramRecognizer` → `CorrelationSpectrogramConfig`.
- `VisualRecognizer` → `VisualConfig` (optional `visrecognize` extras).
- Common base: `BaseRecognizer` (`recognize`, `_align`, `align_hook`, `check_align_hook`, `align_post_hook`, `align_stat_print`); config base `BaseConfig`.

**Result dict shape** (no `AlignmentResult` class — results are plain dicts; the user's "AlignmentResult" does not exist in audalign):

- Recognition: `{"match_time": float, "match_info": {against_name: { "offset_seconds": [...], "offset_frames" (offset_samples): [...], "confidence": [...], "locality_seconds": [...], "locality_frames": [...], "sample_rate": int, "scaling_factor": float }}, "rankings": {...}}`.
- Alignment: adds `"names_and_paths"`, per-file top-level shift values (seconds, ≥ 0), `"match_info"`, optional `"fine_match_info"`, and `"rankings"`.

## 5. Performance notes (from README + config docstrings + source)

- **Fingerprint vs correlation**: README — *"Correlation is more precise than fingerprints and will always give a best alignment unlike fingerprinting, which can return no alignment. `max_lags` is very important for fine aligning. `locality` can be very useful."*
- **Accuracy levels** (`set_accuracy`): 1 = fastest/lowest; 3 = "highest recommended"; 4 = "highest accuracy, but can take **several gigabytes of memory for a couple files**" (more fan-out → more fingerprints; larger hash dict). Level tuning changes `default_fan_value`, `default_amp_min`, `min/max_hash_time_delta`.
- **Memory**: all fingerprints are held in memory in the `FingerprintRecognizer` and must be persisted explicitly with `save_fingerprinted_files` (`.json`/`.pickle`).
- **Multiprocessing**: default `True`; `num_processors` defaults to `cpu_count()`. Correlation directory scans and visual alignment parallelize per-file.
- **Correlation cost**: full `scipy.signal.correlate` is O(N·M); mitigated by 8 kHz downsample + `max_lags`. Plotting correlation "can get really slow if the sample rate is high and the audio file is long."
- **Decoding**: via `pydub`/ffmpeg; audio is resampled to the config sample rate and downmixed to mono 16-bit when processed.

## 6. Dependencies and their licenses

From `pyproject.toml` (hard-pinned versions):

| Dependency | Version | License (typical SPDX) | Role |
|------------|---------|------------------------|------|
| numpy | 1.26.4 | BSD-3-Clause | arrays, FFT/specgram math |
| scipy | 1.12.0 | BSD-3-Clause | correlate, find_peaks, ndimage, signal filters |
| matplotlib | 3.8.2 | BSD (PSF-based) | specgram, plotting |
| pydub | 0.25.1 | MIT | audio decode/export (wraps ffmpeg/libav) |
| tqdm | 4.66.2 | MPL-2.0 / MIT | progress bars |
| setuptools | 59.6.0 | MIT | packaging |

Optional extras:

- `noisereduce` (2.0.1, MIT) + `torch` (2.2.0, BSD-3-Clause) — noise reduction.
- `visrecognize`: `Pillow` (10.2.0, HPND/MIT-CMU) + `scikit-image` (0.19.3, BSD-3-Clause) — visual recognizer (SSIM/MSE).

External system dependency: **ffmpeg or libav** (required for decoding/encoding via pydub; README has install instructions). **No librosa** (spectrograms use `matplotlib.mlab.specgram`).

(Note: exact license strings above are the standard SPDX identifiers for those well-known packages; I did not re-download each wheel's LICENSE in this session → Medium confidence on the individual SPDX labels, High confidence on the dependency list/versions.)

## 7. Reuse potential for ChronoSync

- **Pip-installable and directly reusable**: `pip install audalign`. Good as a **baseline/reference implementation** and for cross-checking ChronoSync results; useful for coarse fingerprint alignment, recognition, and preprocessing (uniform leveling / noisereduce).
- **Wrap**: the recognizer/config objects (`FingerprintRecognizer`, `CorrelationRecognizer`, result dicts) can be wrapped behind ChronoSync's own API; `recognize`/`target_align`/`fine_align` map well onto pairwise alignment.
- **Re-implement (gaps for ChronoSync)**:
  1. **Clock-drift estimation & correction** — not present in audalign. (alignaudio, below, is the reference for the algorithm.)
  2. **Graph/consensus multi-track solver** — audalign uses most-matched-reference + 1 hop; ChronoSync likely wants a proper pairwise graph + global solve.
  3. **Subsample/parabolic peak refinement** and possibly DTW — audalign's fine alignment is limited to 1/sample_rate resolution.
  4. **DAW project export (e.g. Reaper RPP)** — not present.
  5. A time-varying/non-linear mapping model if required.
- **License fit**: MIT → safe to reuse/wrap inside ChronoSync regardless of ChronoSync's license.

## 8. Limitations / open issues

- No clock-drift correction; single constant offset per file.
- Reference-selection heuristic ("most matched" file) can fail if the strongest file is not a true reference; no graph optimization (explicit TODO in source).
- Correlation recognizer is O(N·M) and can be slow/memory-heavy on long files; fingerprint accuracy level 4 can use several GB RAM.
- Fingerprints are in-memory only unless manually saved; all fingerprints must use the same hash style to match.
- Hard-pinned dependency versions (numpy/scipy/matplotlib/pydub/tqdm exact pins) may conflict with other ChronoSync dependencies.
- Requires system ffmpeg/libav; decoding to 16-bit mono (processing path) loses multichannel info.
- Rankings are heuristic ("not definitive proof").
- VisualRecognizer needs optional deps and is case-by-case tuned; no librosa integration.
- No non-linear time mapping; no subsample interpolation in fine alignment.

---

# Project 2: alignaudio (norihiro/alignaudio)

> **Important finding**: I did **not** find a *Python* project named "alignaudio". The project `alignaudio` that actually exists is **written in C**, not Python. It is reported here factually (it is genuinely relevant to ChronoSync's drift-correction goal), followed by the closest **Python** matches I found instead.

## 1. Repo URL, language, license, activity, maturity, Python support

| Item | Value | Confidence |
|------|-------|------------|
| Repo URL | <https://github.com/norihiro/alignaudio> | High |
| Language | **C** (single file `src/alignaudio.c`, ~440 lines). GitHub API `language: C` | High |
| License | **GPL-3.0** (exact: "General Public License version 3"; `COPYING` present) | High |
| Last activity | Created **2021-11-22**; last push **2021-11-22** (same day). Effectively inactive since creation. 7 stars, 1 open issue. | High |
| Maturity | **Immature / prototype** — version `0.1.0` (`configure.ac`), single-day history, single C file, no changelog/NEWS content (files are empty). | High |
| Python support | **N/A — not Python.** | High |

## 2. Purpose and scope

- A CLI tool to **align two audio files**, primary use case: replace/overlay the audio of a video with separately-recorded audio. Usage (README):
  1. `ffmpeg -i video-cam.mp4 video-cam-audio.wav` (extract cam audio)
  2. `alignaudio video-cam-audio.wav audio.wav -o audio-aligned.wav`
  3. mux back with ffmpeg.
- Options: `-o <out>` (write aligned output), `-d <file>` (dump internal sweep data for GNUplot), `-c` (compensate clock drift).
- Scope is strictly **two files**, WAV, 16-bit linear PCM.

## 3. Core algorithms in detail

Source: `src/alignaudio.c` (read in full).

### 3.1 Coarse → fine alignment (amplitude-envelope correlation sweep)

- `mkamplitude`: computes a **rectified-mean amplitude envelope** by averaging `|sample|` over blocks of `n_average_for_amplitude` samples.
- `calculate_by_amplitude` is called **3 times** with decreasing block sizes → 3 sweeps (coarse → fine):
  1. `n_average_for_amplitude = 65536` (with baseline subtraction: a moving ~1-minute average `n_samples_base_for_amplitude = 48000*2*60` is subtracted so the peak is detected relative to a local average).
  2. `= 4096` (`n1_average_for_amplitude`).
  3. `= 256` (`n2_average_for_amplitude`).
- **Score**: for each candidate offset in `[cand_min, cand_max]`, `sp = Σ env1[i] * env2[j] / 256` (sum of products of the two envelopes). The offset with max `sp` wins.
- **Sub-sample refinement**: `center_adjust = n_average * (d0 - d1) / (d0 + d1) / 2` using the neighboring scores (parabolic-like peak interpolation), refining `center` below one block.
- Each pass narrows `cand_min/cand_max` to `center ± 2·n_average`.

### 3.2 Clock drift handling (`-c`) — the key feature

- `calculate_drift`:
  1. Downsample both signals to a mono-ish low rate via `div = 4*2 = 8`-sample averaging ("48 kHz stereo → 12 kHz mono" per comment; the code prints using 96e3 samples/sec).
  2. Walk blocks of `n_blk = 65536` samples (step `n_blk*32`); for each block `x`, find the best local offset `y` that maximizes `|Σ d1[i]·d2[j]|` within a small window around the center offset.
  3. Collect `(x, y)` pairs and fit a **linear least-squares** line `y = a·x + b`. `a` is the drift slope; reports `"%.2f ppm drift (2nd audio has slower/faster clock)"` (`a*1e6`).
  4. Sets `center = (offset_c + b)·div`, `center_drift1 = length1`, `center_drift2 = length1·(1+a)`.
- `overwrite_at_center`: maps sample index `i` (file1 timebase) to `j` (file2) via `i·drift2 = j·drift1`, and **resamples by duplicating/skipping sample pairs** (linear sample drop/duplicate — **not** sinc/bandlimited resampling). Overwrites file1's samples with file2's samples at the mapped positions and writes the output WAV.
- Code TODOs (unfinished/rough): *"TODO: adjust drift of the clock period"* and *"TODO: maybe this calculation is too fuzzy. I should make 1s blocks … then use least-square method."*

### 3.3 Multi-track handling

- **Two files only** (`file1`, `file2`). No multi-track, no reference selection, no graph.

### 3.4 Non-linear time mapping support

- **Linear only**: single global offset `b` + single global drift slope `a`. No piecewise or non-linear warping.

### 3.5 Validation / confidence / quality metrics

- **None.** It prints detected ppm and internal debug stats; there is no confidence score, ranking, or match-strength output. (`-d` dumps the raw sweep score curves for the user to plot with GNUplot.)

### 3.6 DAW export

- **None.** Output is a plain WAV (`write_wave` copies the original WAV container with the overwritten samples).

## 4. API shape

- **CLI only**: `alignaudio <file1> <file2> [-o out.wav] [-d data.dat] [-c]`. No library API, no Python bindings.

## 5. Performance notes

- Loads entire WAV files into memory (`load_wave` reads the whole file; envelope and raw buffers malloc'd per sweep).
- Envelope sweep cost is roughly `O(range_in_blocks × n_env)` per pass — cheap at large block sizes; the drift block correlation is `O(n_blocks × local_window × n_blk)`.
- No external DSP libraries — pure C standard library.

## 6. Dependencies and their licenses

- **No external dependencies.** Standard C library only; reads/writes 16-bit linear-PCM WAV directly (its own RIFF parser).
- Build system: GNU Autotools (`configure.ac`, `Makefile.am`, `autogen.sh`); GitHub Actions builds on Ubuntu (`./autogen.sh && configure && make && make check && make distcheck`).
- **Input restrictions**: WAV only; format must be linear PCM (`format == 1`), 16-bit assumed, mono or stereo; other formats return error 114.

## 7. Reuse potential for ChronoSync

- **Not directly reusable as code in Python**: it is C, and **GPL-3.0** (copyleft) — problematic to link/embed in a permissively-licensed Python project without relicensing obligations. (Re-implementing the *algorithm* is license-safe.)
- **Excellent algorithmic reference for drift correction** — the overall design is exactly what ChronoSync needs and is simple to re-implement in numpy/scipy:
  1. Coarse→fine multi-scale envelope (or low-rate) cross-correlation sweep with narrowing search window.
  2. Block-wise local offset estimation at intervals across the recording.
  3. Linear least-squares fit of `offset(x) = a·x + b` → drift in ppm.
  4. Resample one track (sinc/`scipy.signal.resample_poly` rather than sample drop/duplicate) to correct drift.
- **What to improve over alignaudio** in ChronoSync: bandlimited (sinc) resampling instead of sample-drop/duplicate; robust outlier rejection in the block-offset fit; multi-track (pairwise drift graph); confidence metrics; support for non-PCM formats.

## 8. Limitations / open issues

- **Not Python**; C + GPL-3.0.
- Two files only; 16-bit linear-PCM WAV only.
- Prototype maturity (0.1.0), single commit day, empty ChangeLog/NEWS, 1 open issue.
- Linear-only drift model; resampling via sample drop/duplicate (no anti-aliasing → aliasing/quantization artifacts).
- No confidence/validation metric; no subsample refinement beyond the parabolic block interpolation.
- Own TODOs acknowledge the drift block-fit is "too fuzzy".
- Whole-file in-memory loading.

---

# Closest Python matches for "alignaudio" (since the exact-name project is C)

These were found while searching "alignaudio python clock drift audio alignment github"; listed briefly as candidates for ChronoSync to also review. No dedicated "align-audio" or "synctool" project by those exact names was verified in this session → **Unknown / 需要进一步验证** for those two names.

| Project | URL | Language / License | What it does | Activity |
|---------|-----|--------------------|--------------|----------|
| audio-offset-finder (BBC) | <https://github.com/bbc/audio-offset-finder> | Python / **Apache-2.0** | Find offset of one audio within another using cross-correlation of frame-averaged (downsampled) signals via `scipy.fftconvolve`. 227 stars. | last push 2026-04-13 (API) |
| fast-align-audio (nomonosound) | <https://github.com/nomonosound/fast-align-audio> | Python / **ISC** | "Fast python library for aligning similar audio snippets passed in as NumPy arrays" (FFT-based cross-correlation). 50 stars. | last push 2025-10-27 (API) |
| audiosync-cmd (Oran2009 / wanghaisheng fork) | <https://github.com/Oran2009/audiosync-cmd> | Python (CLI) | CLI to automatically sync matching video+audio files. | older |
| Blender power_sequencer "audiosync" | <https://projects.blender.org/blender/blender-addons> (`power_sequencer/operators/audiosync/find_offset.py`) | Python (GPL, part of Blender) | audio-sync operator inside Blender's VSE. | active (Blender) |

**Note on drift in the Python matches**: none of these three obviously implements the block-fit + resample clock-drift correction that `norihiro/alignaudio` does → **Unknown / 需要进一步验证** without deeper source inspection. They are offset-only aligners by description.

---

# Summary comparison table

| Aspect | audalign (Python) | alignaudio (C) |
|--------|-------------------|----------------|
| Language / License | Python / MIT | C / GPL-3.0 |
| Pip-installable | Yes (`pip install audalign`) | No (autotools build) |
| Multi-track | Yes (most-matched reference + 1 hop) | No (2 files) |
| Coarse method | Spectrogram landmark fingerprinting (4 hash styles) | Multi-scale amplitude-envelope correlation (3 sweeps) |
| Fine method | Downsampled (8 kHz) raw cross-correlation | Nested finer envelope sweeps + parabolic sub-sample |
| Spectrogram correlation | Yes (`CorrelationSpectrogramRecognizer`) | No |
| Visual alignment | Yes (`VisualRecognizer`, SSIM/MSE) | No |
| **Clock drift** | **None** | **Yes — block correlation + least-squares ppm fit + sample-drop/duplicate resample** |
| Non-linear mapping | No | No (linear only) |
| Confidence metric | `rankings` 1–10 + per-recognizer confidences | None |
| DAW export | No RPP; multi-channel WAV + positive shifts | No (WAV only) |
| Dependencies | numpy, scipy, matplotlib, pydub, tqdm (+ optional noisereduce/torch, Pillow/scikit-image); needs ffmpeg | C stdlib only |
| Maturity | Mature (v1.3.1, active) | Prototype (0.1.0, inactive) |
