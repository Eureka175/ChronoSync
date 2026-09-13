"""TimeMap: the core time-mapping abstraction of ChronoSync (ADR-005).

Every track is not a bare offset but a mapping from its LOCAL device timeline
to the unified GLOBAL reference timeline::

    T_global = f(T_local)

The simplest case is T_global = a*T_local + b, where ``a`` captures the clock
scale/drift and ``b`` a constant offset. Discontinuities and piecewise drift
are modeled as ``piecewise_linear`` maps. Business code must depend on the
``TimeMap`` interface, never on concrete offset/alpha/beta fields.

Units: both timelines are expressed in SECONDS. Conversion to/from sample
counts happens at the boundaries using the canonical sample rate
(ADR-002), via :meth:`TimeMap.to_global_samples` / :meth:`TimeMap.to_local_samples`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

from .audio import CANONICAL_SAMPLE_RATE


class TimeMap(ABC):
    """Abstract mapping from local track time to global timeline time."""

    kind: str = "abstract"

    @abstractmethod
    def to_global(self, t_local: float) -> float:
        """Global time (seconds) of a local time ``t_local`` (seconds)."""

    @abstractmethod
    def to_local(self, t_global: float) -> float:
        """Local time (seconds) of a global time ``t_global`` (seconds)."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serializable representation; inverse of :meth:`TimeMap.from_dict`."""

    @abstractmethod
    def is_identity(self) -> bool:
        """True when this map is the identity (T_global == T_local)."""

    def to_global_samples(
        self,
        n_local: int | float,
        sample_rate: int = CANONICAL_SAMPLE_RATE,
    ) -> float:
        """Global sample index (fractional) of local sample ``n_local``."""
        return self.to_global(float(n_local) / sample_rate) * sample_rate

    def to_local_samples(
        self,
        n_global: int | float,
        sample_rate: int = CANONICAL_SAMPLE_RATE,
    ) -> float:
        """Local sample index (fractional) of global sample ``n_global``."""
        return self.to_local(float(n_global) / sample_rate) * sample_rate

    def __call__(self, t_local: float) -> float:
        return self.to_global(t_local)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "TimeMap":
        kind = d.get("kind")
        if kind == "identity":
            return IdentityTimeMap()
        if kind == "constant_offset":
            return ConstantOffsetTimeMap(offset_seconds=float(d["offset_seconds"]))
        if kind == "linear":
            return LinearTimeMap(
                scale=float(d.get("scale", 1.0)),
                offset_seconds=float(d.get("offset_seconds", 0.0)),
            )
        if kind == "piecewise_linear":
            knots = tuple((float(a), float(b)) for a, b in d["knots"])
            return PiecewiseLinearTimeMap(knots=knots)
        raise ValueError(f"unknown TimeMap kind: {kind!r}")


@dataclass(frozen=True)
class IdentityTimeMap(TimeMap):
    """T_global = T_local."""

    kind: str = "identity"

    def to_global(self, t_local: float) -> float:
        return float(t_local)

    def to_local(self, t_global: float) -> float:
        return float(t_global)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind}

    def is_identity(self) -> bool:
        return True


@dataclass(frozen=True)
class ConstantOffsetTimeMap(TimeMap):
    """T_global = T_local + offset_seconds (fixed offset, no drift)."""

    offset_seconds: float = 0.0
    kind: str = "constant_offset"

    def to_global(self, t_local: float) -> float:
        return float(t_local) + self.offset_seconds

    def to_local(self, t_global: float) -> float:
        return float(t_global) - self.offset_seconds

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "offset_seconds": self.offset_seconds}

    def is_identity(self) -> bool:
        return self.offset_seconds == 0.0


@dataclass(frozen=True)
class LinearTimeMap(TimeMap):
    """T_global = scale * T_local + offset_seconds.

    ``scale = 1 + alpha_ppm * 1e-6``; ``alpha_ppm > 0`` means the local
    (target) clock runs faster, i.e. events drift later in target time.
    """

    scale: float = 1.0
    offset_seconds: float = 0.0
    kind: str = "linear"

    def __post_init__(self) -> None:
        if not self.scale > 0.0:
            raise ValueError(f"scale must be positive, got {self.scale!r}")

    @classmethod
    def from_ppm(
        cls, alpha_ppm: float, offset_seconds: float = 0.0
    ) -> "LinearTimeMap":
        return cls(scale=1.0 + alpha_ppm * 1e-6, offset_seconds=offset_seconds)

    @property
    def scale_ppm(self) -> float:
        """Clock-rate offset in parts per million: (scale - 1) * 1e6."""
        return (self.scale - 1.0) * 1e6

    def to_global(self, t_local: float) -> float:
        return self.scale * float(t_local) + self.offset_seconds

    def to_local(self, t_global: float) -> float:
        return (float(t_global) - self.offset_seconds) / self.scale

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "scale": self.scale,
            "offset_seconds": self.offset_seconds,
        }

    def is_identity(self) -> bool:
        return self.scale == 1.0 and self.offset_seconds == 0.0


@dataclass(frozen=True)
class PiecewiseLinearTimeMap(TimeMap):
    """Piecewise-linear mapping defined by knots ``(t_local, t_global)``.

    Knots must be strictly increasing in ``t_local`` and non-decreasing in
    ``t_global`` (monotonic, hence invertible). Values outside the knot range
    are extrapolated linearly using the slope of the nearest edge segment.
    """

    knots: tuple[tuple[float, float], ...]
    kind: str = "piecewise_linear"

    def __post_init__(self) -> None:
        if len(self.knots) < 1:
            raise ValueError("at least one knot is required")
        t_local = [k[0] for k in self.knots]
        t_global = [k[1] for k in self.knots]
        if any(b <= a for a, b in zip(t_local, t_local[1:])):
            raise ValueError("knots must be strictly increasing in t_local")
        if any(b < a for a, b in zip(t_global, t_global[1:])):
            raise ValueError("knots must be non-decreasing in t_global (monotonic map)")

    def to_global(self, t_local: float) -> float:
        t = float(t_local)
        ts = [k[0] for k in self.knots]
        gs = [k[1] for k in self.knots]
        if len(ts) == 1:
            return float(gs[0])
        if t <= ts[0]:
            slope = (gs[1] - gs[0]) / (ts[1] - ts[0])
            return float(gs[0] + slope * (t - ts[0]))
        if t >= ts[-1]:
            slope = (gs[-1] - gs[-2]) / (ts[-1] - ts[-2])
            return float(gs[-1] + slope * (t - ts[-1]))
        return float(np.interp(t, np.asarray(ts), np.asarray(gs)))

    def to_local(self, t_global: float) -> float:
        # Invert by swapping the axes; monotonicity guarantees valid knots.
        inverse = PiecewiseLinearTimeMap(
            knots=tuple((g, t) for t, g in self.knots)
        )
        return inverse.to_global(t_global)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "knots": [list(k) for k in self.knots]}

    def is_identity(self) -> bool:
        return all(abs(a - b) < 1e-12 for a, b in self.knots)
