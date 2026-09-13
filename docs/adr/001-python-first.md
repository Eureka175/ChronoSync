# ADR-001: Python-first technical direction

**Status:** Accepted (2025, Phase 1)
**Impact:** Project-wide language and performance strategy

## Decision

Phase 1 (and the default direction) writes Python only:

```text
Python 3.12+ + NumPy + SciPy + mature native audio libraries
```

* FFT: `scipy.fft` (rfft/irfft, `next_fast_len`)
* Signal processing: `scipy.signal` (find_peaks / peak_prominences / lfilter)
* Decoding: `soundfile` (libsndfile: WAV/BWF/RF64/FLAC, chunked reads)
* Resampling: `soxr` (SoXR polyphase); fallback `scipy.signal.resample_poly` + warning
* Cache: SQLite + `.npy/.npz` file-backed arrays

## Rationale

The bottleneck of an audio alignment system lies in the DSP kernels
(FFT/cross-correlation), and NumPy/SciPy already delegates those kernels to
mature C/Fortran implementations; the overhead of the pure-Python glue layer
did not constitute a bottleneck in Phase 1 measurements (60 s full-length GCC
4.5 s, dominated by FFT).

## Consequences

* Introducing Numba / pybind11 / C++ ahead of time is **forbidden**; it is
  considered only once profiling proves the pure-Python glue layer has become
  the bottleneck (Numba first, C extensions second).
* Performance conclusions must be based on benchmarks (wall/CPU/peak memory +
  accuracy), see `benchmarks/benchmark_gcc.py`.
* Existing benchmark data points: 10 s full-length GCC 0.58 s / 223 MB; 60 s
  4.5 s / 867 MB (this machine, first measured 2025-07). A single full-length
  GCC costs ≈ 16 B/sample × multiple buffers in memory, so anything at the
  minute scale or above must be windowed (Phase 4 drift mode).
