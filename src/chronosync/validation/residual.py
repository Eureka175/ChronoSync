"""Residual GCC validation (Phase 7).

After alignment, GCC is run again between the reference and the
CORRECTED/aligned target at several positions; the residuals should be near
0 samples. Large residuals mean the TimeMap is wrong locally.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chronosync.fine.gcc_phat import gcc_phat
from chronosync.models.timemap import TimeMap


@dataclass
class ResidualConfig:
    """Residual-check parameters (all configurable, documented)."""

    window_samples: int = 8_192
    positions_seconds: tuple[float, ...] = (0.1, 0.3, 0.5, 0.7, 0.9)
    max_lag_seconds: float = 1.0
    silence_floor_ratio: float = 0.01  # windows below this RMS fraction are skipped


@dataclass
class ResidualResult:
    """Residual offsets at the probed positions (ADR-003 samples)."""

    positions_seconds: list[float]
    residuals_samples: list[float]
    mean_abs_samples: float
    max_abs_samples: float
    warnings: list[str] = field(default_factory=list)


def residual_offsets(
    reference: np.ndarray,
    target: np.ndarray,
    time_map: TimeMap,
    sample_rate: int = 48_000,
    config: ResidualConfig | None = None,
) -> ResidualResult:
    """Probe alignment quality with windowed GCC at several positions.

    ``target`` is on its LOCAL timeline; windows are extracted at global
    positions and mapped back through ``time_map`` (so the drift is
    accounted for). Works with any monotonic TimeMap.
    """
    cfg = config if config is not None else ResidualConfig()
    warnings: list[str] = []
    positions = list(cfg.positions_seconds)
    residuals: list[float] = []
    ref_rms = float(np.sqrt(np.mean(reference.astype(np.float64) ** 2)))
    silence_floor = cfg.silence_floor_ratio * ref_rms

    for p in positions:
        start = int(round(p * sample_rate))
        ref_win = reference[start : start + cfg.window_samples]
        # global window [p, p+W) -> local span via the inverse map
        l0 = time_map.to_local(p)
        l1 = time_map.to_local(p + cfg.window_samples / sample_rate)
        tgt_start = int(round(l0 * sample_rate))
        tgt_len = int(round((l1 - l0) * sample_rate))
        tgt_win = target[tgt_start : tgt_start + tgt_len]
        if tgt_win.size != cfg.window_samples:
            # resample mismatch: compare on the common length
            common = min(ref_win.size, tgt_win.size)
            if common < cfg.window_samples // 2:
                warnings.append(
                    f"position {p:.2f}s: target window too short "
                    f"({tgt_win.size} samples); skipped"
                )
                continue
            ref_win = ref_win[:common]
            tgt_win = tgt_win[:common]
        # skip silent windows (e.g. speech gaps): GCC cannot measure them
        if ref_rms > 0.0 and (
            float(np.sqrt(np.mean(ref_win.astype(np.float64) ** 2))) < silence_floor
            or float(np.sqrt(np.mean(tgt_win.astype(np.float64) ** 2))) < silence_floor
        ):
            warnings.append(f"position {p:.2f}s: silent window; skipped")
            continue
        res = gcc_phat(
            ref_win,
            tgt_win,
            sample_rate,
            search_min=-int(cfg.max_lag_seconds * sample_rate),
            search_max=int(cfg.max_lag_seconds * sample_rate),
        )
        if res.success:
            residuals.append(float(res.delay_samples))
        else:
            warnings.append(f"position {p:.2f}s: GCC failed; skipped")

    mean_abs = float(np.mean(np.abs(residuals))) if residuals else float("nan")
    max_abs = float(np.max(np.abs(residuals))) if residuals else float("nan")
    return ResidualResult(
        positions_seconds=positions[: len(residuals)],
        residuals_samples=residuals,
        mean_abs_samples=mean_abs,
        max_abs_samples=max_abs,
        warnings=warnings,
    )
