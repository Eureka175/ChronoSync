"""Unit tests for the feature cache (ADR-006)."""

from __future__ import annotations

import numpy as np

from chronosync.cache import (
    ArrayStore,
    FeatureCacheDB,
    SourceInfo,
    hash_array,
    key_token,
    stat_source,
)


def _source(path="/data/rec.wav", size=12345, mtime=1000, hash=None):
    return SourceInfo(path=path, size=size, mtime_ns=mtime, content_hash=hash)


def _make(tmp_path):
    store = ArrayStore(tmp_path / "arrays")
    db = FeatureCacheDB(tmp_path / "cache.sqlite3", store)
    return db, store


# -------------------------------------------------------------------- keys


def test_key_token_is_deterministic_and_distinct():
    a = key_token("x", 1, "v1", 2)
    b = key_token("x", 1, "v1", 2)
    c = key_token("x", 1, "v2", 2)
    assert a == b and a != c
    assert len(a) == 24


def test_hash_array_detects_differences():
    x = np.arange(10, dtype=np.float32)
    assert hash_array(x) == hash_array(x.copy())
    assert hash_array(x) != hash_array(x + 1)


# ------------------------------------------------------------------- store


def test_array_store_round_trip(tmp_path):
    store = ArrayStore(tmp_path)
    arr = np.arange(100, dtype=np.float32)
    path = store.save("tok1", arr)
    assert path.exists()
    loaded = store.load("tok1")
    assert np.array_equal(loaded, arr)
    assert store.load("missing") is None
    store.delete("tok1")
    assert store.load("tok1") is None


def test_array_store_corrupt_file_is_a_miss(tmp_path):
    store = ArrayStore(tmp_path)
    store.save("tok", np.ones(3))
    store.path_for("tok").write_bytes(b"not a numpy file")
    assert store.load("tok") is None


# ---------------------------------------------------------------- database


def test_db_put_get_round_trip(tmp_path):
    db, _ = _make(tmp_path)
    with db:
        arr = np.arange(50, dtype=np.float32)
        src = _source()
        db.put(src, "envelope", "env@1", 1, arr)
        loaded = db.get(src, "envelope", "env@1", 1)
        assert np.array_equal(loaded, arr)
        assert db.get(src, "envelope", "env@1", 2) is None  # feat version miss
        assert db.get(src, "fingerprint", "env@1", 1) is None  # kind miss


def test_db_source_change_is_a_miss(tmp_path):
    db, _ = _make(tmp_path)
    with db:
        src = _source(mtime=1000)
        db.put(src, "env", "v1", 1, np.ones(4))
        assert db.get(_source(mtime=1001), "env", "v1", 1) is None  # mtime changed
        assert db.get(_source(size=999), "env", "v1", 1) is None  # size changed
        assert db.get(_source(hash="abc"), "env", "v1", 1) is None  # identity mode


def test_db_algo_version_change_is_a_miss(tmp_path):
    db, _ = _make(tmp_path)
    with db:
        src = _source()
        db.put(src, "env", "env@1", 1, np.ones(4))
        assert db.get(src, "env", "env@2", 1) is None


def test_db_hash_identity_separates_same_mtime_sources(tmp_path):
    db, _ = _make(tmp_path)
    with db:
        a = _source(hash="hash-a")
        b = _source(hash="hash-b")
        db.put(a, "env", "v1", 1, np.ones(3))
        db.put(b, "env", "v1", 1, np.full(3, 2.0))
        assert np.array_equal(db.get(a, "env", "v1", 1), np.ones(3))
        assert np.array_equal(db.get(b, "env", "v1", 1), np.full(3, 2.0))


def test_db_invalidate_removes_rows_and_files(tmp_path):
    db, store = _make(tmp_path)
    with db:
        src = _source()
        db.put(src, "env", "v1", 1, np.ones(4))
        db.put(src, "fp", "v1", 1, np.ones(6))
        assert len(list(store.directory.glob("*.npy"))) == 2
        removed = db.invalidate(src)
        assert removed == 2
        assert db.get(src, "env", "v1", 1) is None
        assert len(list(store.directory.glob("*.npy"))) == 0


def test_db_upsert_same_identity_cleans_orphan_files(tmp_path):
    db, store = _make(tmp_path)
    with db:
        src = _source()
        db.put(src, "env", "v1", 1, np.ones(4))
        db.put(src, "env", "v1", 1, np.ones(5))  # same identity: replace
        npy = list(store.directory.glob("*.npy"))
        assert len(npy) == 1  # old array file removed, no orphans
        loaded = db.get(src, "env", "v1", 1)
        assert np.array_equal(loaded, np.ones(5))


def test_db_different_identities_are_separate_entries(tmp_path):
    db, store = _make(tmp_path)
    with db:
        db.put(_source(mtime=1000), "env", "v1", 1, np.ones(4))
        db.put(_source(mtime=2000), "env", "v1", 1, np.ones(5))
        # different mtime identity -> two valid cached states, two files
        assert len(list(store.directory.glob("*.npy"))) == 2
        assert np.array_equal(
            db.get(_source(mtime=1000), "env", "v1", 1), np.ones(4)
        )
        assert np.array_equal(
            db.get(_source(mtime=2000), "env", "v1", 1), np.ones(5)
        )


def test_db_stats(tmp_path):
    db, _ = _make(tmp_path)
    with db:
        db.put(_source(), "env", "v1", 1, np.ones(4))
        db.put(_source(), "fp", "v1", 1, np.ones(4))
        assert db.stats() == {"env": 1, "fp": 1}


def test_stat_source_reads_real_file(tmp_path):
    p = tmp_path / "x.wav"
    p.write_bytes(b"\x00" * 100)
    info = stat_source(p)
    assert info.size == 100
    assert info.mtime_ns > 0
