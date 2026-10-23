
from __future__ import annotations

from qmap.placement.assignment import AssignmentSolver, HungarianSolver
from qmap.placement.base import Placer
from qmap.placement.cost import TransferModel

__all__ = ["THQAPlacer"]

class THQAPlacer(Placer):

    name = "T-HQA"
    description = (
        "Topology-aware HQA: shortest-hop placement cost; shortest-path d/p "
        "physical billing (Eq. 2, 6)"
    )
    transfer_model = TransferModel.DISTANCE
    physical_route_model = "shortest"
    uses_lookahead = True

    def make_solver(self) -> AssignmentSolver:
        return HungarianSolver()
