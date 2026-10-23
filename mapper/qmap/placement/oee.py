
from __future__ import annotations

import logging

import numpy as np

from qmap.exceptions import ConfigurationError
from qmap.metrics.distance import DistanceOracle
from qmap.partition import CORE_DTYPE

__all__ = [
    "DEFAULT_MAX_PASSES",
    "OBJECTIVES",
    "objective_matrix",
    "oee_refine",
    "placement_objective",
]

logger = logging.getLogger(__name__)

DEFAULT_MAX_PASSES = 8
"""Cap on refinement passes. Convergence is typically reached in 2-4."""

OBJECTIVES = ("cut", "hops", "cost")
"""Registered ``D`` choices, in increasing architecture awareness."""

def objective_matrix(kind: str, oracle: DistanceOracle) -> np.ndarray:
    if kind == "cut":
        n = oracle.hops.shape[0]
        return (1.0 - np.eye(n)).astype(np.float64)
    if kind == "hops":
        matrix = np.asarray(oracle.hops, dtype=np.float64).copy()
    elif kind == "cost":
        matrix = np.asarray(oracle.transfer_cost, dtype=np.float64).copy()
    else:
        raise ConfigurationError(
            f"unknown OEE objective {kind!r}; available: {', '.join(OBJECTIVES)}"
        )

    if not np.isfinite(matrix).all():
        finite = matrix[np.isfinite(matrix)]
        matrix[~np.isfinite(matrix)] = finite.max() * 10.0 if finite.size else 1.0
    np.fill_diagonal(matrix, 0.0)
    return matrix

def placement_objective(
    placement: np.ndarray, weights: np.ndarray, distances: np.ndarray
) -> float:
    if placement.size == 0:
        return 0.0
    return float(0.5 * np.sum(weights * distances[np.ix_(placement, placement)]))

def _affinity(
    placement: np.ndarray, weights: np.ndarray, distances: np.ndarray
) -> np.ndarray:
    return weights @ distances[placement, :]

def _exchange_gains(
    placement: np.ndarray,
    weights: np.ndarray,
    distances: np.ndarray,
    affinity: np.ndarray,
) -> np.ndarray:
    own = affinity[np.arange(placement.size), placement]

    cross = affinity[:, placement]
    delta = (cross - own[:, None]) + (cross - own[:, None]).T
    gains = -(delta + 2.0 * weights * distances[np.ix_(placement, placement)])
    gains[placement[:, None] == placement[None, :]] = -np.inf
    return gains

def oee_refine(
    placement: np.ndarray,
    weights: np.ndarray,
    distances: np.ndarray,
    *,
    max_passes: int = DEFAULT_MAX_PASSES,
    tolerance: float = 1e-9,
) -> tuple[np.ndarray, int]:
    current = placement.astype(np.int64, copy=True)
    n_qubits = current.size
    if n_qubits < 2 or weights.sum() == 0:
        return current.astype(CORE_DTYPE), 0

    weights = np.asarray(weights, dtype=np.float64)

    for pass_index in range(max_passes):
        trial = current.copy()
        affinity = _affinity(trial, weights, distances)
        locked = np.zeros(n_qubits, dtype=bool)

        sequence: list[tuple[int, int]] = []
        cumulative = 0.0
        best_total, best_prefix = 0.0, 0

        for _ in range(n_qubits // 2):
            gains = _exchange_gains(trial, weights, distances, affinity)
            gains[locked, :] = -np.inf
            gains[:, locked] = -np.inf
            if not np.isfinite(gains).any():
                break

            flat = int(np.argmax(gains))
            u, v = divmod(flat, n_qubits)
            gain = float(gains[u, v])

            core_u, core_v = int(trial[u]), int(trial[v])

            affinity += np.outer(
                weights[:, u] - weights[:, v], distances[:, core_v] - distances[:, core_u]
            )
            trial[u], trial[v] = core_v, core_u
            locked[u] = locked[v] = True

            cumulative += gain
            sequence.append((u, v))
            if cumulative > best_total + tolerance:
                best_total, best_prefix = cumulative, len(sequence)

        if best_prefix == 0:
            logger.debug("OEE converged after %d pass(es)", pass_index)
            return current.astype(CORE_DTYPE), pass_index

        for u, v in sequence[:best_prefix]:
            current[u], current[v] = current[v], current[u]
        logger.debug(
            "OEE pass %d: %d exchange(s), objective -%.4g",
            pass_index,
            best_prefix,
            best_total,
        )

    return current.astype(CORE_DTYPE), max_passes
