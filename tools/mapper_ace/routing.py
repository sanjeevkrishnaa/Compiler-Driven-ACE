"""Explicit, deterministic physical routing policies for ACE traces."""

from __future__ import annotations

from collections.abc import Iterable

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.exceptions import ArchitectureError
from qmap.metrics.distance import DistanceOracle

ROUTING_POLICIES = (
    "xy",
    "yx",
    "dijkstra",
    "shortest_reliable",
    "max_reliability",
)


def _dimension_order(policy: str, dimensions: int) -> tuple[int, ...]:
    if dimensions != 2:
        raise ValueError(f"{policy} routing requires a two-dimensional mesh")
    return (0, 1) if policy == "xy" else (1, 0)


def _coordinate_path(
    architecture: MulticoreArchitecture,
    source: int,
    target: int,
    policy: str,
) -> tuple[int, ...]:
    if architecture.topology != "mesh":
        raise ValueError(f"{policy} routing is defined only for mesh topologies")
    current = list(architecture.coordinate_of(source))
    destination = architecture.coordinate_of(target)
    path = [source]
    for dimension in _dimension_order(policy, len(current)):
        step = 1 if destination[dimension] > current[dimension] else -1
        while current[dimension] != destination[dimension]:
            current[dimension] += step
            coordinate = tuple(current)
            if coordinate not in architecture.graph:
                raise ArchitectureError(
                    f"coordinate {coordinate} is not in {architecture.label}"
                ) from None
            previous = path[-1]
            next_core = architecture.index_of(coordinate)
            if not architecture.graph.has_edge(
                architecture.coordinate_of(previous), coordinate
            ):
                raise ArchitectureError(
                    f"{policy} produced non-adjacent hop {previous}->{next_core}"
                )
            path.append(next_core)
    return tuple(path)


def route_path(
    architecture: MulticoreArchitecture,
    oracle: DistanceOracle,
    source: int,
    target: int,
    policy: str,
) -> tuple[int, ...]:
    """Return a deterministic core path for a named research policy.

    ``dijkstra`` delegates to qmap's unambiguous shortest-path route model and
    is the sole approved torus policy in the Golden-study contract.
    ``shortest_reliable`` and ``max_reliability`` are the two reliability-aware
    policies implemented by qmap's distance oracle.  ``xy`` and ``yx`` are
    explicit dimension-order baselines for mesh experiments.  No policy
    silently falls back to another policy.
    """
    if policy not in ROUTING_POLICIES:
        raise ValueError(f"unknown routing policy {policy!r}; expected one of {ROUTING_POLICIES}")
    if source == target:
        return (source,)
    if policy in {"xy", "yx"}:
        path = _coordinate_path(architecture, source, target, policy)
    elif policy in {"dijkstra", "shortest_reliable"}:
        path = oracle.route_path(source, target, "shortest")
    else:
        path = oracle.route_path(source, target, "reliability")
    validate_path(architecture, path, source, target)
    return path


def validate_path(
    architecture: MulticoreArchitecture,
    path: Iterable[int],
    source: int,
    target: int,
) -> tuple[int, ...]:
    """Validate endpoints and physical adjacency, then return an immutable path."""
    path_tuple = tuple(int(core) for core in path)
    if not path_tuple or path_tuple[0] != source or path_tuple[-1] != target:
        raise ValueError(
            f"path endpoints {path_tuple!r} do not match ({source}, {target})"
        )
    for left, right in zip(path_tuple, path_tuple[1:], strict=False):
        if not (0 <= left < architecture.n_cores and 0 <= right < architecture.n_cores):
            raise ValueError(f"path contains an invalid core: {left}->{right}")
        if not architecture.graph.has_edge(
            architecture.coordinate_of(left), architecture.coordinate_of(right)
        ):
            raise ValueError(f"path contains a non-adjacent hop: {left}->{right}")
    return path_tuple
