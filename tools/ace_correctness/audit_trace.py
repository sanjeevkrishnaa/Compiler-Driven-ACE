#!/usr/bin/env python3
"""Run a compiler trace through ACE with the invariant monitor attached and report violations.

The run is exactly the one ``run_trace_comparison.py`` would make (it builds the compiler
spec with the runner's own function), plus an event recorder.  Results are identical with or
without the recorder; what is added is a check of the execution against ``invariants.py``.

    python tools/ace_correctness/audit_trace.py --trace data/tracegen/random16_d80_seed303.txt \
        --strategy dynamic --seed 0

Exit status 0 when no invariant is violated, 1 otherwise.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ace.compiler.compiler_trace import (                                    # noqa: E402
    mesh_dimensions, parse_compiler_trace, to_ace_layers, validate_neighbor_requests,
)
from ace.observability.execution_events import Event, ListRecorder               # noqa: E402
from ace.observability.invariants import RequestInfo, Violation, check_events, summarize  # noqa: E402
from ace.simulation.parallel_core import run_parallel_experiment               # noqa: E402
from ace.cli.run_trace_comparison import _compiler_spec                 # noqa: E402

DEFAULT_CONFIG = REPO_ROOT / "config" / "final_config" / "grid_4x4_ace_3.json"
COMPILER_STRATEGIES = ("on-demand", "fixed", "dynamic")


@dataclass(frozen=True)
class Audit:
    requested: int
    completed: int
    events: list[Event]
    violations: list[Violation]
    makespan_ms: float = 0.0
    total_retries: int = 0
    max_retries_one_request: int = 0
    max_admission_wait_ms: float = 0.0
    wall_seconds: float = 0.0


def audit_trace(
    trace_path: Path,
    strategy: str,
    *,
    seed: int = 0,
    total_memories: int = 4,
    compiler_memories: int = 3,
    generation_capacity: int = 3,
    stop_time_s: float = 300.0,
    config: Path = DEFAULT_CONFIG,
    mesh: str = "4x4",
    scheduler: str = "legacy",
    scheduler_options: dict | None = None,
    record: bool = True,
    compiler_reservation_ms: float = 1000,
) -> Audit:
    """Run ``strategy`` on the trace under ``scheduler`` and check the recorded execution.

    With the per-qubit scheduler a request must also be submitted only after the previous hop of
    its qubit completed, so that invariant is checked as well.
    """
    if strategy not in COMPILER_STRATEGIES:
        raise ValueError(f"strategy must be one of {COMPILER_STRATEGIES}, got {strategy!r}")
    trace = parse_compiler_trace(trace_path)
    rows, columns = mesh_dimensions(trace, mesh)
    validate_neighbor_requests(trace, rows, columns)
    layers = to_ace_layers(trace, columns=columns, fidelity=0.01)
    arguments = Namespace(
        compiler_memories=compiler_memories, generation_capacity=generation_capacity,
        coherence_time_layers=10, delta_layers=6, dynamic_lookahead_layers=8,
        fidelity_threshold=0.01, compiler_reservation_ms=compiler_reservation_ms)
    spec = _compiler_spec(arguments, trace, columns, strategy)

    recorder = ListRecorder() if record else None       # record=False times the bare simulation
    started = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        result = run_parallel_experiment(
            str(config), False, False, layers, 5.3, 50, f"audit-{strategy}-{seed}", seed=seed,
            compiler_spec=spec, total_memories_per_core=total_memories,
            simulation_stop_time_s=stop_time_s, serialize_conflicts=True, recorder=recorder,
            scheduler=scheduler, scheduler_options=scheduler_options)

    wall = time.perf_counter() - started
    if recorder is None:
        stats = result["stats"]
        parts = stats["timing_breakdown"].values()
        return Audit(len(trace.requests), stats["completed_requests"], [], [], stats["end_to_end_latency_ms"],
                     stats.get("total_retries", 0), max((p["retry_count"] for p in parts), default=0),
                     max((p.get("admission_wait_time_ms", 0.0) for p in parts), default=0.0), wall)
    info = {r.request_id: RequestInfo(r.request_id, r.layer, r.qubit, r.order) for r in trace.requests}
    violations = check_events(recorder.events, info, require_completion=True,
                              submission_after_predecessor=(scheduler == "per-qubit"))
    stats = result["stats"]
    parts = stats["timing_breakdown"].values()
    return Audit(len(info), stats["completed_requests"], recorder.events, violations,
                 stats["end_to_end_latency_ms"], stats.get("total_retries", 0),
                 max((p["retry_count"] for p in parts), default=0),
                 max((p.get("admission_wait_time_ms", 0.0) for p in parts), default=0.0), wall)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--strategy", choices=COMPILER_STRATEGIES, default="dynamic")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--total-memories", type=int, default=4)
    parser.add_argument("--compiler-memories", type=int, default=3)
    parser.add_argument("--generation-capacity", type=int, default=3)
    parser.add_argument("--stop-time-s", type=float, default=300.0)
    parser.add_argument("--scheduler", choices=("legacy", "per-qubit"), default="legacy")
    parser.add_argument("--admission", choices=("poll", "event"), default=None,
                        help="per-qubit scheduler only (default: event)")
    parser.add_argument("--no-starvation-guard", action="store_true", help="per-qubit event admission only")
    parser.add_argument("--show", type=int, default=5, help="examples to print per invariant")
    args = parser.parse_args(argv)

    options = {}
    if args.admission is not None:
        options["admission"] = args.admission
    if args.no_starvation_guard:
        options["starvation_guard"] = False
    audit = audit_trace(args.trace, args.strategy, seed=args.seed, total_memories=args.total_memories,
                        compiler_memories=args.compiler_memories, generation_capacity=args.generation_capacity,
                        stop_time_s=args.stop_time_s, scheduler=args.scheduler,
                        scheduler_options=options)
    print(f"{args.strategy} [{args.scheduler}]: {audit.completed}/{audit.requested} requests completed, "
          f"makespan {audit.makespan_ms:.2f} ms, {audit.total_retries} retries, "
          f"{len(audit.events)} events, {len(audit.violations)} violations")
    for name, count in sorted(summarize(audit.violations).items()):
        print(f"  {name}: {count}")
        for violation in [v for v in audit.violations if v.invariant == name][: args.show]:
            when = "end of run" if violation.time_ps is None else f"{violation.time_ps / 1e9:.3f} ms"
            print(f"      [{when}] {violation.detail}")
    return 0 if not audit.violations else 1


if __name__ == "__main__":
    sys.exit(main())
