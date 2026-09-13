"""Time-shift helpers for synthetic data (ADR-003 sign semantics).

``delay_samples(x, n)`` with ``n > 0`` returns ``y`` where the content of
``x`` appears ``n`` samples LATER in ``y`` (``y[n + k] == x[k]``): the same
event occurs later in the target, matching the convention
``d = t_target - t_reference``. ``n < 0`` shifts the content earlier.
Content falling beyond the array edges is dropped and the opposite edge is
zero-padded — exactly the semantics of a recording that simply starts later.
"""

from __future__ import annotations

import numpy as np


def delay_samples(x: np.ndarray, n: int | float, dtype=np.float32) -> np.ndarray:
    """Shift content by an integer number of samples (see module docstring)."""
    x = np.asarray(x, dtype=np.float64)
    n = int(round(float(n)))
    y = np.zeros_like(x)
    if n >= 0:
        if n < x.size:
            y[n:] = x[: x.size - n]
    else:
        m = -n
        if m < x.size:
            y[: x.size - m] = x[m:]
    return y.astype(dtype)


def fractional_delay(
    x: np.ndarray, delay: float, taps: int = 65, dtype=np.float32
) -> np.ndarray:
    """Fractional delay via a windowed-sinc (band-limited) FIR filter.

    The fractional part is realized by the FIR filter and the integer part by
    sample shifting (:func:`delay_samples`). Boundary regions (first/last
    ``taps//2`` samples) are approximate; the interior is accurate to the
    filter design — tests must evaluate the interior only.

    ``taps`` must be ODD so that ``numpy.convolve(..., mode="same")`` centers
    the kernel correctly (an even-length kernel would add a ``taps//2``
    sample offset).
    """
    if taps % 2 == 0:
        raise ValueError(f"taps must be odd for centered convolution, got {taps}")
    x = np.asarray(x, dtype=np.float64)
    i0 = int(np.floor(delay))
    frac = delay - i0
    m = np.arange(-(taps // 2), taps // 2 + 1)
    h = np.sinc(m - frac) * np.hanning(taps)
    h /= h.sum()  # unit DC gain
    y = np.convolve(x, h, mode="same")
    return delay_samples(y, i0, dtype=dtype)
