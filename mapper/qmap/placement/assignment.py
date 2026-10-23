
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from qmap.placement.cost import INFEASIBLE_COST

__all__ = ["Assignment", "AssignmentSolver", "GreedySolver", "HungarianSolver"]

@dataclass(frozen=True, slots=True)
class Assignment:

    operations: np.ndarray
    cores: np.ndarray

    @property
    def count(self) -> int:
        return int(self.operations.size)

    def __bool__(self) -> bool:
        return self.count > 0

class AssignmentSolver(ABC):

    name: str

    @abstractmethod
    def solve(
        self,
        cost: np.ndarray,
        occupancy: np.ndarray,
        required: np.ndarray,
        capacity: int,
    ) -> Assignment:
        pass

class HungarianSolver(AssignmentSolver):

    name = "hungarian"

    def solve(
        self,
        cost: np.ndarray,
        occupancy: np.ndarray,
        required: np.ndarray,
        capacity: int,
    ) -> Assignment:
        del occupancy, required, capacity

        feasible = np.isfinite(cost) & (cost < INFEASIBLE_COST)
        if not feasible.any():
            return Assignment(np.empty(0, dtype=np.intp), np.empty(0, dtype=np.intp))

        sentinel = float(np.nextafter(cost[feasible].max(), np.inf))
        sanitised = np.where(feasible, cost, sentinel)

        rows, cols = linear_sum_assignment(sanitised)

        keep = feasible[rows, cols]
        return Assignment(operations=rows[keep], cores=cols[keep])

class GreedySolver(AssignmentSolver):

    name = "greedy"

    def solve(
        self,
        cost: np.ndarray,
        occupancy: np.ndarray,
        required: np.ndarray,
        capacity: int,
    ) -> Assignment:
        load = occupancy.copy()

        chosen_operations: list[int] = []
        chosen_cores: list[int] = []

        for op in range(cost.shape[0]):

            room = load + required[op] <= capacity
            feasible = np.isfinite(cost[op]) & (cost[op] < INFEASIBLE_COST) & room
            if not feasible.any():
                continue

            candidates = np.where(feasible, cost[op], np.inf)
            core = int(np.argmin(candidates))

            chosen_operations.append(int(op))
            chosen_cores.append(core)

            load[core] += int(required[op, core])

        return Assignment(
            operations=np.asarray(chosen_operations, dtype=np.intp),
            cores=np.asarray(chosen_cores, dtype=np.intp),
        )
