#!/usr/bin/env python3
"""Experiment 1: latency, fidelity and congestion of all ten benchmarks across communication-memory budgets.

Question: how much does communication-memory congestion cost each benchmark, and how does the number of memory
slots per core change it?  Everything runs on the corrected (per-qubit) scheduler; results of the legacy scheduler
are never mixed in (its serialization made the budget unable to bind).

* Workloads: the ten MQT circuits of the committed characterization, three mapping seeds each (42, 43, 44),
  three physics seeds (0, 1, 2).  Traces come from the archive, unmodified.
* Budgets (communication memories per core): 1, 2, 3, 4, 6, 8, 16, 32.  The ACGP paper's Table I gives four
  communication qubits per core, so 1 to 4 are modelled values and 6 to 32 are counterfactual (what-if capacity).
  QFT also runs 64: if it reproduces 32, 32 is saturated.
* Policies: on-demand (isolates contention: nothing is pre-generated) and dynamic compiler pre-generation, with
  one memory held back for demand (compiler memories = budget - 1), as in the budget study.  Dynamic needs at least
  two memories.
* Physical parameters are ACE's current ones, undecided (docs/reports/ace-physical-parameters.md).

    python tools/experiment1/run_experiment1.py --output results/<dir>
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools" / "ace_budget_rerun"))
import run_budget_sweep as sweep                                   # noqa: E402  (shared single-run machinery)

WORKLOADS = ["ghz", "bv", "graphstate", "vqe_real_amp", "cdkm_ripple_carry_adder", "bmw_quark_cardinality",
             "draper_qft_adder", "qft", "qaoa", "randomcircuit"]
MAPPING_SEEDS = [42, 43, 44]
BUDGETS = [1, 2, 3, 4, 6, 8, 16, 32]
MODELLED_MAX = 4                    # communication qubits per core in the ACGP paper's Table I
SATURATION = {"qft": 64}
POLICIES = ["on-demand", "dynamic"]
SCHEDULER = "per-qubit"


def enumerate_jobs(budgets_wanted=None, mapping_seeds=None) -> list[tuple[str, int, int, str]]:
    jobs = []
    for workload in WORKLOADS:
        budgets = BUDGETS + ([SATURATION[workload]] if workload in SATURATION else [])
        if budgets_wanted is not None:
            budgets = [b for b in budgets if b in budgets_wanted]
        for mapping_seed in (MAPPING_SEEDS if mapping_seeds is None else mapping_seeds):
            for budget in budgets:
                for policy in POLICIES:
                    if policy == "dynamic" and budget < 2:
                        continue                # a compiler bank needs a memory besides the one held for demand
                    jobs.append((workload, mapping_seed, budget, policy))
    return jobs


def extract_traces(directory: Path) -> Path:
    with zipfile.ZipFile(sweep.ARCHIVE) as archive:
        for workload in WORKLOADS:
            for mapping_seed in MAPPING_SEEDS:
                archive.extract(f"{sweep.PREFIX}/{workload}/seed_{mapping_seed}/requests.txt", directory)
    return directory / sweep.PREFIX


def label(row: dict) -> dict:
    budget = int(row["total_memories"])
    row["capacity_status"] = "modelled" if budget <= MODELLED_MAX else "counterfactual"
    row.pop("congested", None)          # the sweep driver's flag is specific to the budget study's workloads
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--only-workloads", nargs="+", default=None, choices=WORKLOADS)
    parser.add_argument("--budgets", nargs="+", type=int, default=None, help="restrict the memory budgets")
    parser.add_argument("--mapping-seeds", nargs="+", type=int, default=None, choices=MAPPING_SEEDS)
    parser.add_argument("--config", type=Path, default=None, help="topology/physics config (default: ACE's)")
    parser.add_argument("--parameter-set", default="ace-default", help="label recorded in every row")
    parser.add_argument("--resume", action="store_true", help="keep invocations already on disk")
    args = parser.parse_args(argv)

    jobs = [j for j in enumerate_jobs(args.budgets, args.mapping_seeds)
            if args.only_workloads is None or j[0] in args.only_workloads]
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    traces = extract_traces(args.output / "_traces")
    print(f"{len(jobs)} invocations ({3 * len(jobs)} runs), scheduler {SCHEDULER}", flush=True)

    def work(job):
        try:
            return job, [label(dict(r, parameter_set=args.parameter_set))
                         for r in sweep.run_one(job, traces, args.output, SCHEDULER, args.config, args.resume)]
        except subprocess.TimeoutExpired:
            return job, [label({"workload": job[0], "mapping_seed": job[1], "total_memories": job[2],
                                "run_status": "TIMEOUT"})]

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for done, (job, new) in enumerate(pool.map(work, jobs), 1):
            rows.extend(new)
            if done % 10 == 0 or new[0].get("run_status") != "ok":
                print(f"[{done}/{len(jobs)}] {job} -> {new[0].get('run_status')} ({(time.time() - started) / 60:.1f} min)", flush=True)
    sweep.write_results(args.output / "results.csv", rows)
    bad = [r for r in rows if r.get("run_status") != "ok"]
    print(f"done in {(time.time() - started) / 60:.1f} min: {len(rows) - len(bad)} rows ok, {len(bad)} not")
    for r in bad[:20]:
        print("  NOT OK", r.get("workload"), r.get("mapping_seed"), r.get("total_memories"), r.get("run_status"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
