
from __future__ import annotations

from qmap.placement.assignment import AssignmentSolver, HungarianSolver
from qmap.placement.base import Placer
from qmap.placement.cost import TransferModel

__all__ = ["TRHQAPlacer"]

class TRHQAPlacer(Placer):

    name = "TR-HQA"
    description = (
        "Topology- and reliability-aware HQA: shortest-path d/p placement "
        "and physical billing, Hungarian assignment (Eq. 8, 9)"
    )
    transfer_model = TransferModel.RELIABILITY
    physical_route_model = "shortest"
    uses_lookahead = True

    def make_solver(self) -> AssignmentSolver:
        return HungarianSolver()
