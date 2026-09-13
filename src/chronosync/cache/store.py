"""File-based NumPy array store (ADR-006).

Large feature arrays live in ``.npy`` files — never as SQLite BLOBs. Writes
go through a temp file + rename so a crashed process cannot leave a
half-written array that the cache would trust.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


class ArrayStore:
    """Directory-backed store mapping key tokens to ``.npy`` files."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, token: str) -> Path:
        safe = "".join(c for c in token if c.isalnum())
        return self.directory / f"{safe}.npy"

    def exists(self, token: str) -> bool:
        return self.path_for(token).exists()

    def save(self, token: str, arr: np.ndarray) -> Path:
        """Save an array atomically; returns the final path."""
        import os

        target = self.path_for(token)
        safe = "".join(c for c in token if c.isalnum())
        tmp = self.directory / f"{safe}.tmp.npy"  # np.save appends .npy
        np.save(tmp, np.asarray(arr), allow_pickle=False)
        os.replace(tmp, target)
        return target

    def load(self, token: str) -> np.ndarray | None:
        """Load an array or ``None`` when missing/corrupt."""
        path = self.path_for(token)
        if not path.exists():
            return None
        try:
            return np.load(path, allow_pickle=False)
        except (ValueError, OSError):  # corrupt file: treat as a miss
            return None

    def delete(self, token: str) -> None:
        path = self.path_for(token)
        if path.exists():
            path.unlink()
