"""Feature-cache key derivation (ADR-006).

Cache identity = source identity (path + size + mtime, optional content hash)
+ algorithm version + feature version. Any change invalidates the entry.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_HASH_CHUNK = 1 << 20  # 1 MiB


@dataclass(frozen=True)
class SourceInfo:
    """Stable identity of one source file."""

    path: str
    size: int
    mtime_ns: int
    content_hash: str | None = None  # optional strong identity


def stat_source(path: str | Path) -> SourceInfo:
    path = Path(path)
    stat = path.stat()
    return SourceInfo(
        path=str(path),
        size=int(stat.st_size),
        mtime_ns=int(stat.st_mtime_ns),
    )


def source_identity(info: SourceInfo) -> tuple:
    """Tuple identity used as the DB key prefix (hash wins over mtime)."""
    return (
        info.path,
        int(info.size),
        (info.content_hash if info.content_hash is not None else int(info.mtime_ns)),
    )


def feature_identity(
    info: SourceInfo, algo_version: str, feat_version: int
) -> tuple:
    """Full identity of one cached feature entry."""
    return (*source_identity(info), str(algo_version), int(feat_version))


def hash_file(path: str | Path, chunk: int = _HASH_CHUNK) -> str:
    """SHA-256 of a file's content (hex)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def hash_array(arr) -> str:
    """SHA-256 of a NumPy array's raw bytes (hex)."""
    import numpy as np

    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()


def key_token(*parts) -> str:
    """Deterministic file-name token for an identity tuple."""
    joined = "|".join(str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]
