# ChronoSync — Audio I/O & Resampling Stack Research

Status: **Research note** · generated 2026 (session date) · sources linked inline.
Rule applied: unverifiable claims are marked **Unknown / 需要进一步验证**. Confidence tags `[high]` / `[medium]` / `[low]` are per-claim.

---

## 1. PyAV / FFmpeg

### 1.1 License situation

- **FFmpeg is dual-licensed: LGPL-2.1-or-later (default) and GPL-2.0-or-later (opt-in).** The license a binary is distributed under depends entirely on build flags. A build configured with `--enable-gpl` (which pulls in GPL libraries such as `libx264`/`libx265`) must be distributed as **GPL**; a build without `--enable-gpl`/`--enable-nonfree` remains **LGPL**. `[high]`
  - Source: FFmpeg `LICENSE` file, <https://source.ffmpeg.org/?p=ffmpeg.git;a=blob_plain;f=LICENSE;hb=86e107a7>
- **PyAV's own code is BSD-3-Clause.** `[high]`
  - Source: <https://github.com/PyAV-Org/PyAV/issues/805>
- **PyAV's published binary wheels are built against an LGPL FFmpeg** (no GPL / nonfree components), which keeps the whole wheel LGPL-compatible. Verifying exactly which codecs are compiled into a given wheel requires inspecting that wheel's bundled FFmpeg build. `[medium]`
  - Source: <https://github.com/PyAV-Org/PyAV>

> Practical licensing note for an MIT package: LGPL allows *dynamic* linking (or otherwise allowing the user to swap the library) without imposing copyleft on your MIT code. FFmpeg-under-LGPL is therefore usable, but you must preserve FFmpeg's LGPL notice and provide a way for users to relink/replace the FFmpeg library. A GPL FFmpeg build would be incompatible with a permissive MIT distribution.

### 1.2 Decoding arbitrary audio

PyAV wraps FFmpeg's demuxers + decoders, so it can open essentially anything FFmpeg can:

