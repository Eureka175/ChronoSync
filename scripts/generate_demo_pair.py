"""Generate reference.wav / target.wav for CLI acceptance.

Usage::

    python scripts/generate_demo_pair.py [output_dir]

The target is the reference delayed by 12345 samples with mild additive
noise, so `chronosync gcc <dir>/reference.wav <dir>/target.wav` must report
``Delay samples ≈ 12345``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from chronosync.io.wav import write_wav  # noqa: E402
from synthetic.delay import delay_samples  # noqa: E402
from synthetic.generators import speech_like  # noqa: E402
from synthetic.noise import additive_gaussian  # noqa: E402

SR = 48_000
DELAY = 12_345


def _normalize(x: np.ndarray) -> np.ndarray:
    return (x / (np.max(np.abs(x)) + 1e-12) * 0.9).astype(np.float32)


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    ref = speech_like(10 * SR, seed=42)
    tgt = additive_gaussian(delay_samples(ref, DELAY), snr_db=30.0, seed=43)

    ref_path = out_dir / "reference.wav"
    tgt_path = out_dir / "target.wav"
    write_wav(ref_path, _normalize(ref), SR)
    write_wav(tgt_path, _normalize(tgt), SR)
    print(f"wrote {ref_path} and {tgt_path} (expected delay = {DELAY} samples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
