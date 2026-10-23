
from __future__ import annotations

from qmap.placement.assignment import AssignmentSolver, GreedySolver
from qmap.placement.base import Placer
from qmap.placement.cost import TransferModel

__all__ = ["GTRQAPlacer"]

class GTRQAPlacer(Placer):

    name = "GTR-QA"
    description = (
        "Greedy topology- and reliability-aware mapping: shortest-path d/p "
        "placement and physical billing, sequential argmin assignment (Eq. 10)"
    )
    transfer_model = TransferModel.RELIABILITY
    physical_route_model = "shortest"
    uses_lookahead = True

    def make_solver(self) -> AssignmentSolver:
        return GreedySolver()
