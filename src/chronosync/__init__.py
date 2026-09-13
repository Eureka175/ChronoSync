"""ChronoSync: multi-track audio timebase estimation, alignment and clock-drift correction.

The core object of the system is the :class:`~chronosync.models.timemap.TimeMap`
that maps each track's local device timeline onto a unified global timeline,
rather than a bare sample offset.
"""

from __future__ import annotations

#: PEP 440 canonical form of the release "v0.1.0-beta".
__version__ = "0.1.0b0"
__release__ = "v0.1.0-beta"
