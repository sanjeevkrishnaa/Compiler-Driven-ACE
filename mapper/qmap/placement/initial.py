
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from qmap.exceptions import ConfigurationError, PlacementError
from qmap.partition import CORE_DTYPE
from qmap.rng import SeedSequence

if TYPE_CHECKING:
    from qmap.circuit.slicer import SlicedCircuit
    from qmap.metrics.distance import DistanceOracle

__all__ = [
    "DEFAULT_INITIAL_PLACEMENT",
    "INITIAL_PLACEMENTS",
    "InitialPlacement",
    "PlacementContext",
    "initial_placement",
    "list_initial_placements",
    "register_initial_placement",
]

@dataclass(frozen=True, slots=True)
class PlacementContext:

    n_qubits: int
    n_cores: int
    slots_per_core: int
    capacity: int
    rng: np.random.Generator
    sliced: SlicedCircuit | None = None
    oracle: DistanceOracle | None = None

    def require_circuit(self, strategy: str) -> tuple[SlicedCircuit, DistanceOracle]:
        if self.sliced is None or self.oracle is None:
            raise ConfigurationError(
                f"initial placement {strategy!r} is circuit-aware and needs both the "
                f"timesliced circuit and the distance oracle; the caller supplied "
                f"sliced={self.sliced!r}, oracle={self.oracle!r}"
            )
        return self.sliced, self.oracle

InitialPlacement = Callable[["PlacementContext"], np.ndarray]
"""``PlacementContext -> (n_qubits,)`` array of core indices."""

DEFAULT_INITIAL_PLACEMENT = "sequential"
"""Default strategy. Deterministic, and the natural reading of "initial placement"."""

INITIAL_PLACEMENTS: dict[str, InitialPlacement] = {}
"""Registry of strategies. Extend via :func:`register_initial_placement`."""

def register_initial_placement(name: str) -> Callable[[InitialPlacement], InitialPlacement]:

    def decorator(strategy: InitialPlacement) -> InitialPlacement:
        key = name.lower()
        if key in INITIAL_PLACEMENTS:
            raise ConfigurationError(f"initial placement {name!r} is already registered")
        INITIAL_PLACEMENTS[key] = strategy
        return strategy

    return decorator

@register_initial_placement("sequential")
def _sequential(ctx: PlacementContext) -> np.ndarray:
    return (np.arange(ctx.n_qubits, dtype=CORE_DTYPE) // ctx.slots_per_core).astype(
        CORE_DTYPE
    )

@register_initial_placement("round_robin")
def _round_robin(ctx: PlacementContext) -> np.ndarray:
    n_cores, spread = ctx.n_cores, ctx.slots_per_core
    slots = np.repeat(np.arange(n_cores, dtype=CORE_DTYPE), spread)
    order = np.arange(n_cores * spread).reshape(spread, n_cores).T.reshape(-1)
    return slots[np.argsort(order, kind="stable")][: ctx.n_qubits].astype(CORE_DTYPE)

@register_initial_placement("random")
def _random(ctx: PlacementContext) -> np.ndarray:
    slots = np.repeat(np.arange(ctx.n_cores, dtype=CORE_DTYPE), ctx.slots_per_core)
    ctx.rng.shuffle(slots)
    return slots[: ctx.n_qubits].astype(CORE_DTYPE)

def _make_oee(objective: str, name: str) -> InitialPlacement:

    def strategy(ctx: PlacementContext) -> np.ndarray:
        from qmap.placement.oee import objective_matrix, oee_refine

        sliced, oracle = ctx.require_circuit(name)
        seed_placement = _sequential(ctx).astype(np.int64)
        refined, _ = oee_refine(
            seed_placement,
            sliced.interaction_matrix().astype(np.float64),
            objective_matrix(objective, oracle),
        )
        return refined

    strategy.__name__ = f"_oee_{objective}"
    strategy.__doc__ = f"OEE refinement minimising the {objective!r} objective."
    return strategy

register_initial_placement("oee")(_make_oee("cut", "oee"))
register_initial_placement("oee_hops")(_make_oee("hops", "oee_hops"))
register_initial_placement("oee_cost")(_make_oee("cost", "oee_cost"))

def list_initial_placements() -> list[str]:
    return sorted(INITIAL_PLACEMENTS)

def initial_placement(
    strategy: str,
    n_qubits: int,
    n_cores: int,
    slots_per_core: int,
    capacity: int,
    seed: SeedSequence,
    *,
    sliced: SlicedCircuit | None = None,
    oracle: DistanceOracle | None = None,
) -> np.ndarray:
    key = strategy.lower()
    if key not in INITIAL_PLACEMENTS:
        raise ConfigurationError(
            f"unknown initial placement {strategy!r}; "
            f"available: {', '.join(list_initial_placements())}"
        )
    if n_qubits > n_cores * capacity:
        raise PlacementError(
            f"circuit needs {n_qubits} qubits but the architecture holds at most "
            f"{n_cores * capacity} ({n_cores} cores x {capacity} capacity)"
        )

    spread = slots_per_core if n_qubits <= n_cores * slots_per_core else capacity

    context = PlacementContext(
        n_qubits=n_qubits,
        n_cores=n_cores,
        slots_per_core=spread,
        capacity=capacity,
        rng=seed.stream(f"initial-placement.{key}").generator(),
        sliced=sliced,
        oracle=oracle,
    )
    placement = INITIAL_PLACEMENTS[key](context)

    if placement.shape != (n_qubits,):
        raise PlacementError(
            f"initial placement {strategy!r} returned shape {placement.shape}, "
            f"expected ({n_qubits},)"
        )
    if n_qubits and (placement.min() < 0 or placement.max() >= n_cores):
        raise PlacementError(
            f"initial placement {strategy!r} produced out-of-range core indices"
        )
    occupancy = np.bincount(placement, minlength=n_cores)
    if (occupancy > capacity).any():
        overloaded = int(np.argmax(occupancy))
        raise PlacementError(
            f"initial placement {strategy!r} overloads core {overloaded}: "
            f"{occupancy[overloaded]} qubits exceed capacity {capacity}"
        )
    return placement.astype(CORE_DTYPE, copy=False)
