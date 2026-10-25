"""Static core load of a routed trace (no simulation).

Demand follows tools/routing_research and tools/experiment2: for one layer, a core's demand D is the number of hop touches it receives --
a migration's two end cores are touched once, every relay core twice (the qubit arrives and leaves).  Excess at capacity C is
sum over (layer, core) of max(0, D - C).  C = 4 is the group's communication-qubit count; the others show how the picture changes with it.

    PYTHONPATH=mapper:. python -m tools.mapper_ace.route_load LABEL=requests.txt [LABEL=requests.txt ...] --out load.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from .adapter import import_legacy_request_file
from .placement_contract import build_architecture

CAPACITIES = (2, 3, 4, 6, 8)


def gini(values: list[float]) -> float:
    x = np.sort(np.asarray(values, dtype=float))
    if x.sum() == 0:
        return 0.0
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1) @ x / (n * x.sum()))


def analyse(path: Path, dimensions=(4, 4), qubits_per_core=8, seed=42) -> dict:
    architecture = build_architecture(dimensions, qubits_per_core, seed, 0.1)
    _, records = import_legacy_request_file(path, architecture)
    n_cores = architecture.n_cores
    demand: dict[tuple[int, int], int] = defaultdict(int)          # (layer, core) -> hop touches
    endpoint, relay = Counter(), Counter()
    for record in records:
        cores = record.path
        for index, core in enumerate(cores):
            if index in (0, len(cores) - 1):
                demand[(record.layer, core)] += 1
                endpoint[core] += 1
            else:
                demand[(record.layer, core)] += 2
                relay[core] += 2
    totals = [endpoint[c] + relay[c] for c in range(n_cores)]
    out = {"migrations": len(records), "hops": sum(r.path_hops for r in records),
           "relay_touches_by_core": [relay[c] for c in range(n_cores)],
           "endpoint_touches_by_core": [endpoint[c] for c in range(n_cores)],
           "gini_total_load": gini(totals), "gini_relay_load": gini([relay[c] for c in range(n_cores)]),
           "max_relay_core": int(max(range(n_cores), key=lambda c: relay[c])),
           "max_relay_touches": int(max(relay.values(), default=0)),
           "peak_layer_core_demand": int(max(demand.values(), default=0))}
    for capacity in CAPACITIES:
        excess_by_core = Counter()
        overloaded = 0
        for (layer, core), value in demand.items():
            if value > capacity:
                excess_by_core[core] += value - capacity
                overloaded += 1
        total = sum(excess_by_core.values())
        out[f"excess_C{capacity}"] = total
        out[f"overloaded_core_layers_C{capacity}"] = overloaded
        out[f"top3_core_share_of_excess_C{capacity}"] = (sum(v for _, v in excess_by_core.most_common(3)) / total) if total else 0.0
        out[f"excess_by_core_C{capacity}"] = [excess_by_core[c] for c in range(n_cores)]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("traces", nargs="+", help="LABEL=path")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dimensions", type=int, nargs=2, default=(4, 4))
    args = parser.parse_args()
    report = {}
    for item in args.traces:
        label, path = item.split("=", 1)
        report[label] = analyse(Path(path), tuple(args.dimensions))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    header = f"{'arm':22s} {'hops':>5s} {'relay gini':>10s} {'busiest relay':>14s} " + " ".join(f"{'exc C=' + str(c):>8s}" for c in CAPACITIES) + f" {'overl.C4':>8s} {'top3 share C4':>13s}"
    print(header)
    for label, r in report.items():
        print(f"{label:22s} {r['hops']:5d} {r['gini_relay_load']:10.3f} {'core %d (%d)' % (r['max_relay_core'], r['max_relay_touches']):>14s} "
              + " ".join(f"{r['excess_C%d' % c]:8d}" for c in CAPACITIES) + f" {r['overloaded_core_layers_C4']:8d} {r['top3_core_share_of_excess_C4']:13.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
