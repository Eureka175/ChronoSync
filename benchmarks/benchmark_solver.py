"""Multi-track graph-solver benchmark.

Usage::

    python benchmarks/benchmark_solver.py [--json]

Cases: complete measurement graphs of 10 / 20 / 50 tracks (all pairwise
edges, noisy offsets), plain WLS and IRLS. Reports wall/CPU/peak RSS and the
RMS offset recovery error vs the ground truth.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.common import BenchmarkResult, print_table, timed, to_dict  # noqa: E402
from chronosync.global_alignment import SolveConfig, solve  # noqa: E402
from chronosync.models.alignment import AlignmentEdge, AlignmentGraph  # noqa: E402


def _graph(n_tracks: int, seed: int = 0) -> tuple[AlignmentGraph, dict[str, float]]:
    rng = np.random.default_rng(seed)
    truth = {f"T{i:02d}": float(rng.uniform(-1e6, 1e6)) for i in range(n_tracks)}
    edges = []
    for i in range(n_tracks):
        for j in range(i + 1, n_tracks):
            d = truth[f"T{j:02d}"] - truth[f"T{i:02d}"] + rng.normal(0, 20.0)
            edges.append(
                AlignmentEdge(
                    source=f"T{i:02d}", target=f"T{j:02d}",
                    offset_samples=d, confidence=float(rng.uniform(0.7, 1.0)),
                )
            )
    return AlignmentGraph(edges=edges), truth


def _recovery_error(solved, truth: dict[str, float], reference: str) -> float:
    ref = truth[reference]
    errors = [
        abs((t.offset_samples + ref) - truth[t.track])
        for t in solved.tracks
    ]
    return float(np.sqrt(np.mean(np.square(errors))))


def run() -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    for n in (10, 20, 50):
        graph, truth = _graph(n)
        ref = "T00"
        solved, bm = timed(
            lambda: solve(graph, SolveConfig(reference=ref)),
            name=f"graph solve {n} tracks (WLS)",
        )
        bm.extra = {
            "mode": "solve",
            "edges": len(graph.edges),
            "rms_error_samples": _recovery_error(solved, truth, ref),
        }
        results.append(bm)

        solved_i, bm = timed(
            lambda: solve(graph, SolveConfig(reference=ref, irls_iterations=3)),
            name=f"graph solve {n} tracks (IRLS)",
        )
        bm.extra = {
            "mode": "solve",
            "edges": len(graph.edges),
            "rms_error_samples": _recovery_error(solved_i, truth, ref),
        }
        results.append(bm)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    results = run()
    if args.json:
        print(json.dumps([to_dict(r) for r in results], indent=2))
    else:
        print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
