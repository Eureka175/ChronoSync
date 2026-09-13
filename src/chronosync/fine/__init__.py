"""Fine local alignment (Layer 3).

* :mod:`chronosync.fine.gcc_phat` — GCC-PHAT delay estimation
* :mod:`chronosync.fine.peak` — peak discovery/selection strategy
* :mod:`chronosync.fine.subsample` — parabolic sub-sample refinement
"""

from __future__ import annotations

from .gcc_phat import GCCResult, gcc_phat
from .peak import CorrelationPeak, PeakSelectionConfig

__all__ = ["GCCResult", "gcc_phat", "CorrelationPeak", "PeakSelectionConfig"]
