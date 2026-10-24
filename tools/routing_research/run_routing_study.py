#!/usr/bin/env python3
"""Offline re-routing study over the ten archived benchmarks (mesh) or any directory of requests.txt traces.

For every workload, mapping seed, capacity, counting variant and detour allowance it records the demand above capacity
("excess") under the mapper's own routing, under the optimal re-routing, and the two proven lower bounds.

    python tools/routing_research/run_routing_study.py --output results/<dir> --jobs 4
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import offline_routing as ro                                                  # noqa: E402
from hotspot_analysis import read_trace                                       # noqa: E402

ARCHIVE = REPO / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
PREFIX = "mqt_ten_workload_study"
WORKLOADS = ["ghz", "bv", "bmw_quark_cardinality", "vqe_real_amp", "cdkm_ripple_carry_adder", "graphstate",
             "draper_qft_adder", "qaoa", "qft", "randomcircuit"]
SEEDS = (42, 43, 44)
CAPACITIES = (1, 2, 3, 4)
VARIANTS = ("hop", "route")
EXTRAS = (0, 2)
FIELDS = ["workload", "mapping_seed", "topology", "capacity", "variant", "extra_hops", "active_layers", "total_hops",
          "baseline_overloaded_layers", "optimised_overloaded_layers", "baseline_excess", "optimised_excess",
          "endpoint_lower_bound", "volume_lower_bound", "best_lower_bound", "added_hops", "layers_not_proved_optimal", "seconds"]


def study_trace(args) -> list[dict]:
    path, workload, seed, topology = args
    trace = read_trace(Path(path), 4, 4, topology)
    adj = ro.adjacency(topology)
    routes = ro.layer_routes(trace)
    rows = []
    for capacity in CAPACITIES:
        for variant in VARIANTS:
            for extra in EXTRAS:
                t0 = time.time()
                base_x = opt_x = lb_end = lb_vol = lb_best = added = over_b = over_o = unproved = 0
                for layer, paths in routes.items():
                    res = ro.optimize_layer(paths, capacity, variant, adj, extra)
                    base_x += res.baseline_excess
                    opt_x += res.excess
                    e, v = ro.lower_bound(paths, capacity, variant), ro.volume_bound(paths, capacity, variant, adj)
                    lb_end += e
                    lb_vol += v
                    lb_best += max(e, v)
                    over_b += res.baseline_excess > 0
                    over_o += res.excess > 0
                    added += sum(len(p) - 1 for p in res.paths) - sum(len(p) - 1 for p in paths)
                    unproved += not res.optimal
                rows.append({"workload": workload, "mapping_seed": seed, "topology": topology, "capacity": capacity,
                             "variant": variant, "extra_hops": extra, "active_layers": len(routes),
                             "total_hops": len(trace.hops), "baseline_overloaded_layers": over_b,
                             "optimised_overloaded_layers": over_o, "baseline_excess": base_x, "optimised_excess": opt_x,
                             "endpoint_lower_bound": lb_end, "volume_lower_bound": lb_vol, "best_lower_bound": lb_best,
                             "added_hops": added, "layers_not_proved_optimal": unproved,
                             "seconds": f"{time.time() - t0:.2f}"})
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--workloads", nargs="+", default=WORKLOADS, choices=WORKLOADS)
    parser.add_argument("--traces-dir", type=Path, default=None,
                        help="directory <workload>/seed_<n>/requests.txt (default: the committed mesh archive)")
    parser.add_argument("--topology", choices=("mesh", "torus"), default="mesh")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        if args.traces_dir is None:
            with zipfile.ZipFile(ARCHIVE) as archive:
                for w in args.workloads:
                    for s in SEEDS:
                        archive.extract(f"{PREFIX}/{w}/seed_{s}/requests.txt", tmp)
            base = Path(tmp) / PREFIX
        else:
            base = args.traces_dir
        tasks = [(str(base / w / f"seed_{s}" / "requests.txt"), w, s, args.topology) for w in args.workloads for s in SEEDS]
        tasks.sort(key=lambda t: -(t[1] == "randomcircuit"))
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            rows = [row for part in pool.map(study_trace, tasks) for row in part]
    rows.sort(key=lambda r: (WORKLOADS.index(r["workload"]), r["mapping_seed"], r["capacity"], r["variant"], r["extra_hops"]))
    with (args.output / "offline_routing.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} rows in {time.time() - started:.0f} s -> {args.output / 'offline_routing.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
