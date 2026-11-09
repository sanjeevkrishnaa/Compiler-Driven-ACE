"""Shared defaults for compiler-directed physical preparation.

This bounds the compiler-owned reservation from its scheduled start. It is not
the physical coherence time, a layer count, or an added request latency.
The 50 ms policy is evaluated in the 2026-10-29 reservation-window study.
"""

from dataclasses import dataclass


DEFAULT_COMPILER_RESERVATION_MS = 50.0


@dataclass(frozen=True)
class CompilerPolicyDefaults:
    """Permanent quota-six, demand-guarded active-layer policy."""

    total_memories: int = 8
    compiler_memories: int = 6
    generation_capacity: int = 8
    planner_lead_layers: int = 2
    dynamic_lookahead_layers: int = 2
    coherence_time_layers: float = 10
    empty_layer_gap_ms: float = 0.00001
    dynamic_layer_basis: str = "active"
    scheduler: str = "per-qubit"
    demand_first: bool = True
    refill_on_release: bool = True
    preparation_priority: str = "trace"
    borrow_compiler_pairs: bool = True


DEFAULT_COMPILER_POLICY = CompilerPolicyDefaults()
