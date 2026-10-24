"""Run small request sets through the real ACE simulator with the invariant monitor attached.

Used by the microcase tests and by audits.  Nothing here simulates anything itself: it
builds the layered requests ACE expects, calls ``run_parallel_experiment`` and returns what
happened together with the invariants that were violated.

Speculative generation is switched off (``adaptive_max_memory = 0``), so the only demand on
a core's memories is the requests given.  That is the clean setting for asking what the
reservation and request layers do with concurrent demand.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:          # ACE's modules live at the repository root
    sys.path.insert(0, str(REPO_ROOT))

from compiler_trace import CompilerRequest, router_name     # noqa: E402
from execution_events import Event, ListRecorder           # noqa: E402
from invariants import RequestInfo, Violation, check_events  # noqa: E402
from parallel_core import run_parallel_experiment          # noqa: E402

CONFIG = REPO_ROOT / "config" / "final_config" / "grid_4x4_ace_3.json"
MESH_COLUMNS = 4
FIDELITY_TARGET = 0.01          # the threshold the trace-driven runs use; trivially met


@dataclass(frozen=True)
class Hop:
    """One adjacent-core EPR request of a layer, in trace order."""

    request_id: int
    source_core: int
    destination_core: int
    qubit: int = 0


@dataclass(frozen=True)
class Outcome:
    requested: int
    completed: int
    total_retries: int
    retry_layers: int
    makespan_ms: float
    latencies_ms: dict[int, float]
    events: list[Event]
    violations: list[Violation]


def are_neighbours(a: int, b: int, columns: int = MESH_COLUMNS) -> bool:
    """Whether two row-major core indices share a link on the mesh."""
    (ra, ca), (rb, cb) = divmod(a, columns), divmod(b, columns)
    return abs(ra - rb) + abs(ca - cb) == 1


def _config_without_speculation(directory: Path) -> Path:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["templates"]["adaptive_protocol"]["adaptive_max_memory"] = 0
    path = directory / "config_without_speculation.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def run_layers(
    layers: Sequence[Sequence[Hop]],
    *,
    memories: int,
    seed: int = 0,
    serialize: bool = False,
    distinct_fidelity_targets: bool = False,
    stop_time_s: float = 60.0,
    submission_after_predecessor: bool = False,
    scheduler: str = "legacy",
    request_duration_ms: float = 50,
) -> Outcome:
    """Run ``layers`` and check the recorded execution.

    ``scheduler`` is passed to ``run_parallel_experiment``; the per-qubit one is given the
    hops as the trace's request records, so consecutive hops of one qubit in a layer chain.
    ``distinct_fidelity_targets`` gives every request a slightly different fidelity target
    (``0.01 + request_id * 1e-6``).  The difference is physically irrelevant, but it makes
    otherwise identical reservations compare unequal, which separates "the simulator copes
    with concurrent demand" from "the simulator confuses equal-looking requests".
    """
    # ACE would route a non-adjacent request through relays that need two memories each, and
    # with a small budget such a request can never be admitted.  Trace requests are always
    # single links, so a microcase that is not one is a mistake in the test, not a finding.
    for hop in (hop for layer in layers for hop in layer):
        if not are_neighbours(hop.source_core, hop.destination_core):
            raise ValueError(f"request {hop.request_id}: cores {hop.source_core} and "
                             f"{hop.destination_core} are not neighbours")
    layered = [
        [(hop.request_id, router_name(hop.source_core, MESH_COLUMNS),
          router_name(hop.destination_core, MESH_COLUMNS), 1,
          FIDELITY_TARGET + (hop.request_id * 1e-6 if distinct_fidelity_targets else 0.0), 1)
         for hop in layer]
        for layer in layers
    ]
    info: dict[int, RequestInfo] = {}
    for layer_index, layer in enumerate(layers):
        for order, hop in enumerate(layer):
            info[hop.request_id] = RequestInfo(hop.request_id, layer_index, hop.qubit, order)

    plan = [CompilerRequest(hop.request_id, layer_index, order, hop.qubit, hop.source_core, hop.destination_core)
            for layer_index, layer in enumerate(layers) for order, hop in enumerate(layer)]
    recorder = ListRecorder()
    with tempfile.TemporaryDirectory(prefix="ace-harness-") as tmp:
        config = _config_without_speculation(Path(tmp))
        with contextlib.redirect_stdout(io.StringIO()):
            result = run_parallel_experiment(
                str(config), False, False, layered, 5.3, request_duration_ms, "harness", seed=seed,
                compiler_spec=None, total_memories_per_core=memories, simulation_stop_time_s=stop_time_s,
                serialize_conflicts=serialize, recorder=recorder, scheduler=scheduler, request_plan=plan)
    stats = result["stats"]
    violations = check_events(recorder.events, info, require_completion=True,
                              submission_after_predecessor=submission_after_predecessor)
    return Outcome(
        requested=len(info),
        completed=stats["completed_requests"],
        total_retries=stats.get("total_retries", 0),
        retry_layers=stats["retry_layers"],
        makespan_ms=stats["end_to_end_latency_ms"],
        latencies_ms=dict(stats["individual_latencies"]),
        events=recorder.events,
        violations=violations,
    )
