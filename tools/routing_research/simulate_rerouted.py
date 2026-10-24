#!/usr/bin/env python3
"""Does offline re-routing reduce latency in the simulator, not just structurally?

For each workload, mapping seed and memory budget b, re-route every layer's routes to minimise the demand above capacity b (route
counting, which is what the per-qubit scheduler experiences: a relay needs one memory at a time), with either shortest paths only
(``extra`` 0) or up to two extra hops, write the new trace, and simulate it on-demand in ACE with b communication memories next to
the original routes.  The mapping, every request's endpoints, the physics seeds and every parameter are identical in the two arms.

    python tools/routing_research/simulate_rerouted.py --output results/<dir> --jobs 4
"""
from __future__ import annotations

import argparse
import csv
import statistics as st
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "tools" / "ace_budget_rerun"))
import offline_routing as ro                                                  # noqa: E402
import run_budget_sweep as sweep                                              # noqa: E402
from hotspot_analysis import read_trace                                       # noqa: E402

WORKLOADS = ["graphstate", "draper_qft_adder", "qaoa", "qft", "randomcircuit"]
SEEDS = (42, 43, 44)
BUDGETS = (2, 3, 4)
EXTRAS = (0, 2)


def build_one(task):
    workload, seed, budget, extra, original, out_dir, topology = task
    trace = read_trace(Path(original), 4, 4, topology)
    adj = ro.adjacency(topology)
    routes, results = ro.reroute_trace(trace, budget, "route", adj, extra)
    label = f"{workload}__c{budget}_e{extra}"
    path = Path(out_dir) / label / f"seed_{seed}" / "requests.txt"
    ro.write_trace(trace, routes, ro.route_qubits(trace), path)
    new = read_trace(path, 4, 4, topology)                                     # validates adjacency and per-qubit placement
    return {"label": label, "workload": workload, "mapping_seed": seed, "budget": budget, "extra": extra,
            "hops_before": len(trace.hops), "hops_after": len(new.hops),
            "excess_before": sum(r.baseline_excess for r in results.values()),
            "excess_after": sum(r.excess for r in results.values())}


def simulate(args):
    job, traces, output, config, flags = args
    return sweep.run_one(job, traces, output, "per-qubit", config, False, flags)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--workloads", nargs="+", default=WORKLOADS)
    parser.add_argument("--topology", choices=("mesh", "torus"), default="mesh")
    parser.add_argument("--traces-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    config = REPO / "config" / "final_config" / ("grid_4x4_torus_ace_3.json" if args.topology == "torus" else "grid_4x4_ace_3.json")
    flags = ["--topology", args.topology]
    with tempfile.TemporaryDirectory() as tmp:
        if args.traces_dir is None:
            with zipfile.ZipFile(sweep.ARCHIVE) as archive:
                for w in args.workloads:
                    for s in SEEDS:
                        archive.extract(f"{sweep.PREFIX}/{w}/seed_{s}/requests.txt", tmp)
            originals = Path(tmp) / sweep.PREFIX
        else:
            originals = args.traces_dir
        rerouted = args.output / "rerouted_traces"
        tasks = [(w, s, b, e, str(originals / w / f"seed_{s}" / "requests.txt"), str(rerouted), args.topology)
                 for w in args.workloads for s in SEEDS for b in BUDGETS for e in EXTRAS]
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            built = list(pool.map(build_one, tasks))
        # jobs: the rerouted traces and the original routes, on-demand, at the budget they were optimised for
        jobs = [((b["label"], b["mapping_seed"], b["budget"], "on-demand"), rerouted, args.output / "sim", config, flags) for b in built]
        jobs += [((w, s, b, "on-demand"), originals, args.output / "sim", config, flags)
                 for w in args.workloads for s in SEEDS for b in BUDGETS]
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            sims = list(pool.map(simulate, jobs))
    rows = []
    for result in sims:
        for r in result:
            rows.append({"label": r["workload"], "mapping_seed": r["mapping_seed"], "budget": r["total_memories"], "seed": r["seed"],
                         "status": r["run_status"], "latency_ms": r["average_eligible_latency_ms"], "makespan_ms": r["end_to_end_latency_ms"],
                         "waited_fraction": r["requests_that_waited_fraction"], "avg_admission_wait_ms": r["average_admission_wait_ms"],
                         "max_admission_wait_ms": r["max_admission_wait_ms"], "completion_rate": r["completion_rate"],
                         "fidelity": r["average_delivered_epr_fidelity"], "invocation_wall_seconds": r.get("invocation_wall_seconds", "")})
    with (args.output / "simulated.csv").open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (args.output / "rerouted_traces.csv").open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=list(built[0]))
        w.writeheader()
        w.writerows(built)
    bad = [r for r in rows if r["status"] != "ok"]
    print(f"{len(built)} rerouted traces, {len(rows)} simulated runs ({len(bad)} not ok) in {time.time() - started:.0f} s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