- **Containers/formats**: WAV (incl. **BWF** bext chunks and **RF64**, via FFmpeg's `wav` demuxer), **MP3**, **AAC** (ADTS/raw and inside MP4/M4A), **FLAC**, **OGG (Vorbis/Opus)**, and **video containers** (MP4/MKV/AVI/MOV/TS) with their audio streams. `[high]`
  - Source: PyAV container API, <https://pyav.org/docs/6.1.2/api/container.html>
- **API shape**:
  - `av.open(path)` → `container`; `container.streams.audio` to enumerate audio streams.
  - **Block-wise streaming decode**: `container.decode(audio=0)` is a generator yielding `AudioFrame` objects one at a time — this is the streaming path (it pulls packets, demuxes, and decodes incrementally). `[high]`
  - Each `AudioFrame` exposes `frame.samples` (int count), `frame.sample_rate`, `frame.format` (a `AudioFormat`), `frame.layout`, and `frame.planes`.
  - `frame.to_ndarray()` returns a NumPy array (shape `(samples, channels)` for packed, `(channels, samples)` for planar). `[high]`
    - Source: PyAV audio API, <https://pyav.org/docs/0.5.3/api/audio.html>

### 1.3 Sample format conversion

- **`av.AudioFormat`** describes FFmpeg sample formats (`s16`, `s32`, `flt`, `fltp`, `dbl`, …).
- Conversion between formats (and layouts/rates) is done by **`av.AudioResampler`** (and the higher-level `AudioFifo`/`AudioFrame` resample helpers). `AudioResampler(format=..., layout=..., rate=...)` then `.resample(frame)` → new `AudioFrame`; `resample(frame).to_ndarray()` gives a normalized float/int array. `[high]`
- `frame.to_ndarray()` always gives a numpy array but you should request the target `dtype`/format explicitly for determinism (FFmpeg may choose planar vs packed, and int vs float, depending on decoder output). `[medium]`

### 1.4 Resampling via swresample (and the soxr engine)

- PyAV's `AudioResampler` is a wrapper over FFmpeg's **libswresample** (`swr_*`). `[high]`
- FFmpeg's `swresample` has **multiple resampler engines** selectable at runtime; when FFmpeg is compiled with `--enable-libsoxr`, the engine can be set to **`soxr`** (option name `resampler`, e.g. `resampler=soxr`, with a `precision` quality knob, default 20). The CLI equivalent is the **`aresample`** filter (`-af aresample=...`) / `swr` options. Without `--enable-libsoxr`, swresample uses its own built-in resampler. `[high]`
  - Sources: FFmpeg `libswresample/soxr_resample.c` commit, <https://git.kx.studio/falkTX/FFmpeg/commits/commit/da34e4e13238b755bb0e6ebf549015797d9b4467/libswresample/soxr_resample.c>; mpv option docs, <https://raw.githubusercontent.com/mpv-player/mpv/b56e63e2a96b67aff4050d4db06ee67665893c36/DOCS/man/options.rst>
- **Caveat**: the PyAV wheel's bundled FFmpeg may or may not include `libsoxr`. You generally get the default swresample engine unless you control the FFmpeg build. Whether `resampler=soxr` is available in a given PyAV wheel is **Unknown / 需要进一步验证** (inspect the specific wheel). `[low]`
- **Recommendation for ChronoSync**: do not rely on swresample's soxr engine from PyAV for reproducible results; instead use the dedicated `soxr` Python binding (Section 2) for resampling, and use PyAV primarily for decode + format conversion.

### 1.5 Python 3.12 / 3.13 / 3.14 wheel availability

- PyAV publishes prebuilt wheels on PyPI for **Windows, macOS, and Linux** (`manylinux`/`musllinux`), bundling FFmpeg. Recent release line is `av` 13.x → 14.x → 15.x → 16.x → 17.x (17.1.0 observed on PyPI). `[high]` for existence; `[medium]` for exact mapping.
  - Source: <https://pypi.org/project/av/>
- Python support: recent `av` releases target Python ≥ 3.9 and ship `cp313` / `cp314` wheels in the newest versions. The precise "which `av` version first ships a given cp-tag" mapping is **Unknown / 需要进一步验证** — pin by checking the wheel list on the PyPI `av` files page for your target Python. `[low]`

---

## 2. SoXR / libsamplerate

### 2.1 Licenses (correcting a common assumption)

- **libsoxr is LGPL-2.1-or-later, NOT BSD.** This is confirmed by the Ubuntu/Debian packaging copyright files. `[high]`
  - Source: <https://blueprints.launchpad.net/ubuntu/noble/+source/libsoxr/+copyright>
- **libsamplerate ("Secret Rabbit Code") is BSD-2-Clause.** `[high]`
- **Python `soxr` package (dofuuz/python-soxr)**: the Python/Cython binding code is **BSD-3-Clause**, but it bundles/vendors **libsoxr (LGPL-2.1)**, so the effective distribution obligations include LGPL-2.1 for the vendored C library. `[medium]` for the exact split; the LGPL component is `[high]`.
  - Sources: <https://github.com/dofuuz/python-soxr>; <https://python-soxr.readthedocs.io/en/v0.4.x/#credit-and-license>
- **Python `samplerate` package (python-samplerate)**: CFFI + NumPy binding to system libsamplerate; BSD-2-Clause aligned with the C library. `[medium]`
  - Source: <https://github.com/arlofaria-cartesia/python-samplerate>

### 2.2 Quality & SNR claims

- **libsamplerate** documents its sinc converters with worst-case SNR figures (from the official API docs):
  - `SRC_SINC_BEST_QUALITY` — ~97 dB SNR, ~97% of bandwidth.
  - `SRC_SINC_MEDIUM_QUALITY` — ~97 dB SNR, ~90% bandwidth.
  - `SRC_SINC_FASTEST` — ~97 dB SNR, ~80% bandwidth.
  - `SRC_LINEAR` — ~24 dB; `SRC_ZERO_ORDER_HOLD` — ~6 dB.
  - These figures are the library's own claims; `[medium]` (documented numbers, not independently re-measured here).
  - Source: libsamplerate API docs (e.g. <https://docs.rs/crate/libsamplerate-sys/0.1.0/source/libsamplerate/doc/api_misc.html>)
- **libsoxr** is derived from SoX's `rate` effect and is widely considered to deliver **equal or better quality than libsamplerate at substantially higher throughput** for the same quality class (the author's positioning; also reflected in FFmpeg/pulseaudio adopting it as an optional engine). An independent authoritative SNR-in-dB number for libsoxr is **Unknown / 需要进一步验证** — cite the SoX resampler comparison data instead.
  - Source: <https://src.hydrogenaudio.org/compareresults?id1=79aa6302-5403-4b65-98c1-1e03c81f635c&id2=0> (SoX resampler comparison results); pulseaudio adoption thread, <https://lists.freedesktop.org/archives/pulseaudio-discuss/2014-November/022471.html>
- **Python `soxr` quality presets**: `'QQ'` (quick cubic) < `'LQ'` < `'MQ'` < `'HQ'` < `'VHQ'` (default is `'HQ'`). `[high]`
  - Source: <https://pypi.org/project/soxr/>

### 2.3 Algorithms

- Both libraries use **polyphase / bandlimited sinc (windowed-sinc) interpolation** for high-quality modes. libsoxr adds variable-rate support (phase-continuous, suitable for continuous drift correction where the ratio changes per block); libsamplerate's sinc modes are fixed-ratio with full resampler-state semantics. `[high]` for the general algorithm family; `[medium]` for the drift/phase-continuity nuance (verify against soxr's `soxr_process` semantics before relying on it for time-varying ratio).
- libsoxr also has a low-latency design goal and the ability to stream in fixed-size chunks (see 2.4).

