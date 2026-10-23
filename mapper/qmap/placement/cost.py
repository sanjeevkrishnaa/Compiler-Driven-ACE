
from __future__ import annotations

from enum import Enum

import numpy as np

from qmap.metrics.distance import DistanceOracle
from qmap.metrics.interaction import LookaheadWeights
from qmap.placement.attraction import operation_attraction

__all__ = [
    "DEFAULT_LOOKAHEAD_WEIGHT",
    "DEFAULT_NORMALIZATION",
    "INFEASIBLE_COST",
    "CostNormalization",
    "TransferModel",
    "build_cost_matrix",
]

DEFAULT_LOOKAHEAD_WEIGHT = 1.0
"""``lambda`` in Eq. (6) and (9). Section 5.2: "we set lambda = 1 unless stated"."""

class CostNormalization(Enum):

    NONE = "none"
    MINMAX = "minmax"

DEFAULT_NORMALIZATION = CostNormalization.NONE
"""Eq. (6)/(9) as published. Normalisation is opt-in via ``--cost-normalization``."""

# A finite capacity sentinel keeps SciPy's assignment solver numerically
# well-defined.  It is deliberately larger than two saturated operand costs.
INFEASIBLE_COST = np.finfo(np.float64).max / 4.0


def _normalize_rows(cost: np.ndarray, feasible: np.ndarray) -> None:
    """Apply the legacy ``minmax`` option as a row-wise cost shift.

    The option name is retained for CLI and experiment compatibility, but the
    operation is intentionally *not* min--max scaling.  Subtracting a
    row-wise constant preserves the raw expected-cost differences in Eq. (9);
    dividing each row by its range would change the assignment objective.
    """

    low = np.min(np.where(feasible, cost, np.inf), axis=1, keepdims=True)
    with np.errstate(invalid="ignore"):
        shifted = cost - low
    cost[:] = np.where(feasible, shifted, INFEASIBLE_COST)

class TransferModel(Enum):

    UNIT = "unit"
    DISTANCE = "distance"
    RELIABILITY = "reliability"

    def matrix(self, oracle: DistanceOracle) -> np.ndarray:
        if self is TransferModel.UNIT:
            return oracle.unit
        if self is TransferModel.DISTANCE:
            return oracle.hops
        return oracle.transfer_cost

def build_cost_matrix(
    interactions: tuple[tuple[int, int], ...],
    placement: np.ndarray,
    oracle: DistanceOracle,
    model: TransferModel,
    *,
    capacity: int,
    weights: LookaheadWeights | None = None,
    timeslice: int = 0,
    lookahead_weight: float = DEFAULT_LOOKAHEAD_WEIGHT,
    normalization: CostNormalization = DEFAULT_NORMALIZATION,
) -> np.ndarray:
    n_cores = oracle.n_cores
    transfer = model.matrix(oracle)
    occupancy = np.bincount(placement, minlength=n_cores)

    cost = np.empty((len(interactions), n_cores), dtype=np.float64)
    feasible = np.empty((len(interactions), n_cores), dtype=bool)
    attraction = (
        np.empty((len(interactions), n_cores), dtype=np.float64)
        if weights is not None
        else None
    )

    for row, (q_alpha, q_beta) in enumerate(interactions):
        core_alpha = int(placement[q_alpha])
        core_beta = int(placement[q_beta])

        row_cost = transfer[core_alpha] + transfer[core_beta]

        if attraction is not None:
            operation_attraction(
                q_alpha,
                q_beta,
                timeslice,
                placement,
                weights,
                n_cores,
                out=attraction[row],
            )

        residents = np.zeros(n_cores, dtype=np.int64)
        residents[core_alpha] += 1
        residents[core_beta] += 1
        row_feasible = occupancy - residents + 2 <= capacity
        row_cost = np.where(row_feasible, row_cost, INFEASIBLE_COST)

        cost[row] = row_cost
        feasible[row] = row_feasible

    if normalization is CostNormalization.MINMAX:
        _normalize_rows(cost, feasible)

    if attraction is not None:
        cost[feasible] -= lookahead_weight * attraction[feasible]
        cost[~feasible] = INFEASIBLE_COST

    return cost
