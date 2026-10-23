
from __future__ import annotations

import math
import re
from collections.abc import Callable

import networkx as nx

from qmap.exceptions import ArchitectureError, ConfigurationError

__all__ = [
    "TOPOLOGIES",
    "TopologyBuilder",
    "build_topology",
    "canonical_topology",
    "list_topologies",
    "parse_grid",
    "register_topology",
]

TopologyBuilder = Callable[[tuple[int, ...]], nx.Graph]
"""Builds an interconnect graph from grid dimensions. Nodes must be coordinate tuples."""

TOPOLOGIES: dict[str, TopologyBuilder] = {}
"""Registry mapping topology name to builder. Extend via :func:`register_topology`."""

_TOPOLOGY_ALIASES = {
    "all-to-all": "ata",
    "alltoall": "ata",
}
"""Accepted spellings for built-in topology names that have a canonical form."""

_GRID_PATTERN = re.compile(r"^\s*(\d+)\s*(?:[xX*]\s*(\d+)\s*)*$")

def register_topology(name: str) -> Callable[[TopologyBuilder], TopologyBuilder]:

    def decorator(builder: TopologyBuilder) -> TopologyBuilder:
        key = name.lower()
        if key in TOPOLOGIES:
            raise ConfigurationError(f"topology {name!r} is already registered")
        TOPOLOGIES[key] = builder
        return builder

    return decorator

def _core_count(dims: tuple[int, ...]) -> int:
    return math.prod(dims)

def _relabel(graph: nx.Graph) -> nx.Graph:
    return nx.relabel_nodes(graph, {node: (node,) for node in graph.nodes()})


def canonical_topology(name: str) -> str:
    """Return the registry key for a topology name or one of its aliases."""

    key = name.lower().strip().replace("_", "-").replace(" ", "-")
    return _TOPOLOGY_ALIASES.get(key, key)

@register_topology("mesh")
def _build_mesh(dims: tuple[int, ...]) -> nx.Graph:
    if len(dims) != 2:
        raise ArchitectureError(
            f"mesh topology requires 2 dimensions (e.g. '4x4'), got {len(dims)}: {dims}"
        )
    return nx.grid_2d_graph(dims[0], dims[1])

@register_topology("torus")
def _build_torus(dims: tuple[int, ...]) -> nx.Graph:
    if len(dims) != 2:
        raise ArchitectureError(
            f"torus topology requires 2 dimensions (e.g. '4x4'), got {len(dims)}: {dims}"
        )
    if min(dims) < 2:
        raise ArchitectureError(
            f"torus topology requires both extents >= 2, got {dims}: an extent of 1 "
            f"wraps a core onto itself"
        )
    graph = nx.grid_2d_graph(dims[0], dims[1], periodic=True)
    graph.remove_edges_from(nx.selfloop_edges(graph))
    return graph

@register_topology("line")
def _build_line(dims: tuple[int, ...]) -> nx.Graph:
    return _relabel(nx.path_graph(_core_count(dims)))

@register_topology("tree")
def _build_tree(dims: tuple[int, ...]) -> nx.Graph:
    n = _core_count(dims)
    if n < 2:
        raise ArchitectureError(
            f"tree topology requires at least 2 cores, got {n} from dims {dims}"
        )
    graph = nx.Graph()
    graph.add_nodes_from((i,) for i in range(n))
    graph.add_edges_from(((i,), ((i - 1) // 2,)) for i in range(1, n))
    return graph


@register_topology("ata")
def _build_all_to_all(dims: tuple[int, ...]) -> nx.Graph:
    """Build a complete core graph (``K_n``) for an all-to-all interconnect."""

    return _relabel(nx.complete_graph(_core_count(dims)))

def parse_grid(spec: str) -> tuple[int, ...]:
    if not spec or not _GRID_PATTERN.match(spec):
        raise ConfigurationError(
            f"malformed grid specification {spec!r}; expected e.g. '4x4', '8x4', or '64'"
        )
    try:
        dims = tuple(int(part) for part in re.split(r"[xX*]", spec.strip()))
    except ValueError as exc:
        raise ConfigurationError(f"malformed grid specification {spec!r}") from exc
    if any(d <= 0 for d in dims):
        raise ConfigurationError(f"grid dimensions must be positive, got {dims}")
    return dims

def list_topologies() -> list[str]:
    return sorted(TOPOLOGIES)


def build_topology(name: str, dims: tuple[int, ...]) -> nx.Graph:
    key = canonical_topology(name)
    if key not in TOPOLOGIES:
        available = ", ".join(sorted(TOPOLOGIES))
        raise ConfigurationError(f"unknown topology {name!r}; available: {available}")

    graph = TOPOLOGIES[key](dims)

    if graph.number_of_nodes() == 0:
        raise ArchitectureError(f"topology {name!r} with dims {dims} produced an empty graph")
    if not all(isinstance(node, tuple) for node in graph.nodes):
        raise ArchitectureError(
            f"topology {name!r} must key nodes by coordinate tuples; "
            f"got {type(next(iter(graph.nodes))).__name__}"
        )
    if graph.number_of_nodes() > 1 and not nx.is_connected(graph):
        raise ArchitectureError(
            f"topology {name!r} with dims {dims} is disconnected; "
            f"inter-core distance would be undefined for some core pairs"
        )
    return graph
