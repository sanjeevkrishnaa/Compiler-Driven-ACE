
from __future__ import annotations

import numpy as np

from qmap.metrics.interaction import LookaheadWeights

__all__ = ["operation_attraction", "qubit_attraction"]

def qubit_attraction(
    qubit: int,
    timeslice: int,
    placement: np.ndarray,
    weights: LookaheadWeights,
    n_cores: int,
    out: np.ndarray | None = None,
) -> np.ndarray:
    result = np.zeros(n_cores, dtype=np.float64) if out is None else out
    for partner, weight in weights.partners(timeslice, qubit).items():
        result[placement[partner]] += weight
    return result

def operation_attraction(
    q_alpha: int,
    q_beta: int,
    timeslice: int,
    placement: np.ndarray,
    weights: LookaheadWeights,
    n_cores: int,
    out: np.ndarray | None = None,
) -> np.ndarray:
    if out is None:
        buffer = np.zeros(n_cores, dtype=np.float64)
    else:
        buffer = out
        buffer.fill(0.0)

    qubit_attraction(q_alpha, timeslice, placement, weights, n_cores, out=buffer)
    qubit_attraction(q_beta, timeslice, placement, weights, n_cores, out=buffer)
    buffer *= 0.5
    return buffer
