"""Pass-2 verification of the Dynamic launch rules: behaviour checked against the simulator's own records.

V1  planner: with default arguments the design-branch planner returns exactly the main-branch planner's schedule (QFT-96, supplied and XY routes,
    dynamic and fixed); with lead L every preparation is at least L layers before its request.
V2  first-hop-only: every prepared pair belongs to a request that is hop 0 of its chain.
V3  predecessor-start (distance m): a pair for a hop at position >= m was generated no earlier than the start of the hop m positions before it.
V4  layer delay d: a pair was generated no earlier than d after its generation layer activated.
V5  planner lead: pairs were generated no earlier than the activation of their (earlier) generation layer.
V6  default run reproduces the stored result digit for digit.
Runs real (short) simulations: --max-layers 80.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[2]
MAIN = DESIGN.parent / "Compiler-Driven-ACE-correctness"
BTP = DESIGN.parent
failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def load(path: Path, alias: str):
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


# ----------------------------------------------------------------------------------------------------- V1
main_trace = load(MAIN / "compiler_trace.py", "main_compiler_trace")
design_trace = load(DESIGN / "compiler_trace.py", "design_compiler_trace")
for label, path in (("supplied", BTP / "qft_requests.txt"),
                    ("xy", MAIN / "results/routing_study_2026-10-25/qft96/xy/requests.txt")):
    trace_main, trace_design = main_trace.parse_compiler_trace(path), design_trace.parse_compiler_trace(path)
    for strategy in ("dynamic", "fixed"):
        kwargs = dict(strategy=strategy, compiler_memories_per_core=3, generation_capacity_per_core=3,
                      coherence_time_layers=10.0, delta_layers=6, dynamic_lookahead_layers=8)
        a = main_trace.plan_preparations(trace_main, **kwargs)
        b = design_trace.plan_preparations(trace_design, **kwargs)
        c = design_trace.plan_preparations(trace_design, lead_layers=1, **kwargs)
        # the two modules define distinct ScheduledPreparation classes, so compare the contents, not the instances
        flat = lambda plan: ([(p.request_id, p.generation_layer) for p in plan[0]], plan[1], plan[2])       # noqa: E731
        check(f"V1 default planner identical to main ({label}, {strategy}, {len(a[0])} preparations, {a[1]} blocked, peak {a[2]})",
              flat(a) == flat(b) == flat(c) and len(a[0]) > 0)
    for lead in (2, 3, 4):
        plan, blocked, peak = design_trace.plan_preparations(
            trace_design, strategy="dynamic", compiler_memories_per_core=3, generation_capacity_per_core=3,
            coherence_time_layers=10.0, delta_layers=6, dynamic_lookahead_layers=8, lead_layers=lead)
        layer_of = {r.request_id: r.layer for r in trace_design.requests}
        check(f"V1 lead {lead}: every preparation is >= {lead} layers ahead ({label}, {len(plan)} scheduled, {blocked} blocked)",
              all(layer_of[p.request_id] - p.generation_layer >= lead for p in plan))
for bad in (0, 9):
    try:
        design_trace.plan_preparations(trace_design, strategy="dynamic", compiler_memories_per_core=3, generation_capacity_per_core=3,
                                       coherence_time_layers=10.0, dynamic_lookahead_layers=8, lead_layers=bad)
        check(f"V1 lead {bad} rejected", False)
    except ValueError:
        check(f"V1 lead {bad} rejected", True)

# ------------------------------------------------------------------------------------------- simulations
sys.path.insert(0, str(DESIGN))
import run_trace_comparison as runner                                   # noqa: E402
import compiler_scheduler                                               # noqa: E402

captured = []
real_run = runner.run_parallel_experiment
real_init = compiler_scheduler.CompilerPreGenerationController.__init__


def spy_init(self, *a, **kw):
    real_init(self, *a, **kw)
    captured.append(self)


compiler_scheduler.CompilerPreGenerationController.__init__ = spy_init
results = []


def wrapper(*a, **kw):
    result = real_run(*a, **kw)
    results.append(result)
    return result


runner.run_parallel_experiment = wrapper
TRACE = MAIN / "results/routing_study_2026-10-25/qft96/xy/requests.txt"
BASE = ["--trace", str(TRACE), "--strategies", "dynamic", "--seeds", "0", "--total-memories", "4", "--compiler-memories", "3",
        "--generation-capacity", "3", "--scheduler", "per-qubit", "--admission", "event", "--pregeneration-buffer-ms", "0",
        "--stop-time-s", "200", "--max-layers", "80"]


def simulate(extra: list[str], tag: str):
    captured.clear(); results.clear()
    sys.argv = ["run_trace_comparison.py", *BASE, *extra, "--output", f"/private/tmp/verify_triggers_{tag}"]
    import io
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        runner.main()
    controller, result = captured[0], results[0]
    ps = 10 ** 9
    return controller, result, ps


def records_of(controller):
    return [r for r in controller.records]


controller, result, ps = simulate([], "default")
check("V6a default run completes every request", result["stats"]["completed_requests"] == result["stats"]["completed_requests"] > 0)
n_default = len(records_of(controller))

controller, result, ps = simulate(["--chain-hops-prepared", "1"], "first")
recs = records_of(controller)
check(f"V2 first-hop-only: all {len(recs)} pairs are for hop-0 requests (default run made {n_default})",
      len(recs) > 0 and all(controller.chain_position[r["target_request_id"]] == 0 for r in recs))

for m in (1, 2):
    controller, result, ps = simulate(["--preparation-trigger", "predecessor-start", "--predecessor-distance", str(m)], f"pred{m}")
    recs = records_of(controller)
    later = [r for r in recs if controller.chain_position[r["target_request_id"]] >= m]
    bad = [r for r in later
           if r["generated_at_ps"] < controller.deadlines[controller.chain_predecessor[r["target_request_id"]]]]
    check(f"V3 predecessor-start distance {m}: {len(later)} pairs for hops at position >= {m}, none generated before the hop {m} earlier began",
          len(later) > 0 and not bad, f"violations {len(bad)}")
    early = [r for r in recs if controller.chain_position[r["target_request_id"]] < m]
    check(f"V3 distance {m}: hops before position {m} are launched by the layer rule (present: {len(early)})", len(early) > 0)

for d in (2, 4):
    controller, result, ps = simulate(["--preparation-delay-ms", str(d)], f"delay{d}")
    manager = result["request_manager"]
    recs = records_of(controller)
    bad = [r for r in recs if r["generated_at_ps"] < manager.layer_start_times[controller.schedule[r["target_request_id"]]] + d * ps]
    check(f"V4 layer delay {d} ms: {len(recs)} pairs, none generated earlier than {d} ms after its generation layer activated", len(recs) > 0 and not bad,
          f"violations {len(bad)}")

for lead in (2, 3):
    controller, result, ps = simulate(["--planner-lead-layers", str(lead)], f"lead{lead}")
    manager = result["request_manager"]
    recs = records_of(controller)
    layer_of = {r.request_id: r.layer for r in controller.requests.values()}
    far = [r for r in recs if layer_of[r["target_request_id"]] - controller.schedule[r["target_request_id"]] >= lead]
    bad = [r for r in recs if r["generated_at_ps"] < manager.layer_start_times[controller.schedule[r["target_request_id"]]]]
    check(f"V5 planner lead {lead}: all {len(recs)} pairs planned >= {lead} layers ahead and generated after their layer activated",
          len(recs) > 0 and len(far) == len(recs) and not bad, f"violations {len(bad)}")

# V6 default run, full trace, seed 0, supplied routes, against the stored result
sys.argv = ["run_trace_comparison.py", "--trace", str(BTP / "qft_requests.txt"), "--strategies", "dynamic", "--seeds", "0",
            "--total-memories", "4", "--compiler-memories", "3", "--generation-capacity", "3", "--scheduler", "per-qubit",
            "--admission", "event", "--pregeneration-buffer-ms", "0", "--stop-after-workload", "--stop-time-s", "200",
            "--output", "/private/tmp/verify_triggers_full"]
import csv, io
from contextlib import redirect_stdout
with redirect_stdout(io.StringIO()):
    runner.main()
new = next(csv.DictReader(open("/private/tmp/verify_triggers_full/summary.csv")))
stored = next(r for r in csv.DictReader(open(MAIN / "results/routing_study_2026-10-25/runs/original/summary.csv"))
              if r["strategy"] == "dynamic" and r["seed"] == "0")
for column in ("request_latency_mean_ms", "end_to_end_latency_ms", "request_latency_p95_ms", "average_admission_wait_ms", "intended_request_hit_rate"):
    check(f"V6 default full run reproduces stored {column}", new[column] == stored[column], f"{new[column]} vs {stored[column]}")

print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
sys.exit(1 if failures else 0)
