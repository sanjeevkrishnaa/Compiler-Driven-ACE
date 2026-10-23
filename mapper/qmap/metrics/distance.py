
from __future__ import annotations

import heapq
import math
from functools import cached_property

import numpy as np

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.exceptions import ArchitectureError

__all__ = ["MAX_TRANSFER_COST", "DistanceOracle"]


# ``float64`` cannot represent an expected cost beyond this value.  Keep a
# margin below the largest finite value so adding the two operand costs in
# Eq. (8) remains finite as well.
MAX_TRANSFER_COST = np.finfo(np.float64).max / 16.0

class DistanceOracle:

    __slots__ = ("__dict__", "architecture")

    def __init__(self, architecture: MulticoreArchitecture) -> None:
        self.architecture = architecture
        self._validate_reliabilities()

    def _validate_reliabilities(self) -> None:
        for (i, j), p in self.architecture.link_reliabilities.items():
            if not (0.0 < p <= 1.0):
                raise ArchitectureError(
                    f"link ({i}, {j}) has reliability {p}, which is outside (0, 1]; "
                    f"expected a success probability"
                )

    @cached_property
    def _matrices(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Shortest-hop paths, with reliability as the tie-breaker."""
        n = self.architecture.n_cores
        adjacency = self._adjacency()

        hops = np.full((n, n), np.inf, dtype=np.float64)
        neglog = np.full((n, n), np.inf, dtype=np.float64)
        epr_latency = np.full((n, n), np.inf, dtype=np.float64)

        for source in range(n):
            h_row, n_row, e_row = self._dijkstra(source, adjacency, n)
            hops[source] = h_row
            neglog[source] = n_row
            epr_latency[source] = e_row

        if not np.isfinite(hops).all():
            unreachable = int((~np.isfinite(hops)).sum())
            raise ArchitectureError(
                f"{unreachable} core pair(s) are unreachable in "
                f"{self.architecture.label}; inter-core distance is undefined"
            )
        return hops, neglog, epr_latency

    @cached_property
    def _reliable_matrices(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Maximum-product-reliability paths, with hops as the tie-breaker."""
        n = self.architecture.n_cores
        adjacency = self._adjacency()

        hops = np.full((n, n), np.inf, dtype=np.float64)
        neglog = np.full((n, n), np.inf, dtype=np.float64)
        epr_latency = np.full((n, n), np.inf, dtype=np.float64)

        for source in range(n):
            h_row, n_row, e_row = self._dijkstra(
                source, adjacency, n, primary="reliability"
            )
            hops[source] = h_row
            neglog[source] = n_row
            epr_latency[source] = e_row

        if not np.isfinite(hops).all():
            unreachable = int((~np.isfinite(hops)).sum())
            raise ArchitectureError(
                f"{unreachable} core pair(s) are unreachable in "
                f"{self.architecture.label}; inter-core distance is undefined"
            )
        return hops, neglog, epr_latency

    def _adjacency(self) -> list[list[tuple[int, float]]]:
        adjacency: list[list[tuple[int, float]]] = [[] for _ in range(self.architecture.n_cores)]
        for (i, j), p in self.architecture.link_reliabilities.items():
            weight = -math.log(p)
            adjacency[i].append((j, weight))
            adjacency[j].append((i, weight))
        return adjacency

    @staticmethod
    def _dijkstra(
        source: int,
        adjacency: list[list[tuple[int, float]]],
        n: int,
        *,
        primary: str = "hops",
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        best_hops = np.full(n, np.inf, dtype=np.float64)
        best_neglog = np.full(n, np.inf, dtype=np.float64)
        best_epr_latency = np.full(n, np.inf, dtype=np.float64)
        best_hops[source] = 0.0
        best_neglog[source] = 0.0
        best_epr_latency[source] = 0.0

        if primary not in {"hops", "reliability"}:
            raise ValueError(f"unknown path objective {primary!r}")

        def key(
            hop_count: float,
            negative_log: float,
            epr_latency: float,
        ) -> tuple[float, float, float]:
            if primary == "hops":
                return hop_count, negative_log, epr_latency
            return negative_log, hop_count, epr_latency

        heap: list[tuple[float, float, float, int]] = [
            (*key(0.0, 0.0, 0.0), source)
        ]
        settled = np.zeros(n, dtype=bool)

        while heap:
            _primary, _secondary, _tertiary, node = heapq.heappop(heap)
            if settled[node]:
                continue
            settled[node] = True

            hops = best_hops[node]
            neglog = best_neglog[node]
            for neighbour, weight in adjacency[node]:
                if settled[neighbour]:
                    continue
                cand_hops = hops + 1.0
                cand_neglog = neglog + weight
                # A path succeeds only when every link succeeds, so its EPR
                # generation latency is the reciprocal of the complete path
                # reliability: 1 / product(p(e)) = exp(sum(-log(p(e)))).
                cand_epr_latency = math.exp(
                    min(cand_neglog, math.log(MAX_TRANSFER_COST))
                )

                if key(cand_hops, cand_neglog, cand_epr_latency) < key(
                    best_hops[neighbour],
                    best_neglog[neighbour],
                    best_epr_latency[neighbour],
                ):
                    best_hops[neighbour] = cand_hops
                    best_neglog[neighbour] = cand_neglog
                    best_epr_latency[neighbour] = cand_epr_latency
                    heapq.heappush(
                        heap,
                        (*key(cand_hops, cand_neglog, cand_epr_latency), neighbour),
                    )

        return best_hops, best_neglog, best_epr_latency

    @cached_property
    def hops(self) -> np.ndarray:
        matrix = self._matrices[0].copy()
        matrix.setflags(write=False)
        return matrix

    @cached_property
    def reliability(self) -> np.ndarray:
        """Reliability of the selected shortest-hop paths."""
        matrix = np.exp(-self._matrices[1])
        np.fill_diagonal(matrix, 1.0)
        matrix.setflags(write=False)
        return matrix

    @cached_property
    def transfer_cost(self) -> np.ndarray:
        """``d / p`` on the selected shortest-hop paths."""
        return self._stable_transfer_cost(self._matrices[0], self._matrices[1])

    @cached_property
    def epr_latency(self) -> np.ndarray:
        """``1 / product(p(e))`` on each selected shortest-hop path."""
        matrix = self._matrices[2].copy()
        matrix.setflags(write=False)
        return matrix

    @cached_property
    def reliable_hops(self) -> np.ndarray:
        """Hop lengths of maximum-product-reliability paths."""
        matrix = self._reliable_matrices[0].copy()
        matrix.setflags(write=False)
        return matrix

    @cached_property
    def reliable_reliability(self) -> np.ndarray:
        """Products of link reliabilities on maximum-reliability paths."""
        matrix = np.exp(-self._reliable_matrices[1])
        np.fill_diagonal(matrix, 1.0)
        matrix.setflags(write=False)
        return matrix

    @cached_property
    def reliable_transfer_cost(self) -> np.ndarray:
        """``d / p`` on maximum-product-reliability paths."""
        return self._stable_transfer_cost(
            self._reliable_matrices[0], self._reliable_matrices[1]
        )

    @cached_property
    def reliable_epr_latency(self) -> np.ndarray:
        """``1 / product(p(e))`` on each maximum-reliability path."""
        matrix = self._reliable_matrices[2].copy()
        matrix.setflags(write=False)
        return matrix

    @staticmethod
    def _stable_transfer_cost(
        hops: np.ndarray, neglog_reliability: np.ndarray
    ) -> np.ndarray:
        """Evaluate ``d / p`` in log space and return a read-only matrix."""

        # Eq. (8) uses d / rho.  Computing rho first can underflow to zero on
        # long, unreliable paths even when every link probability is valid.
        # Work in log space until the final exponentiation instead:
        # log(d / rho) = log(d) - log(rho) = log(d) + neglog(rho).
        # Values outside float64's representable range are saturated at the
        # largest safe finite transfer cost; their exact mathematical value
        # cannot be represented by the solver in any case.
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            log_cost = np.log(hops) + neglog_reliability
            matrix = np.exp(np.minimum(log_cost, math.log(MAX_TRANSFER_COST)))
        np.fill_diagonal(matrix, 0.0)
        matrix.setflags(write=False)
        return matrix

    def route_matrices(
        self, route_model: str
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return ``(hops, reliability, d/p)`` for a physical route policy."""
        if route_model == "shortest":
            return self.hops, self.reliability, self.transfer_cost
        if route_model == "reliability":
            return (
                self.reliable_hops,
                self.reliable_reliability,
                self.reliable_transfer_cost,
            )
        raise ValueError(
            f"unknown physical route model {route_model!r}; expected 'shortest' "
            "or 'reliability'"
        )

    def route_epr_latency(self, route_model: str) -> np.ndarray:
        """Return per-path EPR latency for a physical route policy."""
        if route_model == "shortest":
            return self.epr_latency
        if route_model == "reliability":
            return self.reliable_epr_latency
        raise ValueError(
            f"unknown physical route model {route_model!r}; expected 'shortest' "
            "or 'reliability'"
        )

    def route_path(
        self, source: int, target: int, route_model: str = "shortest"
    ) -> tuple[int, ...]:
        """Return a deterministic physical path selected by a route policy.

        ``shortest`` minimises hop count and then maximises the product of link
        reliabilities. ``reliability`` reverses those two priorities. If both
        quantities tie, the lexicographically smallest core-index path is used
        so exported communication requests are reproducible.
        """
        n = self.architecture.n_cores
        if not 0 <= source < n or not 0 <= target < n:
            raise ArchitectureError(
                f"route endpoints ({source}, {target}) must lie in [0, {n})"
            )
        if route_model not in {"shortest", "reliability"}:
            raise ValueError(
                f"unknown physical route model {route_model!r}; expected 'shortest' "
                "or 'reliability'"
            )
        if source == target:
            return (source,)

        adjacency = self._adjacency()

        def priority(hops: int, negative_log: float) -> tuple[float, float]:
            if route_model == "shortest":
                return float(hops), negative_log
            return negative_log, float(hops)

        start_path = (source,)
        start_key = (*priority(0, 0.0), start_path)
        best: list[tuple[float, float, tuple[int, ...]] | None] = [None] * n
        best[source] = start_key
        heap: list[
            tuple[float, float, tuple[int, ...], int, float, int]
        ] = [(*start_key, 0, 0.0, source)]

        while heap:
            primary, secondary, path, hops, negative_log, node = heapq.heappop(heap)
            if best[node] != (primary, secondary, path):
                continue
            if node == target:
                return path

            for neighbour, weight in sorted(adjacency[node]):
                if neighbour in path:
                    continue
                candidate_hops = hops + 1
                candidate_negative_log = negative_log + weight
                candidate_path = (*path, neighbour)
                candidate_key = (
                    *priority(candidate_hops, candidate_negative_log),
                    candidate_path,
                )
                if best[neighbour] is None or candidate_key < best[neighbour]:
                    best[neighbour] = candidate_key
                    heapq.heappush(
                        heap,
                        (
                            *candidate_key,
                            candidate_hops,
                            candidate_negative_log,
                            neighbour,
                        ),
                    )

        raise ArchitectureError(
            f"core {target} is unreachable from core {source} in "
            f"{self.architecture.label}"
        )

    @cached_property
    def unit(self) -> np.ndarray:
        matrix = 1.0 - np.eye(self.architecture.n_cores, dtype=np.float64)
        matrix.setflags(write=False)
        return matrix

    @property
    def n_cores(self) -> int:
        return self.architecture.n_cores

    def cost(self, source: int, target: int) -> float:
        return float(self.transfer_cost[source, target])

    def hop_count(self, source: int, target: int) -> float:
        return float(self.hops[source, target])

    def path_reliability(self, source: int, target: int) -> float:
        return float(self.reliability[source, target])

    def summary(self) -> dict[str, float]:
        n = self.architecture.n_cores
        if n < 2:
            return {"diameter": 0.0, "mean_transfer_cost": 0.0, "max_transfer_cost": 0.0}
        off_diagonal = ~np.eye(n, dtype=bool)
        return {
            "diameter": float(self.hops[off_diagonal].max()),
            "mean_transfer_cost": float(self.transfer_cost[off_diagonal].mean()),
            "max_transfer_cost": float(self.transfer_cost[off_diagonal].max()),
        }
