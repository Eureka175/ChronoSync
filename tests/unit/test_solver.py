"""Unit tests for the multi-track graph solver (Phase 6)."""

from __future__ import annotations

import numpy as np
import pytest

from chronosync.global_alignment import SolveConfig, solve
from chronosync.models.alignment import AlignmentEdge, AlignmentGraph


def _edge(source, target, offset, confidence=1.0):
    return AlignmentEdge(source, target, offset_samples=offset, confidence=confidence)


def test_exact_consistent_graph_recovers_true_offsets():
    # A (ref) = 0, B = +1000, C = -2000; all three pairwise edges measured.
    graph = AlignmentGraph(
        edges=[
            _edge("A", "B", 1_000.0),
            _edge("A", "C", -2_000.0),
            _edge("B", "C", -3_000.0),  # t_C - t_B = -2000 - 1000
        ],
        reference="A",
    )
    solved = solve(graph, SolveConfig(reference="A"))
    assert solved.success
    offsets = {t.track: t.offset_samples for t in solved.tracks}
    assert offsets == pytest.approx({"A": 0.0, "B": 1_000.0, "C": -2_000.0})
    for residual in solved.edge_residuals.values():
        assert abs(residual) < 1e-6
    assert solved.outlier_edges == []


def test_noisy_edges_still_solve_near_true_offsets():
    rng = np.random.default_rng(0)
    graph = AlignmentGraph(
        edges=[
            _edge("A", "B", 1_000.0 + rng.normal(0, 30)),
            _edge("A", "C", -2_000.0 + rng.normal(0, 30)),
            _edge("B", "C", -3_000.0 + rng.normal(0, 30)),
        ]
    )
    solved = solve(graph, SolveConfig(reference="A"))
    offsets = {t.track: t.offset_samples for t in solved.tracks}
    assert offsets["A"] == 0.0
    assert abs(offsets["B"] - 1_000.0) < 50.0
    assert abs(offsets["C"] - (-2_000.0)) < 50.0
    # residuals reflect the injected noise
    assert all(abs(r) < 100.0 for r in solved.edge_residuals.values())


def test_outlier_edge_is_flagged_and_limited_by_irls():
    # One wildly wrong measurement (A->C: +10000 instead of -2000) with low
    # confidence. Plain WLS is bent; IRLS down-weights the outlier.
    graph = AlignmentGraph(
        edges=[
            _edge("A", "B", 1_000.0),
            _edge("A", "C", 10_000.0, confidence=0.1),
            _edge("B", "C", -3_000.0),
        ]
    )
    plain = solve(graph, SolveConfig(reference="A", irls_iterations=0))
    robust = solve(graph, SolveConfig(reference="A", irls_iterations=3))
    assert ("A", "C") in plain.outlier_edges
    assert abs(robust.track_map()["C"].offset_samples - (-2_000.0)) < abs(
        plain.track_map()["C"].offset_samples - (-2_000.0)
    )
    # the true B<->C relation dominates after reweighting
    assert abs(robust.track_map()["C"].offset_samples - (-2_000.0)) < 200.0


def test_disconnected_components_are_solved_independently():
    graph = AlignmentGraph(
        edges=[_edge("A", "B", 500.0), _edge("C", "D", -300.0)]
    )
    solved = solve(graph, SolveConfig(reference="A"))
    offsets = {t.track: t.offset_samples for t in solved.tracks}
    assert offsets["A"] == 0.0
    assert offsets["B"] == pytest.approx(500.0)
    assert offsets["C"] == 0.0  # independently anchored
    assert offsets["D"] == pytest.approx(-300.0)
    assert any("not connected" in w for w in solved.warnings)


def test_tracks_without_measurements_are_not_in_the_graph():
    # The graph only contains measured nodes; unmeasured tracks are the
    # pipeline's responsibility (they are reported, never silently placed).
    graph = AlignmentGraph(edges=[_edge("A", "B", 100.0)])
    solved = solve(graph, SolveConfig(reference="A"))
    assert {t.track for t in solved.tracks} == {"A", "B"}


def test_auto_reference_picks_most_connected():
    # B appears in both edges; A and C only in one each -> B is the anchor.
    graph = AlignmentGraph(
        edges=[
            _edge("A", "B", 1_000.0, confidence=0.9),
            _edge("B", "C", -500.0, confidence=0.9),
        ]
    )
    solved = solve(graph)
    assert solved.reference == "B"
    offsets = {t.track: t.offset_samples for t in solved.tracks}
    assert offsets["B"] == 0.0
    assert offsets["A"] == pytest.approx(-1_000.0)
    assert offsets["C"] == pytest.approx(-500.0)


def test_track_confidence_rewards_agreement():
    graph = AlignmentGraph(
        edges=[
            _edge("A", "B", 1_000.0),
            _edge("A", "C", -2_000.0),
            _edge("B", "C", -3_000.0),
        ]
    )
    solved = solve(graph, SolveConfig(reference="A"))
    conf = {t.track: t.confidence for t in solved.tracks}
    assert conf["A"] == 1.0  # reference
    assert conf["B"] > 0.9
    assert conf["C"] > 0.9


def test_near_perfect_fit_does_not_flag_outliers_or_collapse_confidence():
    # Regression: with essentially zero residuals the MAD scale collapses
    # and used to flag every edge as an outlier (and zero the confidence).
    # Edges within 1 sample are never outliers; confidence has a floor.
    graph = AlignmentGraph(
        edges=[
            _edge("A", "B", 1_000.0),
            _edge("A", "C", -2_000.0),
            _edge("B", "C", -3_000.0),
        ]
    )
    solved = solve(graph, SolveConfig(reference="A"))
    assert solved.outlier_edges == []
    conf = {t.track: t.confidence for t in solved.tracks}
    assert conf["B"] > 0.9
    assert conf["C"] > 0.9


def test_empty_graph_fails_cleanly():
    solved = solve(AlignmentGraph())
    assert not solved.success
    assert solved.tracks == []
