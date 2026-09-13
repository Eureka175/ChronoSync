"""High-level multi-track pipeline (Phases 5-7 orchestration).

``align_pair`` runs coarse -> drift for one file pair and returns an
``AlignmentEdge``; ``batch_align`` runs all pairs, solves the measurement
graph globally and builds per-track TimeMaps (direct-to-reference drift maps
when measured, constant solved offsets otherwise — composition across
unmeasured pairs is a documented future work).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from chronosync.coarse import CoarseConfig, coarse_match_paths
from chronosync.drift import DriftConfig, DriftEstimate, estimate_drift
from chronosync.global_alignment import SolveConfig, SolvedAlignment, solve
from chronosync.io import probe, read_canonical
from chronosync.models.alignment import AlignmentEdge, AlignmentGraph
from chronosync.models.audio import CANONICAL_SAMPLE_RATE
from chronosync.models.match import MatchResult
from chronosync.models.timemap import (
    ConstantOffsetTimeMap,
    IdentityTimeMap,
    TimeMap,
)


@dataclass
class PipelineConfig:
    """Batch pipeline configuration."""

    coarse: CoarseConfig | None = None
    drift: DriftConfig | None = None
    solve: SolveConfig | None = None
    cache_dir: str | Path | None = None
    max_seconds: float | None = None  # decode guard for very long files


@dataclass
class PairResult:
    """One pair's coarse + drift results."""

    reference: str
    target: str
    coarse: MatchResult
    drift: DriftEstimate | None
    edge: AlignmentEdge | None  # None when the pair could not be measured
    warnings: list[str] = field(default_factory=list)


@dataclass
class BatchResult:
    """Full multi-track batch result."""

    pair_results: list[PairResult]
    graph: AlignmentGraph
    solved: SolvedAlignment
    time_maps: dict[str, TimeMap]  # track name -> local-to-global map
    warnings: list[str] = field(default_factory=list)


def align_pair(
    reference_path: str | Path,
    target_path: str | Path,
    config: PipelineConfig | None = None,
) -> PairResult:
    """Coarse + drift for one pair -> AlignmentEdge (ADR-003 direction)."""
    cfg = config if config is not None else PipelineConfig()
    ref_track = probe(reference_path)
    tgt_track = probe(target_path)
    warnings: list[str] = []

    coarse = coarse_match_paths(
        reference_path, target_path,
        config=cfg.coarse, cache_dir=cfg.cache_dir,
    )
    if not coarse.matched:
        return PairResult(
            reference=ref_track.name, target=tgt_track.name,
            coarse=coarse, drift=None, edge=None,
            warnings=[*coarse.warnings],
        )

    ref = read_canonical(reference_path, max_seconds=cfg.max_seconds)
    tgt = read_canonical(target_path, max_seconds=cfg.max_seconds)
    drift = estimate_drift(
        ref.mono_mix, tgt.mono_mix, CANONICAL_SAMPLE_RATE,
        coarse_offset_samples=coarse.offset_samples, config=cfg.drift,
    )
    warnings.extend(drift.warnings)
    if drift.success:
        confidence = float(
            min(1.0, 0.7 * coarse.confidence + 0.3 * max(drift.model.r2, 0.0))
        )
        edge = AlignmentEdge(
            source=ref_track.name,
            target=tgt_track.name,
            offset_samples=drift.model.beta_samples,
            confidence=confidence,
            evidence={
                "coarse_confidence": coarse.confidence,
                "drift_r2": drift.model.r2,
                "drift_alpha_ppm": drift.model.alpha_ppm,
            },
            warnings=list(drift.warnings),
        )
    else:
        # Coarse matched but drift failed (e.g. short/noisy overlap): keep a
        # low-confidence edge so the graph is not needlessly disconnected.
        warnings.append(
            f"drift failed for {ref_track.name}/{tgt_track.name}; "
            "low-confidence coarse-only edge"
        )
        edge = AlignmentEdge(
            source=ref_track.name,
            target=tgt_track.name,
            offset_samples=coarse.offset_samples or 0.0,
            confidence=0.3 * coarse.confidence,
            evidence={"coarse_confidence": coarse.confidence},
            warnings=list(drift.warnings),
        )
    return PairResult(
        reference=ref_track.name, target=tgt_track.name,
        coarse=coarse, drift=drift, edge=edge, warnings=warnings,
    )


def batch_align(
    files: list[str | Path],
    config: PipelineConfig | None = None,
) -> BatchResult:
    """All-pairs measurement -> global solve -> per-track TimeMaps."""
    cfg = config if config is not None else PipelineConfig()
    warnings: list[str] = []
    paths = [Path(f) for f in files]
    if len(paths) < 2:
        raise ValueError("batch_align needs at least two files")

    tracks = [probe(p) for p in paths]
    names = [t.name for t in tracks]
    if len(set(names)) != len(names):
        raise ValueError(
            "duplicate file basenames; rename files before batch alignment"
        )

    pair_results: list[PairResult] = []
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            pr = align_pair(paths[i], paths[j], cfg)
            pair_results.append(pr)
            if pr.edge is None:
                warnings.append(
                    f"no match between {names[i]} and {names[j]}: "
                    f"{pr.coarse.method} confidence {pr.coarse.confidence:.2f}"
                )
    edges = [pr.edge for pr in pair_results if pr.edge is not None]
    graph = AlignmentGraph(edges=edges, reference=None)
    solved = solve(graph, cfg.solve)
    warnings.extend(solved.warnings)

    measured = {e.source for e in edges} | {e.target for e in edges}
    for name in names:
        if name not in measured:
            warnings.append(
                f"track '{name}' matched nothing; excluded from the session"
            )

    # Per-track TimeMap onto the reference timeline. Tracks measured
    # DIRECTLY against the (possibly auto-selected) reference keep their
    # drift TimeMap; every other track gets the constant solved offset
    # (composition across unmeasured pairs is documented future work).
    ref = solved.reference
    time_maps: dict[str, TimeMap] = {ref: IdentityTimeMap()}
    for pr in pair_results:
        if pr.drift is None or not pr.drift.success or pr.drift.time_map is None:
            continue
        if pr.reference == ref and pr.target != ref:
            time_maps[pr.target] = pr.drift.time_map
        elif pr.target == ref and pr.reference != ref:
            time_maps[pr.reference] = pr.drift.time_map
    for track in solved.tracks:
        if track.track not in time_maps:
            time_maps[track.track] = ConstantOffsetTimeMap(
                offset_seconds=track.offset_seconds
            )
            warnings.append(
                f"track '{track.track}' has no direct drift measurement with "
                "the reference; placed by constant solved offset (drift "
                "composition is future work)"
            )
    return BatchResult(
        pair_results=pair_results, graph=graph, solved=solved,
        time_maps=time_maps, warnings=warnings,
    )
