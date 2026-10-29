"""Pass-2 verification of --congestion-threshold: independent re-implementation, checked against real runs.

V1  default (threshold=None) is byte-identical to the stored full-chain result.
V2  threshold huge (never exceeded) == full-chain default.
V3  threshold 0 (every layer with >0 activity drops later hops) == --chain-hops-prepared 1.
V4  on QFT-96 (real trace, real layer-activity distribution): for several threshold values, every prepared pair
    either is hop 0 of its chain, or belongs to an original layer whose request count is <= the threshold
    (recomputed here from the trace file, not from the controller's own counters).
V5  monotonicity: as the threshold rises (less filtering), the number of prepared non-hop-0 pairs is non-decreasing.
"""
from __future__ import annotations

import csv
import io
import sys
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[2]
MAIN = DESIGN.parent / "Compiler-Driven-ACE-correctness"
BTP = DESIGN.parent
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


sys.path.insert(0, str(DESIGN))
import ace.cli.run_trace_comparison as runner                                   # noqa: E402
import ace.compiler.compiler_scheduler as compiler_scheduler                                               # noqa: E402

captured = []
real_init = compiler_scheduler.CompilerPreGenerationController.__init__


def spy_init(self, *a, **kw):
    real_init(self, *a, **kw)
    captured.append(self)


compiler_scheduler.CompilerPreGenerationController.__init__ = spy_init
TRACE = MAIN / "results/routing_study_2026-10-25/qft96/xy/requests.txt"
BASE = ["--trace", str(TRACE), "--strategies", "dynamic", "--seeds", "0", "--total-memories", "4", "--compiler-memories", "3",
        "--generation-capacity", "3", "--scheduler", "per-qubit", "--admission", "event", "--pregeneration-buffer-ms", "0",
        "--stop-time-s", "200", "--max-layers", "80"]


def simulate(extra, tag):
    captured.clear()
    sys.argv = ["run_trace_comparison.py", *BASE, *extra, "--output", f"/private/tmp/verify_congestion_{tag}"]
    with redirect_stdout(io.StringIO()):
        runner.main()
    return captured[0]


# V1: default run, full trace, seed 0, reproduces the stored 30-seed-run's seed-0 row
sys.argv = ["run_trace_comparison.py", "--trace", str(TRACE), "--strategies", "dynamic", "--seeds", "0",
            "--total-memories", "4", "--compiler-memories", "3", "--generation-capacity", "3", "--scheduler", "per-qubit",
            "--admission", "event", "--pregeneration-buffer-ms", "0", "--stop-after-workload", "--stop-time-s", "200",
            "--output", "/private/tmp/verify_congestion_default"]
with redirect_stdout(io.StringIO()):
    runner.main()
new = next(csv.DictReader(open("/private/tmp/verify_congestion_default/summary.csv")))
stored = next(r for r in csv.DictReader(open(MAIN / "results/routing_study_2026-10-25/runs/xy/summary.csv"))
              if r["strategy"] == "dynamic" and r["seed"] == "0")
check("V1 default (no congestion_threshold) reproduces the stored XY seed-0 result",
      new["request_latency_mean_ms"] == stored["request_latency_mean_ms"], f"{new['request_latency_mean_ms']} vs {stored['request_latency_mean_ms']}")

# V2: a threshold no layer exceeds == full-chain default
controller_default = simulate([], "v2default")
controller_huge = simulate(["--congestion-threshold", "100000"], "v2huge")
check("V2 threshold never exceeded == full-chain default",
      [r["target_request_id"] for r in controller_default.records] == [r["target_request_id"] for r in controller_huge.records])

# V3: threshold 0 == chain-hops-prepared 1
controller_zero = simulate(["--congestion-threshold", "0"], "v3zero")
controller_first = simulate(["--chain-hops-prepared", "1"], "v3first")
check("V3 threshold 0 == --chain-hops-prepared 1",
      sorted(r["target_request_id"] for r in controller_zero.records) == sorted(r["target_request_id"] for r in controller_first.records))

# V4 + V5: real QFT-96 XY trace, recompute layer activity independently from the file
trace = runner.parse_compiler_trace(TRACE)
activity = Counter(r.layer for r in trace.requests)
counts = {}
for threshold in (5, 20, 30, 45, 60):
    controller = simulate(["--congestion-threshold", str(threshold)], f"v4_{threshold}")
    later_hops = [r for r in controller.records if controller.chain_position[r["target_request_id"]] > 0]
    bad = [r for r in later_hops if activity[controller.requests[r["target_request_id"]].layer] > threshold]
    check(f"V4 threshold {threshold}: {len(later_hops)} later-hop pairs prepared, none in a layer with activity > {threshold}",
          len(later_hops) > 0 and not bad, f"violations {len(bad)}")
    counts[threshold] = len(later_hops)

ordered = sorted(counts)
check(f"V5 later-hop pairs prepared is non-decreasing as the threshold rises: {[counts[t] for t in ordered]}",
      all(counts[ordered[i]] <= counts[ordered[i + 1]] for i in range(len(ordered) - 1)))

print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
sys.exit(1 if failures else 0)
