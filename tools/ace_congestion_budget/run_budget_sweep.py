"""ACE congestion budget sweep.

Case 1: 2, 3 or 4 communication memories per core -> congestion present.
Case 2: 32 per core -> congestion structurally impossible, since the peak
core-layer demand over these workloads is 24. A 64-memory arm on QFT confirms
32 already saturates.

Design and caveats: docs/plans/ace-congestion-budget-study.md
Column meanings:    docs/reference/metrics-glossary.md
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

SCRATCH = Path("/private/tmp/claude-501/-Users-dhruvrpansuriya-Documents-IITG-Acad-Sem-7-BTP/e28b2ce3-a808-45df-b069-3699d0957705/scratchpad")
ACE = SCRATCH / "wt-congestion"
RUNNER = ACE / "run_trace_comparison.py"
MQT = SCRATCH / "mqt_zip" / "mqt_ten_workload_study"
PY = Path("/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP/Compiler-Driven-ACE/.venv/bin/python")

OUT = SCRATCH / "ace_budget"
RUNS = OUT / "runs"
RESULTS = OUT / "results.csv"

CONGESTED = ["qft", "qaoa", "draper_qft_adder", "graphstate"]
CONTROL = ["ghz"]
MAPPING_SEEDS = [42, 43, 44]
BUDGETS = [2, 3, 4, 32]
SATURATION = {"qft": 64}
STRATEGIES = ["on-demand", "dynamic"]
PHYSICS_SEEDS = "0,1,2"

CONTEXT = ["workload", "congested", "mapping_seed", "total_memories",
           "compiler_memories", "demand_bank", "trace_sha256", "run_status"]


def compiler_memories(strategy: str, budget: int) -> int:
    """Compiler slots to request, holding one slot back for demand.

    At a budget of four this reproduces the project's established 3+1 split,
    so the standard configuration stays a point on the curve.

    The value passed for ``on-demand`` is a planner argument only, and the
    planner rejects zero before returning an empty schedule for this strategy.
    The runtime cap is forced to zero for on-demand inside ``_compiler_spec``
    regardless of what is passed here, so on-demand always has its whole bank
    serving demand. Verified: on-demand results are byte-identical whether 1 or
    3 is passed.
    """
    return max(1, budget - 1)


def runtime_compiler_cap(strategy: str, budget: int) -> int:
    """The cap the simulator actually applies, for provenance in the output."""
    return 0 if strategy == "on-demand" else compiler_memories(strategy, budget)


def run_one(workload: str, mseed: int, budget: int, strategy: str) -> list[dict]:
    trace = MQT / workload / f"seed_{mseed}" / "requests.txt"
    comp = compiler_memories(strategy, budget)
    cap = runtime_compiler_cap(strategy, budget)
    tag = f"{workload}_m{mseed}_c{budget}_{strategy}"
    outdir = RUNS / tag
    base = {
        "workload": workload,
        "congested": workload in CONGESTED,
        "mapping_seed": mseed,
        "total_memories": budget,
        "compiler_memories": cap,
        "demand_bank": budget - cap,
        "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
    }
    cmd = [
        str(PY), "-B", str(RUNNER),
        "--trace", str(trace),
        "--mesh", "4x4",
        "--strategies", strategy,
        "--seeds", PHYSICS_SEEDS,
        "--total-memories", str(budget),
        "--compiler-memories", str(comp),
        # Generation capacity is a SECOND per-core, per-layer cap, independent of
        # memory, and it also gates the planner.  Leaving it pinned at 3 while the
        # memory budget grows means the unlimited case is not unlimited: QFT tops
        # out at 97.8% and QAOA at 93.1% of requests schedulable, held back by
        # generation rather than by memory.  Scaling it with the budget lets every
        # workload reach 100% at c=32, and at c=4 it is 3 -- the project default.
        "--generation-capacity", str(comp),
        "--delta-layers", "6",
        "--dynamic-lookahead-layers", "8",
        "--coherence-time-layers", "10",
        "--compiler-reservation-ms", "1000",
        "--stop-time-s", "300",
        "--output", str(outdir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ACE), timeout=7200)
    if proc.returncode != 0:
        tail = (proc.stderr.strip().splitlines() or ["?"])[-1][:200]
        return [dict(base, run_status="FAILED: " + tail)]

    meta = json.loads((outdir / "metadata.json").read_text(encoding="utf-8"))
    # The run must have used the budget we asked for, or the row is meaningless.
    # Record the mismatch rather than raising: one bad row should not discard a
    # long sweep, and a row marked CONFIG-MISMATCH is excluded from the results.
    got_total = meta["parameters"]["total_memories"]
    got_comp = meta["parameters"]["compiler_memories"]
    if got_total != budget or got_comp != comp:
        return [dict(base, run_status=(
            f"CONFIG-MISMATCH: asked total={budget} compiler={comp}, "
            f"ran total={got_total} compiler={got_comp}"))]

    rows = []
    for r in csv.DictReader((outdir / "summary.csv").open(encoding="utf-8")):
        row = dict(base, run_status="ok", **r)
        # fallback to on-demand is normal recovery; a dropped request is not
        if float(row.get("completion_rate", 0)) != 1.0:
            row["run_status"] = f"INCOMPLETE: completion_rate={row.get('completion_rate')}"
        rows.append(row)
    return rows


def main() -> int:
    RUNS.mkdir(parents=True, exist_ok=True)
    jobs = []
    for workload in CONGESTED + CONTROL:
        budgets = list(BUDGETS) + ([SATURATION[workload]] if workload in SATURATION else [])
        for mseed in MAPPING_SEEDS:
            for budget in budgets:
                for strategy in STRATEGIES:
                    jobs.append((workload, mseed, budget, strategy))

    print(f"{len(jobs)} invocations ({len(jobs) * 3} runs) queued", flush=True)
    rows: list[dict] = []
    fields: list[str] = []
    started = time.time()
    for index, job in enumerate(jobs, 1):
        t0 = time.time()
        try:
            new = run_one(*job)
        except subprocess.TimeoutExpired:
            new = [{"workload": job[0], "mapping_seed": job[1], "total_memories": job[2],
                    "run_status": "TIMEOUT"}]
        rows.extend(new)
        for row in new:
            for key in row:
                if key not in fields:
                    fields.append(key)
        ordered = CONTEXT + [f for f in fields if f not in CONTEXT]
        with RESULTS.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ordered)
            writer.writeheader()
            for item in rows:
                writer.writerow({k: item.get(k) for k in ordered})
        print(f"[{index}/{len(jobs)}] {job} -> {new[0].get('run_status')} "
              f"({time.time() - t0:.0f}s, total {(time.time() - started) / 60:.1f}m)",
              flush=True)

    bad = [r for r in rows if r.get("run_status") != "ok"]
    print(f"done in {(time.time() - started) / 60:.1f}m. {len(rows) - len(bad)} rows ok, {len(bad)} failed")
    for r in bad:
        print("  FAIL", r.get("workload"), r.get("mapping_seed"), r.get("total_memories"), r.get("run_status"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