### 2.4 Python bindings status

- **`soxr` (python-soxr)** — actively maintained, ships binary wheels (bundles libsoxr), NumPy-first.
  - One-shot: `soxr.resample(x, in_rate, out_rate, quality='HQ')`.
  - **Streaming**: `soxr.ResampleStream(in_rate, out_rate, num_channels, dtype=...)` with `.resample_chunk(chunk, last=False)` — this is the key API for long files / block processing (stateful, keeps filter state between chunks).
  - Input/output `dtype` float32/float64 supported. `[high]`
  - Source: <https://python-soxr.readthedocs.io/en/stable/soxr.html#soxr.ResampleStream>
- **`samplerate` (python-samplerate)** — CFFI binding to system `libsamplerate`; requires the system library present (not self-contained). One-shot via `samplerate.resample(...)`; supports converter-type selection (`sinc_best`, `sinc_medium`, `sinc_fastest`, `linear`, `zero_order_hold`). Streaming (`Resampler` class with `process()`) exists but the ecosystem/forks (e.g. `samplerate-ledfx`) suggest the original project is lower-maintenance. `[medium]`
  - Sources: <https://github.com/arlofaria-cartesia/python-samplerate>; <https://pypi.org/project/samplerate-ledfx/>

**Streaming vs one-shot summary**: use `soxr.ResampleStream` for streaming/long files and time-varying (drift) resampling; use `soxr.resample` for short one-shot conversion.

---

## 3. soundfile / libsndfile

### 3.1 License

- **libsndfile is LGPL-2.1-or-later.** `[high]`
- **python-soundfile (bastibe)** — the Python binding (`soundfile`) is **BSD-3-Clause**, but its wheels **bundle libsndfile (LGPL-2.1)**; a `pysoundfile` name also exists (conda). Effective distribution obligations again include LGPL-2.1 for the vendored C library. `[high]` for LGPL of libsndfile; `[medium]` for the wrapper license split.
  - Sources: <https://github.com/bastibe/python-soundfile/issues/470> (wheel licenses for libsndfile deps); Fedora review, <https://lists.pagure.io/archives/list/package-review@lists.fedoraproject.org/thread/OHJQXZLSNB2CNXMJ6ZOQEHC53FZA7NRW/>

### 3.2 Supported formats

