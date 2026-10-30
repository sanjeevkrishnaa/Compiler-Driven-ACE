"""Shared defaults for compiler-directed physical preparation.

This bounds the compiler-owned reservation from its scheduled start. It is not
the physical coherence time, a layer count, or an added request latency.
The 50 ms policy is evaluated in the 2026-10-29 reservation-window study.
"""

DEFAULT_COMPILER_RESERVATION_MS = 50.0
