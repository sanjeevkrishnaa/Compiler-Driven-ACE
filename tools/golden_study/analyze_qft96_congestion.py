#!/usr/bin/env python3
"""Generate QFT-96 congestion tables and per-route heatmaps.

The analysis is trace-only: it does not invent simulator occupancy or replace
the ACE timing results.  It measures compiler-layer demand from every
validated QFT-96 route trace.  ``hop`` counting counts two incidences for an
internal relay (arrival and departure); ``route`` counting counts one core
occupancy for a qubit route.  Endpoint demand and relay-only overload are
reported separately for both definitions.

Example::

    python -m tools.golden_study.analyze_qft96_congestion \
      --root results/qft96_2seed_2026-10-26 \
      --output results/qft96_2seed_2026-10-26/congestion \
      --capacities 2,3,4,6,8,16,32,64
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VARIANTS = ("hop", "route")
DEFAULT_CAPACITIES = (2, 3, 4, 6, 8, 16, 32, 64)


def parse_trace(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    """Parse a TraceGen file without enforcing mesh-only adjacency.

    The normal validator intentionally rejects torus wraparound edges.  This
    reader validates the trace structure and evolving qubit source positions,
    while allowing a torus edge such as 3 -> 0.
    """
    cores = slots = qubits = None
    placement: dict[int, int] = {}
    hops: list[tuple[int, int, int, int]] = []
    section = None
    layer = None
    last_layer = -1
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        low = line.lower()
        if not line or line.startswith("//"):
            if low == "// number of cores": section = "cores"; continue
            if low == "// number of qubit slots per core": section = "slots"; continue
            if low == "// number of qubits": section = "qubits"; continue
            if low.startswith("// initial placement"): section = "placement"; continue
            if low.startswith("// inter-core communication requests"): section = "hops"; continue
            if low.startswith("// layer"):
                layer = int(low.split()[-1]);
                if layer != last_layer + 1: raise ValueError(f"{path}:{lineno}: non-consecutive layer")
                last_layer = layer; section = "hops"; continue
            continue
        if section in {"cores", "slots", "qubits"}:
            value = int(line); 
            if section == "cores": cores = value
            elif section == "slots": slots = value
            else: qubits = value
            section = None
            continue
        if not (line.startswith("(") and line.endswith(")")):
            raise ValueError(f"{path}:{lineno}: malformed tuple")
        values = tuple(int(x.strip()) for x in line[1:-1].split(","))
        if section == "placement" and len(values) == 2:
            q, core = values
            if q in placement: raise ValueError(f"{path}:{lineno}: duplicate placement")
            placement[q] = core
        elif section == "hops" and len(values) == 3 and layer is not None:
            q, source, target = values
            if placement.get(q) != source:
                raise ValueError(f"{path}:{lineno}: qubit {q} source {source} != {placement.get(q)}")
            hops.append((layer, q, source, target)); placement[q] = target
        else:
            raise ValueError(f"{path}:{lineno}: tuple in wrong section")
    if None in (cores, slots, qubits) or len(placement) != qubits:
        raise ValueError(f"{path}: incomplete metadata or placement")
    return int(cores), last_layer + 1, hops


def routes_by_layer(hops: list[tuple[int, int, int, int]]) -> dict[int, list[list[int]]]:
    layers: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for layer, q, source, target in hops:
        layers[layer].append((q, source, target))
    result: dict[int, list[list[int]]] = {}
    for layer, entries in layers.items():
        routes: list[tuple[int, list[int]]] = []
        for q, source, target in entries:
            if routes and routes[-1][0] == q and routes[-1][1][-1] == source:
                routes[-1][1].append(target)
            else:
                routes.append((q, [source, target]))
        result[layer] = [path for _, path in routes]
    return result


def demand_for_layer(paths: list[list[int]], variant: str) -> tuple[Counter, Counter]:
    demand, endpoint = Counter(), Counter()
    for path in paths:
        last = len(path) - 1
        if variant == "hop":
            for index, core in enumerate(path):
                if index in (0, last):
                    demand[core] += 1; endpoint[core] += 1
                else:
                    demand[core] += 2
        elif variant == "route":
            for core in set(path):
                demand[core] += 1
                if core in (path[0], path[-1]): endpoint[core] += 1
        else:
            raise ValueError(variant)
    return demand, endpoint


def analyse(alias: dict[str, Any], root: Path, capacities: tuple[int, ...]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trace = root / alias["trace_path"]
    cores, layers, hops = parse_trace(trace)
    by_layer = routes_by_layer(hops)
    active = len(by_layer)
    summary: list[dict[str, Any]] = []
    core_rows: list[dict[str, Any]] = []
    for variant in VARIANTS:
        layer_demands = {layer: demand_for_layer(paths, variant) for layer, paths in by_layer.items()}
        for capacity in capacities:
            overloaded_layers = overloaded_core_layers = excess = 0
            for demand, _ in layer_demands.values():
                hot = [c for c, value in demand.items() if value > capacity]
                overloaded_layers += bool(hot); overloaded_core_layers += len(hot)
                excess += sum(max(0, value - capacity) for value in demand.values())
            summary.append({**alias, "variant": variant, "capacity": capacity, "layers": layers,
                            "active_layers": active, "physical_hops": len(hops),
                            "overloaded_layers": overloaded_layers,
                            "overloaded_layer_percent": 100 * overloaded_layers / active if active else 0,
                            "overloaded_core_layers": overloaded_core_layers,
                            "excess_demand": excess})
            for core in range(cores):
                demand_values = [d.get(core, 0) for d, _ in layer_demands.values()]
                endpoint_values = [e.get(core, 0) for _, e in layer_demands.values()]
                over = sum(value > capacity for value in demand_values)
                own = sum(value > capacity for value in endpoint_values)
                relay_only = sum(e <= capacity < d for d, e in zip(demand_values, endpoint_values))
                relay_incidences = sum(d - e for d, e in zip(demand_values, endpoint_values))
                excess_core = sum(max(0, d - capacity) for d in demand_values)
                relay_excess = sum(max(0, d - capacity) - max(0, e - capacity) for d, e in zip(demand_values, endpoint_values))
                core_rows.append({**alias, "variant": variant, "capacity": capacity, "core": core,
                                  "row": core // 4, "column": core % 4, "active_layers": active,
                                  "incident_demand": sum(demand_values), "endpoint_demand": sum(endpoint_values),
                                  "relay_incidences": relay_incidences, "peak_demand": max(demand_values, default=0),
                                  "overloaded_percent": 100 * over / active if active else 0,
                                  "own_percent": 100 * own / active if active else 0,
                                  "relay_only_percent": 100 * relay_only / active if active else 0,
                                  "relay_share_of_excess": relay_excess / excess_core if excess_core else 0})
    return summary, core_rows


def heatmaps(rows: list[dict[str, Any]], output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for key in sorted({(r["topology"], r["route_policy"], r["mapping_seed"], r["capacity"], r["variant"]) for r in rows}):
        topology, route, seed, capacity, variant = key
        subset = [r for r in rows if (r["topology"], r["route_policy"], r["mapping_seed"], r["capacity"], r["variant"]) == key]
        fields = [("overloaded_percent", "Total overload"), ("own_percent", "Source/destination"), ("relay_only_percent", "Relay-only")]
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), constrained_layout=True)
        for ax, (field, title) in zip(axes, fields):
            lookup = {int(r["core"]): float(r[field]) for r in subset}
            grid = [[lookup[row * 4 + col] for col in range(4)] for row in range(4)]
            im = ax.imshow(grid, cmap="YlOrRd", vmin=0, vmax=100)
            ax.set_title(title); ax.set_xticks(range(4)); ax.set_yticks(range(4))
            for row in range(4):
                for col in range(4):
                    value = grid[row][col]
                    ax.text(col, row, f"C{row*4+col}\n{value:.1f}%", ha="center", va="center", fontsize=7,
                            color="white" if value > 60 else "black")
        fig.colorbar(im, ax=axes, label="% of communication-active layers")
        fig.suptitle(f"QFT-96 {topology} / {route} / mapping {seed} / capacity {capacity} / {variant}")
        name = f"{topology}__{route}__seed{seed}__cap{capacity}__{variant}.png"
        fig.savefig(output / name, dpi=160, bbox_inches="tight")
        plt.close(fig)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows: return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capacities", default=','.join(map(str, DEFAULT_CAPACITIES)))
    args = parser.parse_args()
    capacities = tuple(int(x) for x in args.capacities.split(","))
    audit = list(csv.DictReader((args.root / "validation/mapping_audit.csv").open(newline="", encoding="utf-8")))
    aliases, seen = [], set()
    for row in audit:
        key = (row["topology"], row["mapping_algorithm"], row["workload"], int(row["mapping_seed"]), row["route_policy"])
        if key in seen: continue
        seen.add(key)
        aliases.append({"topology": row["topology"], "mapping_algorithm": row["mapping_algorithm"],
                        "workload": row["workload"], "mapping_seed": int(row["mapping_seed"]),
                        "route_policy": row["route_policy"], "trace_path": str(Path("traces/placements") / row["topology"] /
                        row["mapping_algorithm"] / row["workload"] / f"seed_{row['mapping_seed']}" / "routes" /
                        row["route_policy"] / "requests.txt"), "trace_sha256": row["request_trace_sha256"]})
    all_summary, all_core = [], []
    for alias in aliases:
        summary, core = analyse(alias, args.root, capacities)
        all_summary.extend(summary); all_core.extend(core)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "trace_congestion_summary.csv", all_summary)
    write_csv(args.output / "per_core_congestion.csv", all_core)
    heatmaps(all_core, args.output / "heatmaps") if (args.output / "heatmaps").mkdir(exist_ok=True) is None else None
    manifest = {"schema": "qft96-congestion-v1", "capacities": capacities, "variants": VARIANTS,
                "trace_count": len(aliases), "summary_rows": len(all_summary), "core_rows": len(all_core),
                "definitions": {"hop": "internal relay contributes two incident demands; endpoints one",
                                "route": "each core visited by a qubit route contributes one demand",
                                "relay_only": "total demand exceeds capacity while endpoint demand does not"}}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
