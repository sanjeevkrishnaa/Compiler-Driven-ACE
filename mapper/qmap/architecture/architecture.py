
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

import networkx as nx

from qmap.architecture.core import Core
from qmap.architecture.reliability import (
    RELIABILITY_ATTR,
    ReliabilityBand,
    assign_reliabilities,
)
from qmap.architecture.topology import build_topology, canonical_topology, parse_grid
from qmap.exceptions import ArchitectureError
from qmap.rng import SeedSequence

__all__ = ["MulticoreArchitecture"]

@dataclass(frozen=True)
class MulticoreArchitecture:

    topology: str
    dimensions: tuple[int, ...]
    graph: nx.Graph
    cores: tuple[Core, ...]
    seed_path: str = ""

    _index_of: dict[tuple[int, ...], int] = field(
        default_factory=dict, repr=False, compare=False
    )

    @classmethod
    def build(
        cls,
        grid: str | tuple[int, ...],
        *,
        qubits_per_core: int,
        reserved_ancilla: int,
        seed: SeedSequence,
        reliability_band: ReliabilityBand,
        topology: str = "mesh",
    ) -> MulticoreArchitecture:
        dims = parse_grid(grid) if isinstance(grid, str) else tuple(grid)
        topology = canonical_topology(topology)
        graph = build_topology(topology, dims)

        reliability_seed = seed.stream("reliability")
        assign_reliabilities(graph, reliability_seed.generator(), reliability_band)

        cores = tuple(
            Core(
                index=i,
                coordinate=node,
                qubits_per_core=qubits_per_core,
                reserved_ancilla=reserved_ancilla,
            )
            for i, node in enumerate(sorted(graph.nodes()))
        )
        return cls(
            topology=topology,
            dimensions=dims,
            graph=graph,
            cores=cores,
            seed_path=reliability_seed.path,
        )

    def __post_init__(self) -> None:
        if not self.cores:
            raise ArchitectureError("architecture must contain at least one core")

        capacities = {c.capacity for c in self.cores}
        if len(capacities) != 1:
            raise ArchitectureError(
                f"heterogeneous core capacities are not supported; got {sorted(capacities)}"
            )

        missing = [
            (u, v)
            for u, v, data in self.graph.edges(data=True)
            if RELIABILITY_ATTR not in data
        ]
        if missing:
            raise ArchitectureError(
                f"{len(missing)} link(s) lack a {RELIABILITY_ATTR!r} attribute "
                f"(first: {missing[0]}); build the architecture via "
                f"MulticoreArchitecture.build()"
            )

        self._index_of.update({core.coordinate: core.index for core in self.cores})

    @property
    def n_cores(self) -> int:
        return len(self.cores)

    @property
    def capacity(self) -> int:
        return self.cores[0].capacity

    @property
    def workload_capacity(self) -> int:
        return self.cores[0].workload_capacity

    @property
    def qubits_per_core(self) -> int:
        return self.cores[0].qubits_per_core

    @property
    def reserved_ancilla(self) -> int:
        return self.cores[0].reserved_ancilla

    @property
    def total_capacity(self) -> int:
        return self.n_cores * self.capacity

    @property
    def workload_width(self) -> int:
        return self.n_cores * self.workload_capacity

    @property
    def occupancy_fraction(self) -> float:
        return self.workload_width / self.total_capacity

    @property
    def label(self) -> str:
        return f"{self.topology}_{'x'.join(map(str, self.dimensions))}"

    def index_of(self, coordinate: tuple[int, ...]) -> int:
        try:
            return self._index_of[coordinate]
        except KeyError:
            raise ArchitectureError(
                f"no core at coordinate {coordinate} in {self.label}"
            ) from None

    def coordinate_of(self, index: int) -> tuple[int, ...]:
        if not 0 <= index < self.n_cores:
            raise ArchitectureError(
                f"core index {index} out of range for {self.label} "
                f"({self.n_cores} cores)"
            )
        return self.cores[index].coordinate

    @cached_property
    def link_reliabilities(self) -> dict[tuple[int, int], float]:
        out: dict[tuple[int, int], float] = {}
        for u, v, data in self.graph.edges(data=True):
            i, j = self.index_of(u), self.index_of(v)
            out[(min(i, j), max(i, j))] = float(data[RELIABILITY_ATTR])
        return out

    def reliability_summary(self) -> dict[str, float]:
        values = list(self.link_reliabilities.values())
        return {
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
            "count": float(len(values)),
        }

    def describe(self) -> dict[str, object]:
        return {
            "topology": self.topology,
            "dimensions": list(self.dimensions),
            "n_cores": self.n_cores,
            "qubits_per_core": self.qubits_per_core,
            "reserved_ancilla": self.reserved_ancilla,
            "capacity": self.capacity,
            "workload_capacity": self.workload_capacity,
            "total_capacity": self.total_capacity,
            "workload_width": self.workload_width,
            "occupancy_fraction": self.occupancy_fraction,
            "n_links": self.graph.number_of_edges(),
            "seed_path": self.seed_path,
            "reliability": self.reliability_summary(),
        }

    def __str__(self) -> str:
        return (
            f"{self.label} ({self.n_cores} cores x {self.capacity} capacity, "
            f"workload {self.workload_width} qubits @ {self.occupancy_fraction:.0%})"
        )
