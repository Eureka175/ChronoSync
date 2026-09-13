"""Multi-track alignment graph models (Layer 5 of the pipeline).

Tracks are the nodes of the graph; every pairwise offset measurement is a
directed edge. The global solver minimizes the weighted edge residuals

    min sum w_ij (t_i - t_j - d_ij)^2

with the reference track fixed at 0. Edge offsets follow ADR-003:

    d_ij = t_target(j) - t_source(i);  d_ij > 0 means events occur later in j.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AlignmentEdge:
    """One pairwise offset measurement between two tracks."""

    source: str
    target: str
    offset_samples: float  # d = t_target - t_source (ADR-003)
    confidence: float  # in [0, 1]
    evidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TrackAlignment:
    """Estimated placement of one track on the unified timeline."""

    track: str
    offset_samples: float  # relative to the graph reference; 0.0 for the reference
    offset_seconds: float
    confidence: float  # in [0, 1]
    residual_samples: float | None = None  # signed residual after the global solve (ADR-003)
    evidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class AlignmentGraph:
    """Tracks as nodes, pairwise measurements as edges.

    Provides connectivity inspection so that disconnected components can be
    handled separately (ADR: the global solver must never silently mix
    unrelated timelines).
    """

    edges: list[AlignmentEdge] = field(default_factory=list)
    reference: str | None = None

    def nodes(self) -> list[str]:
        names: set[str] = set()
        for edge in self.edges:
            names.add(edge.source)
            names.add(edge.target)
        return sorted(names)

    def neighbors(self, node: str) -> list[tuple[str, AlignmentEdge]]:
        return [(e.target, e) for e in self.edges if e.source == node] + [
            (e.source, e) for e in self.edges if e.target == node
        ]

    def is_connected(self) -> bool:
        return len(self.components()) <= 1

    def components(self) -> list[set[str]]:
        """Connected components of the *undirected* graph."""
        nodes = self.nodes()
        adj = {n: [m for m, _ in self.neighbors(n)] for n in nodes}
        seen: set[str] = set()
        components: list[set[str]] = []
        for node in nodes:
            if node in seen:
                continue
            component: set[str] = set()
            stack = [node]
            while stack:
                current = stack.pop()
                if current in component:
                    continue
                component.add(current)
                stack.extend(m for m in adj[current] if m not in component)
            seen |= component
            components.append(component)
        return components
