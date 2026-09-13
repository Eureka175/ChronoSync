"""Window scheduling for drift estimation (Layer 4).

Windows are placed on the REFERENCE timeline; the corresponding target
window is the reference window shifted by the current coarse offset (ADR-003:
``d = t_target - t_reference``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WindowSchedule:
    """Sliding-window schedule (default 30 s windows, 50% overlap)."""

    window_samples: int = 30 * 48_000
    overlap_ratio: float = 0.5

    @property
    def stride_samples(self) -> int:
        return max(1, int(round(self.window_samples * (1.0 - self.overlap_ratio))))

    def centers(self, min_center: int, max_center: int) -> list[int]:
        """Window centers ``c`` with ``min_center <= c <= max_center``.

        ``min_center``/``max_center`` are absolute CENTER bounds (already
        margin-corrected by :func:`overlap_center_range`); centers step by
        the stride.
        """
        if max_center < min_center:
            return []
        n = 1 + (max_center - min_center) // self.stride_samples
        return [min_center + i * self.stride_samples for i in range(n)]


def overlap_center_range(
    len_ref: int,
    len_tgt: int,
    offset_samples: float,
    schedule: WindowSchedule,
) -> tuple[int, int]:
    """Center bounds so BOTH windows lie fully inside their signals.

    Reference window: ``[c - w/2, c + w/2)``; target window:
    ``[c + d - w/2, c + d + w/2)``. Returns ``(min_center, max_center)``
    (empty when no full window fits: ``max < min``).
    """
    half = schedule.window_samples // 2
    lo = max(half, half - int(round(offset_samples)))
    hi = min(
        len_ref - half,
        len_tgt - half - int(round(offset_samples)),
    )
    return (lo, hi)
