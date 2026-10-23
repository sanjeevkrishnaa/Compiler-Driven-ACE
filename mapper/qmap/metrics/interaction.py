
from __future__ import annotations

from collections import defaultdict

from qmap.circuit.slicer import SlicedCircuit
from qmap.exceptions import ConfigurationError

__all__ = ["DEFAULT_HORIZON", "LookaheadWeights"]

DEFAULT_HORIZON = 8
"""Default look-ahead horizon in timeslices. Truncation error is at most ``2**-8``."""

class LookaheadWeights:

    __slots__ = ("_weights", "horizon")

    def __init__(self, sliced: SlicedCircuit, horizon: int = DEFAULT_HORIZON) -> None:
        if horizon < 0:
            raise ConfigurationError(f"look-ahead horizon must be non-negative, got {horizon}")
        self.horizon = horizon
        self._weights = self._precompute(sliced, horizon)

    @staticmethod
    def _precompute(
        sliced: SlicedCircuit, horizon: int
    ) -> list[dict[int, dict[int, float]]]:
        n_slices = sliced.n_slices
        tables: list[dict[int, dict[int, float]]] = []

        for t in range(n_slices):
            table: dict[int, dict[int, float]] = defaultdict(dict)

            for offset in range(1, horizon + 1):
                m = t + offset
                if m >= n_slices:
                    break
                decay = 2.0**-offset
                for a, b in sliced.slices[m].interactions:
                    table[a][b] = table[a].get(b, 0.0) + decay
                    table[b][a] = table[b].get(a, 0.0) + decay
            tables.append(dict(table))
        return tables

    def partners(self, t: int, qubit: int) -> dict[int, float]:
        if not 0 <= t < len(self._weights):
            return {}
        return self._weights[t].get(qubit, {})

    def weight(self, t: int, q_i: int, q_j: int) -> float:
        return self.partners(t, q_i).get(q_j, 0.0)

    def __len__(self) -> int:
        return len(self._weights)

    def __str__(self) -> str:
        return f"LookaheadWeights(horizon={self.horizon}, slices={len(self._weights)})"
