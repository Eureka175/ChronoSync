# ADR-008: Coarse-matching cascade

**Status:** Accepted (2025, Phase 3)
**Impact:** coarse/, features/, cache/

## Decision

Coarse matching uses a short-circuit cascade: metadata (prior) → fingerprint →
envelope → transient → No Match; every stage returns a `MatchResult`
(matched/offset/confidence/method/overlap_estimate/evidence/warnings), and the
cascade returns as soon as any stage reaches `accept_confidence`; when all stages
fail it returns the best evidence with matched=False.

## Key implementation decisions

1. **Absolute dB calibration for the fingerprint**: unit-RMS normalization of the
   input + spectral magnitude divided by window energy → a full-energy frame
   ≈ 0 dB. This replaces "relative normalization to the segment maximum" — the
   latter made chunked fingerprints inconsistent with a single computation (each
   chunk had a different threshold baseline; boundary anchors were empirically
   lost/gained). Absolute calibration also guarantees gain invariance across
   files.
2. **Chunked == single-shot**: peak detection needs ±5 frames of real context
   (`maximum_filter` zero padding produces spurious/lost peaks at segment
   boundaries, fixed empirically); inter-chunk overlap of delta_max+2 frames
   covers the anchor partner region. A test pins this down with
   `np.array_equal`.
3. **Vote confidence**: 0.7·vote share + 0.3·peak ratio, then multiplied by the
   `min(1, votes/5)` vote gate — 3 votes/10 hash collisions is not a match.
4. **envelope direction**: the peak of `scipy.signal.correlate(ref, tgt)` = −d
   (cross-validated against GCC and pinned down).
5. **metadata is never matched**: without timecode parsing the mtime prior is a
   search hint, not evidence.

## Consequences

* A coarse-matching accuracy of ±0.5 frames (~23 ms @ 11025 Hz) is by-design
  behaviour; the drift layer refines it;
* cache keys include the algo/feat versions (ADR-006), so a fingerprint
  algorithm change invalidates automatically;
* patent note (ADR-007): the constellation idea is a clean-room implementation;
  commercial use is evaluated separately.
