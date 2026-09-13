# ADR-006: Feature cache design

**Status:** Accepted (2025, Phase 1, design first; implemented in Phase 3)
**Impact:** cache/, features/, coarse/, drift/

## Decision

Two-level cache:

1. **SQLite** stores index metadata only; **large arrays never go into BLOBs**;
2. feature arrays are stored as **`.npy` / `.npz` files**, whose paths SQLite
   records.

## Index keys

```text
path         source file path
size         file size (bytes)
mtime        modification time
hash         (optional) content hash, for cases where mtime is unreliable
algo_version algorithm version (e.g. "gcc-phat@1")
feat_version feature version (incremented when the feature definition changes)
```

Hit condition: path + (size, mtime) or hash + algo_version + feat_version all
match.

## Features planned for caching

energy envelope, spectral features, MFCC, fingerprint, transient map — one cache
record per feature, invalidated independently.

## Rationale

Feature extraction / coarse matching of recordings longer than 1 hour is the
dominant repeated cost; SQLite is a single file, transactional and usable across
processes; file-based arrays avoid the performance disaster and the memory
copies of large SQLite BLOBs.

## Consequences

* Every feature extractor must declare algo_version / feat_version, otherwise
  caching must not be enabled;
* the cache-invalidation policy is primarily (size, mtime), with hash as an
  optional strong check;
* the cache is transparent to correctness: any cache miss degrades to computing
  on the spot.
