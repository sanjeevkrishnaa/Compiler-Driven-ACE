
from __future__ import annotations

from qmap.placement.assignment import AssignmentSolver, HungarianSolver
from qmap.placement.base import Placer
from qmap.placement.cost import TransferModel

__all__ = ["HQANoLookaheadPlacer", "HQAPlacer"]

class HQAPlacer(Placer):

    name = "HQA"
    description = (
        "Baseline Hungarian Qubit Assignment: unit 0/1/2 placement cost; "
        "shortest-path d/p physical billing"
    )
    transfer_model = TransferModel.UNIT
    physical_route_model = "shortest"
    uses_lookahead = True

    def make_solver(self) -> AssignmentSolver:
        return HungarianSolver()

class HQANoLookaheadPlacer(Placer):

    name = "HQA-NL"
    description = "Baseline HQA, residency-only cost with no look-ahead (Eq. 1 literal)"
    transfer_model = TransferModel.UNIT
    physical_route_model = "shortest"
    uses_lookahead = False

    def make_solver(self) -> AssignmentSolver:
        return HungarianSolver()
