"""The experiment matrix.  Every case differs from the base case only in what its name says.

The base case is the configuration of docs/research/routing/greedy-xy-2026-10-30 with C=M-1:
chain-wide preparation, a two-layer lead, ready-first admission, native handoff, a 50 ms compiler
reservation and no artificial buffer.  Seeds 60-69 are the primary set for the fast settings, 60-65
for the slow grid points and 60-63 for the screens and tuning; 100-105 are held back for validating
anything chosen from tuning.  See "Deviations" in docs/research/generation-time-2026-11-01/plan.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from knobs import Knobs, ROOT

PRIMARY = ",".join(str(s) for s in range(60, 70))
TUNING = "60,61,62,63"
VALIDATION = ",".join(str(s) for s in range(100, 106))
REPLICATE = "60,61,62,63,64,65"
WORKLOADS = ("qft", "qaoa")
CONFIGS = ((3, 2), (4, 3))
SLOW = (0.95, 0.6, 0.4)
EFFICIENCY_GRID = (1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3)
DELAY_GRID = (0.1, 0.5, 1.0, 2.0, 5.0)
GAP_GRID = (0.0, 0.1, 0.5, 1.0, 2.0, 5.0, 20.0)
GAP_GRID_COARSE = (0.0, 0.5, 5.0)
BOTH = "on-demand,dynamic"
OPTIONS = dict(lead=2, lookahead=8, coherence_layers=10, reservation_ms=50.0, consumption="handoff", priority="ready-first",
               trigger="layer-start", predecessor_distance=1, planning="offline", chain_hops=None, congestion=None,
               flags=[], request_duration_ms=50.0)


def case(workload: str, route: str, memories: int, compiler: int, knobs: Knobs = Knobs(), seeds: str = PRIMARY,
         strategies: str = BOTH, tag: str = "base", **options) -> dict:
    spec = dict(OPTIONS, workload=workload, route=route, memories=memories, compiler_memories=compiler,
                generation_capacity=max(compiler, 1), knobs=knobs.overrides(), seeds=seeds, strategies=strategies,
                trace=f"results/generation_time_2026-11-01/traces/{workload}/{route}/requests.txt")
    spec.update(options)
    spec["tag"] = tag
    return spec


def efficiency() -> list[dict]:
    return [case(w, r, m, c, Knobs(memory_efficiency=e), seeds=PRIMARY if e >= 0.7 else REPLICATE) for e in EFFICIENCY_GRID
            for w in WORKLOADS for r in ("xy", "history") for m, c in CONFIGS]


def delay() -> list[dict]:
    return [case(w, r, m, c, Knobs(classical_scale=s), seeds=PRIMARY if s == 1.0 else REPLICATE) for s in DELAY_GRID
            for w in WORKLOADS for r in ("xy", "history") for m, c in CONFIGS]


def equivalence() -> list[dict]:
    """Three different physical causes of one success probability; the study treats them as one axis."""
    same_p = 0.5 * (0.6 * 0.95) ** 2 / (0.95 * 0.95) ** 2
    return [case(w, "history", 4, 3, k, seeds=TUNING) for w in WORKLOADS
            for k in (Knobs(memory_efficiency=0.6), Knobs(detector_efficiency=0.6), Knobs(bsm_success_rate=same_p))]


def gap() -> list[dict]:
    return [case(w, "history", m, c, Knobs(memory_efficiency=e, empty_gap_ms=g), seeds=TUNING) for m, c in CONFIGS
            for g in (GAP_GRID if m == 4 else GAP_GRID_COARSE) for e in SLOW for w in WORKLOADS]


def scale() -> list[dict]:
    """If only ratios mattered, scaling every time constant by a would scale latency by a and nothing else."""
    out = []
    for a in (0.01, 0.1, 2.0):
        for w in WORKLOADS:
            knobs = Knobs(classical_scale=a, empty_gap_ms=5.0 * a)
            out.append(case(w, "history", 4, 3, knobs, seeds=TUNING, tag="delay+gap"))
            out.append(case(w, "history", 4, 3, knobs, seeds=TUNING, tag="delay+gap+windows", reservation_ms=50.0 * a, request_duration_ms=50.0 * a))
    return out


def chip() -> list[dict]:
    """Fast classical control with a local-gate layer far shorter than the 5 ms legacy constant."""
    return [case(w, "history", 4, 3, Knobs(classical_scale=s, empty_gap_ms=g), seeds=TUNING) for s in (0.01, 0.1)
            for g in (0.0, 0.1, 1.0, 5.0) for w in WORKLOADS]


def memory() -> list[dict]:
    return [case(w, "history", m, m - 1, Knobs(memory_efficiency=e), seeds=TUNING) for m in (2, 3, 4, 6, 8) for e in (0.95, 0.4) for w in WORKLOADS]


def lead_gap() -> list[dict]:
    return [case(w, "history", 4, 3, Knobs(memory_efficiency=e, empty_gap_ms=g), seeds=TUNING, strategies="dynamic",
                 tag=f"lead={lead}", lead=lead, lookahead=max(8, lead), coherence_layers=max(10, lead + 2))
            for lead in (1, 2, 3, 4, 6, 8) for g in (0.0, 5.0) for e in (0.95, 0.4) for w in WORKLOADS]


def tuning_options(memories: int, compiler: int) -> list[tuple[str, dict]]:
    options: list[tuple[str, dict]] = [("default", {})]
    options += [(f"lead={v}", dict(lead=v)) for v in (1, 3, 4, 6, 8)]
    options += [(f"lookahead={v}", dict(lookahead=v)) for v in (2, 4, 16)]
    options += [(f"reservation={v:g}", dict(reservation_ms=float(v))) for v in (10, 100, 1000)]
    options += [(f"capacity={v}", dict(generation_capacity=v)) for v in (1, 8)]
    options += [(f"C={v}", dict(compiler_memories=v, generation_capacity=max(v, 1)))
                for v in range(1, memories + 1) if v != compiler]
    options += [("predecessor-1", dict(trigger="predecessor-start", predecessor_distance=1)),
                ("predecessor-2", dict(trigger="predecessor-start", predecessor_distance=2)),
                ("refill", dict(flags=["--refill-on-release"])), ("demand-first", dict(flags=["--demand-first"])),
                ("borrow", dict(flags=["--borrow-compiler-pairs"])), ("runtime", dict(planning="runtime")),
                ("first-hop", dict(chain_hops=1)), ("two-hops", dict(chain_hops=2)), ("congestion=25", dict(congestion=25)),
                ("swap", dict(consumption="swap")), ("fifo", dict(priority="fifo"))]
    return options


def tuning() -> list[dict]:
    return [case(w, "history", m, c, Knobs(memory_efficiency=e), seeds=TUNING, strategies="dynamic", tag=name, **options)
            for e in (0.95, 0.4) for w in WORKLOADS for m, c in CONFIGS for name, options in tuning_options(m, c)]


def coherence() -> list[dict]:
    return [case(w, "history", 4, 3, Knobs(memory_efficiency=e, coherence_time_s=t), seeds=TUNING) for t in (1.0, 0.1, 0.01, 0.001)
            for e in SLOW for w in WORKLOADS]


def routes() -> list[dict]:
    return [case(w, r, 4, 3, Knobs(memory_efficiency=e), seeds=TUNING) for r in ("xy", "greedy", "history", "minhop") for e in SLOW
            for w in WORKLOADS]


def workloads() -> list[dict]:
    return [case(w, r, 4, 3, Knobs(memory_efficiency=e), seeds=TUNING)
            for w in ("draper_qft_adder", "cdkm_ripple_carry_adder", "randomcircuit") for r in ("xy", "history")
            for e in (0.95, 0.4)]


def validation() -> list[dict]:
    """Written by choose_tuned.py from the tuning seeds, run on seeds that tuning never saw."""
    path = ROOT / "docs" / "research" / "generation-time-2026-11-01" / "data" / "tuned_choices.json"
    out = []
    for choice in json.loads(path.read_text()):
        knobs = Knobs(memory_efficiency=choice["memory_efficiency"])
        m, c = choice["memories"], choice["compiler_memories"]
        out.append(case(choice["workload"], "history", m, c, knobs, seeds=VALIDATION, tag="default"))
        out.append(case(choice["workload"], "history", m, c, knobs, seeds=VALIDATION, strategies="dynamic",
                        tag=choice["tag"], **choice["options"]))
    return out


EXPERIMENTS = dict(efficiency=efficiency, delay=delay, equivalence=equivalence, gap=gap, scale=scale, chip=chip, memory=memory,
                   lead_gap=lead_gap, tuning=tuning, coherence=coherence, routes=routes, workloads=workloads, validation=validation)
