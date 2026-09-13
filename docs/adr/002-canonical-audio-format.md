# ADR-002: Canonical internal audio format

**Status:** Accepted (2025, Phase 1)
**Impact:** io/, fine/, features/ and every core DSP module

## Decision

Before entering the core DSP everything is unified to:

```text
sample rate = 48000 Hz
dtype       = float32
channels    = mono (analysis runs on a quality-weighted downmix; the left/right channel arrays are retained)
```

## Rationale

A unified internal format frees every downstream module (GCC, features, drift)
from branching on the input sample rate / bit depth / channel count; 48 kHz is
the common clock of location recording devices, and integer-to-float conversion
is performed only once, at the decoding boundary.

## Details and constraints

1. **Resampling is only permitted with high-quality sinc/polyphase**: SoXR by
   default (the `soxr` package, quality="HQ"); when it is not installed, fall
   back to `scipy.signal.resample_poly` and emit a warning (lower quality than
   SoXR).
   **`numpy.interp` is explicitly forbidden** as an audio resampling scheme
   (linear interpolation, not band-limited).
2. **Stereo handling**: `left` / `right` / `mono_mix` are retained; `mono_mix`
   is used by default. Channel weight = `max(1 - clip_fraction, 1e-3)²`: a
   persistently clipping channel is **down-weighted, not deleted** (clip
   criterion: fraction of samples with |x| ≥ 0.999).
3. **Long files**: short files are read into RAM whole (`read_canonical`); long
   files are streamed (`iter_chunks`). Known limitation: the edge transients of
   chunked resampling are stitched by the Phase 4 drift layer; the Phase 1
   documentation states this honestly.
4. Input format coverage (already supported in Phase 1): WAV/BWF/RF64/FLAC etc.
   (libsndfile), 44.1/48/other sample rates, 16/24 bit int and 32 bit float,
   mono/stereo/multichannel.
5. `DecodedAudio` always carries `source_sample_rate`, the per-channel
   `clip_fraction` and decoding warnings, so that upper layers can make quality
   decisions.
6. **Container integrity (added in Phase 7 after CI findings)**: when reading
   multi-stream containers (MP4 with several mono PCM streams), decoding must
   be performed in the CONTENT domain:
   * FFmpeg extraction always passes `-ignore_editlist 1` — an edit list (which
     some muxers write to align audio to video) trims the head of a stream on
     some FFmpeg versions (measured: 305 samples with FFmpeg 6 on Linux, none
     with FFmpeg 8 on Windows), which silently biases every relative delay;
   * container `start_time` is reported as INFORMATION ONLY and is never added
     to a measured delay (that would double-count);
   * all streams of one recording must decode to EQUAL sample counts; unequal
     lengths are reported as a container anomaly with the warning
     "bias = trimmed samples", never absorbed silently.
   Rationale: a measurement that is quietly off by a few hundred samples is
   worse than no measurement — the pipeline must detect and report the
   condition instead of returning a plausible-looking number.

## Consequences

* Every API whose unit is "samples" refers to 48 kHz canonical samples (see
  ADR-003).
* Switching to a 96 kHz or float64 internal format is an architectural change,
  requiring a new ADR and a rerun of all benchmarks.