libsndfile reads/writes: **WAV (incl. PCM, IEEE float, ADPCM variants), AIFF, AU, FLAC, OGG (Vorbis, Opus), and RF64**. **BWF** is a WAV file carrying a `bext` broadcast chunk — libsndfile reads/writes it as WAV (the `bext` metadata is exposed via `extra_info` in python-soundfile). **MP3** support depends on the build (libsndfile ≥1.1 with `libmp3lame` or via `libmpg123` in some builds) — treat MP3 as build-dependent. `[high]` for WAV/BWF/RF64/FLAC/OGG; `[medium]` for MP3 (build-dependent).
- Source: <https://libsndfile.github.io/libsndfile/formats.html>

### 3.3 Block reading (`frames` argument)

- `sf.read(path, frames=N, dtype='float64')` reads at most `N` frames (a "frame" = one sample across all channels); returns `(data, samplerate)`. Reading a full file: `sf.read(path)` without `frames`.
- **True streaming / block iteration**: `sf.blocks(path, blocksize=N, dtype=..., ...)` yields successive blocks, and the object API `with sf.SoundFile(path) as f:` supports `f.seek()`, `f.tell()`, and `f.read(frames, dtype, always_2d=True)` — the recommended path for long files and random access. `[high]`
- Source: python-soundfile docs, <https://python-soundfile.readthedocs.io/en/0.10.3post1/>

### 3.4 dtype conversion

- `dtype` parameter converts on read: `'float64'`, `'float32'`, `'int16'`, `'int32'`, etc. libsndfile normalizes integer PCM to **[-1.0, 1.0)** when reading as float. Output array is `(frames, channels)` (2-D) for `always_2d=True`. `[high]`

---

## 4. NumPy / SciPy DSP capabilities

### 4.1 FFT-based cross-correlation (drift/lag estimation)

- **`scipy.fft.next_fast_len(n, real=False)`** — returns the next "fast" FFT length (smooth/composite number, i.e. composed of small primes 2/3/5). Use `real=True` for real-input FFTs. Use it to pad signals to a fast length before correlation for speed (FFT is fastest at smooth lengths). `[high]`
  - Source: <https://scipy.github.io/devdocs/reference/generated/scipy.fft.next_fast_len.html>
- **`scipy.fft.rfft` / `scipy.fft.irfft`** — real-input FFT pair; for linear cross-correlation you must zero-pad to length `>= len(x) + len(y) - 1` before multiplying spectra (or use `scipy.signal.correlate(..., method='fft')` which handles padding internally). `[high]`
- **`scipy.signal.correlate(x, y, method='fft')`** — computes the linear cross-correlation via FFT (equivalent to `scipy.signal.fftconvolve` with conjugation). `method='auto'` picks direct vs FFT; `method='fft'` is O(N log N) and wins for long signals, while direct convolution is O(N·M) and wins for short ones. `[high]`
  - Sources: <https://docs.scipy.org/doc/scipy-1.16.0/reference/generated/scipy.signal.correlate.html>; implementation uses FFT path, <https://github.com/scipy/scipy/commit/d3120e75d483a4c250ff73673a74fb7e8f9cd360>
- **Performance characteristic**: for alignment of long recordings, use `correlate(..., method='fft')` (or manual rfft + `next_fast_len`) and take the argmax of the lag axis; expect O(N log N). Memory is the practical limit for very long files — chunk via overlap-save if needed. `[medium]` (general DSP knowledge, not re-benchmarked).

### 4.2 Peak finding

- **`scipy.signal.find_peaks(x, height=..., distance=..., prominence=..., ...)`** — returns peak indices + a properties dict (`peak_heights`, `prominences`, `widths`, …). Use for locating the cross-correlation peak and its neighbors. `[high]`
  - Source: <https://docs.scipy.org/doc/scipy-1.9.0/reference/generated/scipy.signal.find_peaks.html>
- **`scipy.signal.peak_prominences(x, peaks, wlen=...)`** — computes peak prominence (reliable signal-vs-noise discriminator, better than raw height). `[high]`
  - Source: <https://docs.scipy.org.cn/doc/scipy-1.14.0/reference/generated/scipy.signal.peak_prominences.html>

### 4.3 `resample_poly` limitations

