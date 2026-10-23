from __future__ import annotations

from qmap.placement.assignment import AssignmentSolver, HungarianSolver
from qmap.placement.base import Placer
from qmap.placement.cost import TransferModel

__all__ = ["THQARPlacer"]


class THQARPlacer(Placer):
    """Topology-aware placement followed by maximum-reliability routing."""

    name = "T-HQAR"
    description = (
        "Topology-aware HQA: decide placement with shortest-hop distance, then "
        "route transfers on maximum-product-reliability paths and bill their d/p"
    )
    transfer_model = TransferModel.DISTANCE
    physical_route_model = "reliability"
    uses_lookahead = True

    def make_solver(self) -> AssignmentSolver:
        return HungarianSolver()
