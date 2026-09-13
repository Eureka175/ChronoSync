"""WAV writing utilities (synthetic exports, demos, future audio export).

ChronoSync's primary DAW/export output is a *non-destructive timeline
representation* (offsets + time maps + segments), never a re-render. This
module only exists for test material and demo files.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def write_wav(
    path: str | Path, data: np.ndarray, sample_rate: int, subtype: str = "PCM_16"
) -> None:
    """Write mono/stereo float32 data to a WAV file via libsndfile.

    Args:
        path: output path (parent directories are created).
        data: 1-D (mono) or 2-D (channels, n) float32 audio in [-1, 1].
        sample_rate: sample rate in Hz.
        subtype: libsndfile subtype, e.g. "PCM_16", "PCM_24", "FLOAT".
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr[:, None]
    else:
        arr = arr.T  # (n, channels)

    import soundfile as sf

    sf.write(str(path), arr, int(sample_rate), subtype=subtype)