- **`scipy.signal.resample_poly(x, up, down, axis=..., window=('kaiser', 5.0), padtype=..., cval=...)`** — polyphase resampling via `upfirdn` (upsample → FIR anti-alias filter → downsample). Only for **rational** ratios `up/down`. `[high]`
- **Limitations to note for ChronoSync**:
  - **One-shot only** — no stateful/streaming API; you must manually handle block boundaries and filter state for long files. `[high]`
  - **Fixed Kaiser-windowed filter** — quality is "good but not SoXR-class"; not designed for the highest fidelity large-ratio conversions. `[medium]`
  - **dtype preservation bugs** — historically `resample_poly` (and `resample`) did not preserve `float32` and could upcast/change dtype; several open issues exist (scipy #14733, #22684). Verify dtype explicitly for your version. `[medium]`
    - Source: <https://github.com/scipy/scipy/issues/22684>, <https://github.com/scipy/scipy/issues/14733>
  - **End padding** — default `padtype='constant'` zero-pads both ends (edge effects near boundaries). `[high]`
  - Source: <https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.signal.resample_poly.html>

### 4.4 Coherence

- **`scipy.signal.coherence(x, y, fs=..., window=..., nperseg=..., noverlap=..., detrend=...)`** — returns `(frequencies, Cxy)`, the magnitude-squared coherence via Welch's averaged periodogram. Use to assess which frequency bands actually correlate (i.e. whether an alignment/clock model is meaningful). Requires `fs` to return physical Hz. `[high]`
- **Windows**: `scipy.signal.windows.hann`, `hamming`, `blackman`, `kaiser`, `flattop`, plus generic `scipy.signal.get_window(name, Nx, fftbins=...)`. Use `flattop` for accurate amplitude, `hann`/`kaiser` for general spectral analysis. `[high]`

### 4.5 Performance notes (summary)

| Operation | API | Complexity | Notes |
|---|---|---|---|
| FFT (real) | `scipy.fft.rfft` | O(N log N) | pad to `next_fast_len(..., real=True)` for speed |
| X-correlation | `scipy.signal.correlate(method='fft')` | O(N log N) | linear correlation; argmax = lag |
| Peak find | `find_peaks` + `peak_prominences` | O(N) | prominence > height for noise robustness |
| Resample (polyphase) | `resample_poly` | O(N·filter_len) | one-shot, rational ratios only |
| Coherence | `scipy.signal.coherence` | O(N log N) per segment (Welch) | segment/window trade-off |

---

## 5. Recommendation matrix for ChronoSync

| Concern | Primary choice | Fallback | Notes |
|---|---|---|---|
| **Decode (audio files)** | **`soundfile` (libsndfile)** | PyAV (FFmpeg) | soundfile covers WAV/BWF/RF64/FLAC/OGG with simple `frames`/`blocks` streaming and `dtype` conversion; fewer moving parts. Use PyAV when the source is **MP3/AAC/video container** or a codec libsndfile's build lacks. |
| **Decode (compressed / video)** | **PyAV** | (ffmpeg CLI) | `container.decode(audio=0)` block-wise streaming; `to_ndarray()`; format/layout conversion via `AudioResampler`. |
| **Resample** | **`soxr` (python-soxr)** | `scipy.signal.resample_poly` | soxr = high quality + **streaming `ResampleStream`** + wheels. Fallback `resample_poly` when you cannot add the dependency (pure NumPy/SciPy). Do **not** rely on PyAV/swresample's optional `soxr` engine for reproducible results. |
| **Streaming long files** | `soundfile` block read + `soxr.ResampleStream` | `sf.blocks()` + `resample_poly` (manual state) | `ResampleStream` keeps filter state across chunks and supports a **time-varying ratio** (relevant to clock-drift correction). |
| **Drift/lag estimation** | `scipy.signal.correlate(method='fft')` + `find_peaks`/`peak_prominences` | manual `rfft` + `next_fast_len` | use `peak_prominences` to reject false correlation peaks. |
| **License (MIT package)** | BSD-3 wrappers + LGPL C libs are all compatible | — | All of PyAV (BSD), python-soundfile (BSD), python-soxr (BSD) and python-samplerate (BSD) wrappers are permissive; the **C libraries FFmpeg (LGPL), libsndfile (LGPL), libsoxr (LGPL)** impose LGPL obligations — acceptable for MIT if linked dynamically (or vendored with source offered) and notices preserved. **libsamplerate is the only BSD-2 C library**, but its Python binding is lower-maintenance and requires a system lib. |

### License compatibility conclusion (for an MIT Python package)

- **Safe default stack**: `soundfile` + `soxr` + `scipy` — all LGPL-vendored C components (libsndfile, libsoxr) are LGPL, which is compatible with MIT **as long as** the C libraries remain replaceable (standard dynamic linking via wheels) and their notices/licenses are redistributed. `[high]`
- **Avoid**: GPL FFmpeg builds, GPL/nonfree FFmpeg codecs (x264/x265/fdk-aac in a GPL build), and statically linking GPL code. `[high]`
- **Note**: libsoxr being **LGPL (not BSD)** is the single most important correction to verify when people assume the whole SoXR chain is BSD. `[high]`

---

## Sources (primary)

- FFmpeg LICENSE — <https://source.ffmpeg.org/?p=ffmpeg.git;a=blob_plain;f=LICENSE;hb=86e107a7>
- PyAV license issue — <https://github.com/PyAV-Org/PyAV/issues/805>
- PyAV GitHub — <https://github.com/PyAV-Org/PyAV> · PyPI — <https://pypi.org/project/av/>
- PyAV container API — <https://pyav.org/docs/6.1.2/api/container.html>
- FFmpeg soxr_resample.c — <https://git.kx.studio/falkTX/FFmpeg/commits/commit/da34e4e13238b755bb0e6ebf549015797d9b4467/libswresample/soxr_resample.c>
- SoX resampler comparison (hydrogenaudio) — <https://src.hydrogenaudio.org/compareresults?id1=79aa6302-5403-4b65-98c1-1e03c81f635c&id2=0>
- PulseAudio libsoxr adoption — <https://lists.freedesktop.org/archives/pulseaudio-discuss/2014-November/022471.html>
- libsoxr Ubuntu copyright (LGPL) — <https://blueprints.launchpad.net/ubuntu/noble/+source/libsoxr/+copyright>
- python-soxr GitHub — <https://github.com/dofuuz/python-soxr> · docs — <https://python-soxr.readthedocs.io/en/stable/soxr.html#soxr.ResampleStream> · PyPI — <https://pypi.org/project/soxr/>
- python-samplerate GitHub — <https://github.com/arlofaria-cartesia/python-samplerate> · PyPI — <https://pypi.org/project/samplerate-ledfx/>
- libsamplerate API docs (SNR figures) — <https://docs.rs/crate/libsamplerate-sys/0.1.0/source/libsamplerate/doc/api_misc.html>
- libsndfile formats — <https://libsndfile.github.io/libsndfile/formats.html>
- python-soundfile docs — <https://python-soundfile.readthedocs.io/en/0.10.3post1/> · wheel-license issue — <https://github.com/bastibe/python-soundfile/issues/470>
- scipy.fft.next_fast_len — <https://scipy.github.io/devdocs/reference/generated/scipy.fft.next_fast_len.html>
- scipy.signal.correlate — <https://docs.scipy.org/doc/scipy-1.16.0/reference/generated/scipy.signal.correlate.html>
- scipy.signal.find_peaks — <https://docs.scipy.org/doc/scipy-1.9.0/reference/generated/scipy.signal.find_peaks.html>
- scipy.signal.peak_prominences — <https://docs.scipy.org.cn/doc/scipy-1.14.0/reference/generated/scipy.signal.peak_prominences.html>
- scipy.signal.resample_poly — <https://docs.scipy.org/doc/scipy-1.17.0/reference/generated/scipy.signal.resample_poly.html>
- resample_poly dtype bugs — <https://github.com/scipy/scipy/issues/22684> · <https://github.com/scipy/scipy/issues/14733>
