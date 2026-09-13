"""SQLite feature-cache index (ADR-006).

The SQLite row stores only metadata + the array file token; the array itself
lives in an :class:`~chronosync.cache.store.ArrayStore`. One row per
(source, kind, algo_version, feat_version). NOT thread-safe by design —
users serialize access (the alignment pipeline is single-process anyway).

Identity: ``(path, size, ident)`` where ``ident`` is the mtime in ns, or the
content SHA-256 when strong identity is requested (mtime survives copies and
network shares; hash survives anything but is expensive).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import numpy as np

from .keys import SourceInfo, feature_identity, key_token, source_identity
from .store import ArrayStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS features (
    source_path   TEXT NOT NULL,
    source_size   INTEGER NOT NULL,
    source_mtime  INTEGER NOT NULL,  -- real mtime (ns), diagnostics only
    source_ident  TEXT NOT NULL,     -- mtime_ns or content hash (identity)
    kind          TEXT NOT NULL,
    algo_version  TEXT NOT NULL,
    feat_version  INTEGER NOT NULL,
    array_token   TEXT NOT NULL,
    created_at    REAL NOT NULL,
    PRIMARY KEY (source_path, source_ident, kind, algo_version, feat_version)
);
"""


class FeatureCacheDB:
    """SQLite index over a directory of ``.npy`` feature arrays."""

    def __init__(self, db_path: str | Path, store: ArrayStore) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.store = store
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "FeatureCacheDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------- queries

    def get(
        self, source: SourceInfo, kind: str, algo_version: str, feat_version: int
    ) -> np.ndarray | None:
        """Return the cached feature array, or None on any kind of miss."""
        row = self._conn.execute(
            "SELECT array_token FROM features WHERE source_path=? AND source_size=?"
            " AND source_ident=? AND kind=? AND algo_version=? AND feat_version=?",
            (
                source.path,
                int(source.size),
                str(source_identity(source)[2]),
                kind,
                algo_version,
                int(feat_version),
            ),
        ).fetchone()
        if row is None:
            return None
        arr = self.store.load(row[0])
        if arr is None:  # array file vanished/corrupt: drop the stale row
            self.invalidate(source, kind, algo_version, feat_version)
        return arr

    def put(
        self,
        source: SourceInfo,
        kind: str,
        algo_version: str,
        feat_version: int,
        arr: np.ndarray,
    ) -> None:
        """Store a feature array (index row + array file, upsert)."""
        identity = feature_identity(source, algo_version, feat_version)
        token = key_token(kind, *identity)
        old = self._conn.execute(
            "SELECT array_token FROM features WHERE source_path=? AND source_ident=?"
            " AND kind=? AND algo_version=? AND feat_version=?",
            (source.path, str(source_identity(source)[2]), kind, algo_version, int(feat_version)),
        ).fetchone()
        if old is not None and old[0] != token:
            self.store.delete(old[0])  # no orphaned array files
        self.store.save(token, arr)
        self._conn.execute(
            "INSERT OR REPLACE INTO features VALUES (?,?,?,?,?,?,?,?,?)",
            (
                source.path,
                int(source.size),
                int(source.mtime_ns),
                str(source_identity(source)[2]),
                kind,
                algo_version,
                int(feat_version),
                token,
                time.time(),
            ),
        )
        self._conn.commit()

    def invalidate(
        self,
        source: SourceInfo | None = None,
        kind: str | None = None,
        algo_version: str | None = None,
        feat_version: int | None = None,
    ) -> int:
        """Delete matching rows (and their array files). Returns rows removed."""
        clauses, params = [], []
        if source is not None:
            clauses.append("source_path=? AND source_size=? AND source_ident=?")
            params.extend((source.path, int(source.size), str(source_identity(source)[2])))
        if kind is not None:
            clauses.append("kind=?")
            params.append(kind)
        if algo_version is not None:
            clauses.append("algo_version=?")
            params.append(algo_version)
        if feat_version is not None:
            clauses.append("feat_version=?")
            params.append(int(feat_version))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            "SELECT array_token FROM features" + where, params
        ).fetchall()
        for (token,) in rows:
            self.store.delete(token)
        self._conn.execute("DELETE FROM features" + where, params)
        self._conn.commit()
        return len(rows)

    def stats(self) -> dict:
        """Row count per feature kind (diagnostics)."""
        rows = self._conn.execute(
            "SELECT kind, COUNT(*) FROM features GROUP BY kind"
        ).fetchall()
        return {kind: int(n) for kind, n in rows}
