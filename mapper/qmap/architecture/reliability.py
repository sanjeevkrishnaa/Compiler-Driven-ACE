
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from qmap.exceptions import ArchitectureError, ConfigurationError

__all__ = [
    "DEFAULT_BANDS",
    "RELIABILITY_ATTR",
    "ReliabilityBand",
    "assign_reliabilities",
    "default_bands",
    "parse_bands",
]

RELIABILITY_ATTR = "reliability"
"""Edge attribute under which ``p(e)`` is stored.

Deliberately *not* ``weight``: NetworkX shortest-path routines treat ``weight`` as
an additive cost, and a probability is neither additive nor a cost. Naming it
distinctly makes a mistaken ``nx.shortest_path_length(..., weight='weight')`` call
fail loudly rather than silently returning a meaningless sum.
"""

@dataclass(frozen=True, slots=True)
class ReliabilityBand:

    low: float
    high: float

    def __post_init__(self) -> None:
        if not (0.0 < self.low <= 1.0):
            raise ConfigurationError(
                f"reliability lower bound must lie in (0, 1], got {self.low}"
            )
        if not (0.0 < self.high <= 1.0):
            raise ConfigurationError(
                f"reliability upper bound must lie in (0, 1], got {self.high}"
            )
        if self.low > self.high:
            raise ConfigurationError(
                f"reliability band is inverted: low={self.low} > high={self.high}"
            )

    @property
    def label(self) -> str:
        return f"{self.low:.2f}-{self.high:.2f}"

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.low + self.high)

    def __str__(self) -> str:
        return self.label

DEFAULT_BANDS: tuple[tuple[float, float], ...] = (
    (0.1, 0.3),
    (0.3, 0.5),
    (0.5, 0.8),
    (0.8, 1.0),
)
"""The four reliability groups of Figure 6, read from its x-axis.

Section 6.3's prose says only that probabilities range over ``[0.1, 1.0]`` and are
"grouped into ranges corresponding to low, medium, or high reliability". The
boundaries appear solely in the figure's axis labels --- and they are **not**
equal-width: the bands are 0.2, 0.2, 0.3 and 0.2 wide.
"""

def default_bands(
    n_bands: int | None = None, floor: float = 0.1, ceiling: float = 1.0
) -> tuple[ReliabilityBand, ...]:
    if n_bands is None:
        return tuple(ReliabilityBand(low=low, high=high) for low, high in DEFAULT_BANDS)
    if n_bands <= 0:
        raise ConfigurationError(f"n_bands must be positive, got {n_bands}")
    if not floor < ceiling:
        raise ConfigurationError(f"empty reliability range: floor={floor} >= ceiling={ceiling}")
    edges = np.linspace(floor, ceiling, n_bands + 1)
    return tuple(
        ReliabilityBand(low=float(edges[i]), high=float(edges[i + 1])) for i in range(n_bands)
    )

def parse_bands(spec: str) -> tuple[ReliabilityBand, ...]:
    if not spec or not spec.strip():
        raise ConfigurationError("empty reliability band specification")
    bands: list[ReliabilityBand] = []
    for chunk in spec.split(","):
        part = chunk.strip()
        if not part:
            continue
        try:
            low_str, high_str = part.split("-")
            bands.append(ReliabilityBand(low=float(low_str), high=float(high_str)))
        except ValueError as exc:
            raise ConfigurationError(
                f"malformed reliability band {part!r}; expected 'low-high', e.g. '0.55-0.775'"
            ) from exc
    if not bands:
        raise ConfigurationError(f"no reliability bands parsed from {spec!r}")
    return tuple(bands)

def assign_reliabilities(
    graph: nx.Graph,
    rng: np.random.Generator,
    band: ReliabilityBand,
) -> nx.Graph:
    n_edges = graph.number_of_edges()
    if n_edges == 0:
        raise ArchitectureError(
            "interconnect has no links; reliability assignment is undefined "
            "(a multi-core architecture requires at least one inter-core link)"
        )

    draws = rng.uniform(band.low, band.high, size=n_edges)
    for (u, v), p in zip(sorted(graph.edges()), draws, strict=True):
        graph[u][v][RELIABILITY_ATTR] = float(p)
    return graph
