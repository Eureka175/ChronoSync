"""Unit tests for the core data models."""

from __future__ import annotations

import math

import numpy as np
import pytest

from chronosync.models import (
    AlignmentEdge,
    AlignmentGraph,
    ConstantOffsetTimeMap,
    DriftModel,
    IdentityTimeMap,
    LinearTimeMap,
    MatchResult,
    OffsetMeasurement,
    PiecewiseLinearTimeMap,
    TimeMap,
    TrackAlignment,
)


# ---------------------------------------------------------------- TimeMap


def test_identity_time_map():
    tm = IdentityTimeMap()
    assert tm.to_global(123.5) == 123.5
    assert tm.to_local(123.5) == 123.5
    assert tm.is_identity()


def test_constant_offset_time_map():
    tm = ConstantOffsetTimeMap(offset_seconds=2.5)
    assert tm.to_global(10.0) == 12.5
    assert tm.to_local(12.5) == 10.0
    assert not tm.is_identity()


def test_linear_time_map_and_inverse():
    tm = LinearTimeMap(scale=1.0002, offset_seconds=-0.1)
    assert tm.to_global(10.0) == pytest.approx(1.0002 * 10.0 - 0.1)
    assert tm.to_local(tm.to_global(1234.0)) == pytest.approx(1234.0)
    assert not tm.is_identity()


def test_linear_time_map_from_ppm():
    tm = LinearTimeMap.from_ppm(alpha_ppm=200.0, offset_seconds=0.0)
    assert tm.scale == pytest.approx(1.0002)
    assert tm.scale_ppm == pytest.approx(200.0)


def test_linear_time_map_rejects_non_positive_scale():
    with pytest.raises(ValueError):
        LinearTimeMap(scale=0.0)


def test_piecewise_time_map_interpolation_and_extrapolation():
    tm = PiecewiseLinearTimeMap(knots=((0.0, 0.0), (10.0, 10.2), (20.0, 20.1)))
    assert tm.to_global(5.0) == pytest.approx(5.1)  # slope of segment 1 = 1.02
    assert tm.to_global(15.0) == pytest.approx(15.15)  # slope of segment 2 = 0.99
    assert tm.to_global(-5.0) == pytest.approx(-5.1)  # extrapolation, slope 1.02
    assert tm.to_global(30.0) == pytest.approx(30.0)  # extrapolation, slope 0.99
    assert tm.to_local(10.2) == pytest.approx(10.0)


def test_piecewise_time_map_rejects_non_monotonic_knots():
    with pytest.raises(ValueError):
        PiecewiseLinearTimeMap(knots=((0.0, 5.0), (10.0, 0.0)))  # t_global decreasing
    with pytest.raises(ValueError):
        PiecewiseLinearTimeMap(knots=((0.0, 0.0), (0.0, 1.0)))  # t_local not increasing


@pytest.mark.parametrize(
    "tm",
    [
        IdentityTimeMap(),
        ConstantOffsetTimeMap(offset_seconds=-3.25),
        LinearTimeMap(scale=1.000123, offset_seconds=0.5),
        PiecewiseLinearTimeMap(knots=((0.0, 0.0), (10.0, 10.2), (20.0, 20.1))),
    ],
)
def test_time_map_serialization_round_trip(tm: TimeMap):
    restored = TimeMap.from_dict(tm.to_dict())
    assert restored.kind == tm.kind
    for t in (-5.0, 0.0, 5.0, 12.5, 25.0):
        assert restored.to_global(t) == pytest.approx(tm.to_global(t))


def test_time_map_sample_helpers():
    tm = ConstantOffsetTimeMap(offset_seconds=1.0)
    assert tm.to_global_samples(0) == pytest.approx(48_000.0)
    assert tm.to_local_samples(48_000.0) == pytest.approx(0.0)


def test_unknown_time_map_kind_raises():
    with pytest.raises(ValueError):
        TimeMap.from_dict({"kind": "warp9"})


# ---------------------------------------------------------------- Drift


def test_drift_model_fields():
    dm = DriftModel(
        alpha_ppm=120.0, beta_samples=-300.0, r2=0.999, model_type="linear", success=True
    )
    assert dm.alpha_ppm == 120.0
    assert dm.beta_samples == -300.0
    assert dm.r2 == 0.999
    assert dm.model_type == "linear"
    assert dm.success


def test_offset_measurement_defaults():
    om = OffsetMeasurement(center_samples=10_000.0, offset_samples=4.0, confidence=0.9)
    assert om.window_start_samples == 0
    assert om.window_end_samples == 0


# ---------------------------------------------------------------- Match


def test_match_result_defaults():
    mr = MatchResult(
        matched=True,
        offset_samples=100.0,
        offset_seconds=100.0 / 48_000.0,
        confidence=0.9,
        method="envelope",
    )
    assert mr.overlap_estimate is None
    assert mr.evidence == {}
    assert mr.warnings == []


# ---------------------------------------------------------------- Graph


def _graph() -> AlignmentGraph:
    return AlignmentGraph(
        edges=[
            AlignmentEdge("A", "B", offset_samples=100.0, confidence=0.9),
            AlignmentEdge("B", "C", offset_samples=-50.0, confidence=0.8),
        ],
        reference="A",
    )


def test_graph_nodes_and_connectivity():
    g = _graph()
    assert g.nodes() == ["A", "B", "C"]
    assert g.is_connected()
    assert g.components() == [{"A", "B", "C"}]


def test_graph_disconnected_components():
    g = _graph()
    g.edges.append(AlignmentEdge("X", "Y", offset_samples=1.0, confidence=0.5))
    assert not g.is_connected()
    components = g.components()
    assert {"A", "B", "C"} in components
    assert {"X", "Y"} in components


def test_graph_neighbors_are_undirected():
    g = _graph()
    neighbors = {n for n, _ in g.neighbors("B")}
    assert neighbors == {"A", "C"}


def test_track_alignment_defaults():
    ta = TrackAlignment(track="B", offset_samples=100.0, offset_seconds=100.0 / 48_000, confidence=0.9)
    assert ta.residual_samples is None
