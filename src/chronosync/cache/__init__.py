"""Feature cache (ADR-006): SQLite index + file-based NumPy arrays."""

from __future__ import annotations

from .database import FeatureCacheDB
from .keys import SourceInfo, feature_identity, hash_array, hash_file, key_token, stat_source
from .store import ArrayStore

__all__ = [
    "ArrayStore",
    "FeatureCacheDB",
    "SourceInfo",
    "feature_identity",
    "hash_array",
    "hash_file",
    "key_token",
    "stat_source",
]
