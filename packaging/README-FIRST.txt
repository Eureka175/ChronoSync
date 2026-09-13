ChronoSync — self-contained Windows package
===========================================

Version : see VERSION.txt          (PEP 440 canonical form in parentheses)
License : MIT (see LICENSE)
Repo    : https://github.com/Eureka175/ChronoSync

WHAT THIS PACKAGE IS
--------------------
ChronoSync estimates a unified audio timebase for recordings made by
independent devices, aligns them, and models/corrects clock drift. Its core
object is a TimeMap (local device time -> unified global time), not a bare
sample offset.

Everything needed to RUN the CLI is bundled: bin\chronosync.exe contains
Python + NumPy + SciPy + soundfile + soxr. No Python installation required.

WHAT IS INSIDE
--------------
  bin\chronosync.exe        Self-contained CLI (no Python needed).
  wheelhouse\               Offline wheels for a normal Python install:
                            chronosync + numpy/scipy/soundfile/soxr/psutil
                            for CPython 3.11 / win_amd64.
  install-offline.bat       Installs from wheelhouse\ (no network needed).
  handoff\                  Standalone algorithm package for external tools
                            (pure numpy+scipy, with its own self-test).
  docs\                     Architecture, algorithms, offset convention and
                            ADR 001-012 (English).
  examples\                 Small demo pair for a first run (if present).
  CHANGELOG.md, LICENSE, README.md, README.zh-CN.md

QUICK START (bundled executable)
--------------------------------
  bin\chronosync.exe --version
  bin\chronosync.exe info  yourfile.wav
  bin\chronosync.exe gcc   reference.wav target.wav
  bin\chronosync.exe align reference.wav target.wav --json
  bin\chronosync.exe align reference.wav target.wav --sesx session.sesx
  bin\chronosync.exe batch a.wav b.wav c.wav --json --csv align.csv
  bin\chronosync.exe benchmark --suite all

Wireless-microphone channel sync inside multi-stream MP4 files
(e.g. CH1/CH2 wireless vs CH3/CH4 wired; per-file measurement):
  bin\chronosync.exe mp4-sync --folder D:\footage --json delays.json --csv delays.csv
  bin\chronosync.exe mp4-sync clip.MP4 --fix --remux --out-dir fixed

QUICK START (normal Python install, offline)
--------------------------------------------
  pip install --no-index --find-links wheelhouse chronosync[io,dev]
or simply run install-offline.bat.

EXTERNAL TOOL REQUIREMENT
-------------------------
FFmpeg (ffmpeg + ffprobe on PATH) is needed ONLY for:
  * the mp4-sync command (demux/remux of MP4 containers), and
  * the MP4 integration tests.
Every other command (info/gcc/align/batch/test-gcc/benchmark) works fully
offline without FFmpeg. Any modern FFmpeg build is fine; extraction always
uses -ignore_editlist 1 so measurements stay in the content domain.

VERIFICATION
------------
  SHA256SUMS.txt lists the checksum of every distributed file.
  Self-check without input files:
      bin\chronosync.exe test-gcc          (runs the GCC unit-test subset)
  The bundled handoff package has its own independent test:
      python handoff\mp4_channel_sync\test_mp4_channel_sync.py

MEASURED QUALITY (documented, reproducible)
-------------------------------------------
  * 202 pytest (unit + integration) + 16 standalone handoff assertions
  * Benchmark suites: gcc / features / drift / solve
  * Real footage: 19 4K MP4 files (4x mono PCM) — per-file wireless-mic delay
    19.7-29.5 ms (constant within a file, varying across files);
    post-correction verification residual < 0.05 ms
  * Documented honesty rules: sub-sample interpolation is a numerical
    estimate, not an absolute-accuracy claim.

KNOWN LIMITATIONS (see CHANGELOG.md)
------------------------------------
  * TimeMap composition between tracks not measured directly is not
    implemented yet (a constant solved offset is used, with a warning).
  * Reaper RPP export is not implemented; SESX cannot express a
    variable-rate timeline.
  * Large-scale real-world benchmark (Phase 8) is still pending.
