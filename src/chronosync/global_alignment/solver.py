"""Multi-track global alignment solver (Phase 6, ADR-011).

Tracks are graph nodes; pairwise offset measurements are weighted directed
edges (ADR-003: ``offset = t_target - t_source``). The solver minimizes

    min sum w_ij * (t_i - t_j - d_ij)^2

with the reference track fixed at 0. Disconnected components are solved
independently (each with its own anchor) and reported with warnings — the
solver must NEVER silently mix unrelated timelines. Every edge gets a
residual and every track a confidence derived from incident-edge agreement.
Optional IRLS reweighting (``irls_iterations > 0``) down-weights outlier
edges instead of letting them bend the solution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chronosync.models.alignment import AlignmentEdge, AlignmentGraph, TrackAlignment
from chronosync.models.audio import CANONICAL_SAMPLE_RATE

from .robust import irls_weights


@dataclass
class SolveConfig:
    """Global-solver configuration (all thresholds configurable)."""

    reference: str | None = None  # None -> auto-select the most-connected track
    irls_iterations: int = 0  # 0 = plain WLS; >0 adds IRLS reweighting
    outlier_sigma: float = 3.0  # edge flagged when |residual| > k * robust sigma


@dataclass
class SolvedAlignment:
    """Result of the global solve."""

    reference: str
    tracks: list[TrackAlignment]  # sorted by name; reference offset = 0
    edge_residuals: dict[tuple[str, str], float]  # (source, target) -> samples
    outlier_edges: list[tuple[str, str]]
    warnings: list[str] = field(default_factory=list)
    success: bool = True

    def track_map(self) -> dict[str, TrackAlignment]:
        return {t.track: t for t in self.tracks}


def solve(graph: AlignmentGraph, config: SolveConfig | None = None) -> SolvedAlignment:
    """Solve the graph; see the module docstring for semantics."""
    cfg = config if config is not None else SolveConfig()
    warnings: list[str] = []
    nodes = graph.nodes()
    if not nodes:
        return SolvedAlignment(
            reference=cfg.reference or "",
            tracks=[],
            edge_residuals={},
            outlier_edges=[],
            warnings=["empty graph"],
            success=False,
        )

    reference = cfg.reference if cfg.reference in nodes else None
    if reference is None:
        reference = _auto_reference(graph, nodes)
        warnings.append(
            f"auto-selected reference track '{reference}' (most connected)"
        )

    weights = np.array(
        [max(float(e.confidence), 1e-6) for e in graph.edges], dtype=np.float64
    )
    components = graph.components()

    def solve_once() -> dict[str, float]:
        placements: dict[str, float] = {reference: 0.0}
        for component in components:
            if component == {reference}:
                continue
            anchor = reference if reference in component else sorted(component)[0]
            if anchor != reference:
                warnings.append(
                    f"component {sorted(component)} is not connected to the "
                    f"reference '{reference}'; anchored independently at '{anchor}'"
                )
            component_list = sorted(component)
            indexed = [
                (i, e)
                for i, e in enumerate(graph.edges)
                if e.source in component and e.target in component
            ]
            free, a_mat, b_vec = _build_system(
                component_list, indexed, anchor, weights
            )
            if a_mat.size == 0:
                placements[anchor] = 0.0
                continue
            try:
                x = np.linalg.solve(a_mat, b_vec)
            except np.linalg.LinAlgError:
                x, *_ = np.linalg.lstsq(a_mat, b_vec, rcond=None)
                warnings.append(
                    f"singular system in component {component_list}; "
                    "least-squares fallback used"
                )
            for pos, i in enumerate(free):
                placements[component_list[i]] = float(x[pos])
            placements[anchor] = 0.0
        return placements

    placements = solve_once()

    for _ in range(max(0, cfg.irls_iterations)):
        residuals = np.array(
            [
                (placements[e.target] - placements[e.source]) - e.offset_samples
                for e in graph.edges
            ]
        )
        weights = irls_weights(residuals, weights)
        placements = solve_once()

    edge_residuals: dict[tuple[str, str], float] = {}
    for e in graph.edges:
        edge_residuals[(e.source, e.target)] = float(
            (placements[e.target] - placements[e.source]) - e.offset_samples
        )
    residuals_arr = np.array(list(edge_residuals.values()), dtype=np.float64)
    # Robust sigma with a FLOOR: when the fit is essentially perfect, the
    # MAD scale collapses and would flag every tiny numerical residual as an
    # outlier. Edges within 1 sample are never outliers.
    robust_sigma = max(_robust_sigma(residuals_arr), 0.5)
    outlier_threshold = max(cfg.outlier_sigma * robust_sigma, 1.0)
    outlier_mask = (
        np.abs(residuals_arr) > outlier_threshold
        if residuals_arr.size
        else np.zeros(0, dtype=bool)
    )
    outlier_edges = [
        key for key, flag in zip(edge_residuals.keys(), outlier_mask) if flag
    ]
    for source, target in outlier_edges:
        warnings.append(
            f"outlier edge {source}->{target}: residual "
            f"{edge_residuals[(source, target)]:+.0f} samples"
        )
    tracks = []
    for name in sorted(nodes):
        conf = _track_confidence(
            name, graph, edge_residuals, robust_sigma, reference
        )
        offset = placements.get(name, 0.0)
        tracks.append(
            TrackAlignment(
                track=name,
                offset_samples=float(offset),
                offset_seconds=float(offset) / CANONICAL_SAMPLE_RATE,
                confidence=conf,
                residual_samples=(
                    None
                    if name == reference
                    else _mean_abs_residual(name, graph, edge_residuals)
                ),
            )
        )
    return SolvedAlignment(
        reference=reference,
        tracks=tracks,
        edge_residuals=edge_residuals,
        outlier_edges=outlier_edges,
        warnings=warnings,
        success=True,
    )


def _build_system(
    component: list[str],
    indexed_edges: list[tuple[int, AlignmentEdge]],
    reference: str,
    weights: np.ndarray,
) -> tuple[list[int], np.ndarray, np.ndarray]:
    """Weighted normal equations for one component (reference pinned at 0).

    ``indexed_edges`` carries (index into weights, edge); ``weights`` aligns
    with ``graph.edges``. Returns (free node indices, A, b).
    """
    index = {name: i for i, name in enumerate(component)}
    n = len(component)
    ref_i = index[reference]
    free = [i for i in range(n) if i != ref_i]
    a = np.zeros((len(free), len(free)))
    b = np.zeros(len(free))
    for edge_i, edge in indexed_edges:
        u, v = index[edge.source], index[edge.target]
        w = float(weights[edge_i])
        d = float(edge.offset_samples)
        if v in free:
            pos = free.index(v)
            a[pos, pos] += w
            if u in free:
                a[pos, free.index(u)] -= w
            b[pos] += w * d
        if u in free:
            pos = free.index(u)
            a[pos, pos] += w
            if v in free:
                a[pos, free.index(v)] -= w
            b[pos] -= w * d
    return free, a, b


def _auto_reference(graph: AlignmentGraph, nodes: list[str]) -> str:
    """Most-connected track: highest total incident edge confidence."""
    score = {n: 0.0 for n in nodes}
    for e in graph.edges:
        score[e.source] += float(e.confidence)
        score[e.target] += float(e.confidence)
    return max(nodes, key=lambda n: (score[n], n))


def _robust_sigma(residuals: np.ndarray) -> float:
    if residuals.size == 0:
        return 0.0
    med = float(np.median(residuals))
    return 1.4826 * max(float(np.median(np.abs(residuals - med))), 1e-9)


def _mean_abs_residual(
    name: str, graph: AlignmentGraph, residuals: dict[tuple[str, str], float]
) -> float:
    values = [
        abs(residuals[(e.source, e.target)])
        for e in graph.edges
        if e.source == name or e.target == name
    ]
    return float(np.mean(values)) if values else 0.0


def _track_confidence(
    name: str,
    graph: AlignmentGraph,
    residuals: dict[tuple[str, str], float],
    robust_sigma: float,
    reference: str,
) -> float:
    if name == reference:
        return 1.0
    incident = [
        (e, residuals[(e.source, e.target)])
        for e in graph.edges
        if e.source == name or e.target == name
    ]
    if not incident:
        return 0.0
    scale = max(robust_sigma, 0.5)  # floored: near-perfect fits stay confident
    if scale <= 0.0:
        return float(np.mean([e.confidence for e, _ in incident]))
    total_w = 0.0
    total = 0.0
    for e, r in incident:
        agreement = max(0.0, 1.0 - abs(r) / (3.0 * scale))
        wgt = max(float(e.confidence), 1e-6)
        total += wgt * agreement
        total_w += wgt
    return float(np.clip(total / max(total_w, 1e-12), 0.0, 1.0))
