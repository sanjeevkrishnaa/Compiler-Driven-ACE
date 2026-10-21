"""Validate TraceGen hop traces and summarize per-layer communication hotspots.

Usage:
    python analyze_trace_hotspots.py --output hotspot_summary.json TRACE [TRACE ...]

Each hop contributes one communication-memory demand at its source and one at
its destination. These are compiler-layer demand counts, not measured
simultaneous physical occupancy.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re


LAYER = re.compile(r"^//\s*Layer\s+(\d+)\s*$", re.IGNORECASE)
TUPLE = re.compile(r"^\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)$")
CAPACITIES = (1, 2, 3, 4, 6, 8)


def parse_trace(path: Path) -> dict:
    metadata = {}
    placement = {}
    hops = []
    section = None
    pending = None
    layer = None
    last_layer = -1
    markers = {
        "// number of cores": "cores",
        "// number of qubit slots per core": "slots",
        "// number of qubits": "qubits",
    }
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in markers:
            pending = markers[lowered]
            continue
        if lowered.startswith("// initial placement"):
            section = "placement"
            continue
        if lowered.startswith("// inter-core communication requests"):
            section = "hops"
            continue
        match = LAYER.match(line)
        if match:
            layer = int(match.group(1))
            if layer != last_layer + 1:
                raise ValueError(f"{path}:{line_number}: layer markers must be consecutive")
            last_layer = layer
            section = "hops"
            continue
        if line.startswith("//"):
            continue
        if pending is not None:
            metadata[pending] = int(line)
            pending = None
            continue
        match = TUPLE.match(line)
        if match is None:
            raise ValueError(f"{path}:{line_number}: malformed tuple")
        values = tuple(int(part.strip()) for part in match.group(1).split(","))
        if section == "placement" and len(values) == 2:
            qubit, core = values
            if qubit in placement:
                raise ValueError(f"{path}:{line_number}: duplicate qubit placement")
            placement[qubit] = core
        elif section == "hops" and layer is not None and len(values) == 3:
            hops.append((layer, *values))
        else:
            raise ValueError(f"{path}:{line_number}: tuple in wrong section")

    cores, slots, qubits = (metadata[key] for key in ("cores", "slots", "qubits"))
    if cores != 16:
        raise ValueError(f"{path}: expected 16 cores on a 4x4 mesh")
    if set(placement) != set(range(qubits)):
        raise ValueError(f"{path}: incomplete initial placement")
    occupancy = Counter(placement.values())
    if any(core not in range(cores) for core in placement.values()):
        raise ValueError(f"{path}: invalid initial core")
    if any(count > slots for count in occupancy.values()):
        raise ValueError(f"{path}: initial core exceeds slot capacity")
    evolving = dict(placement)
    for index, (hop_layer, qubit, source, target) in enumerate(hops):
        if qubit not in evolving or evolving[qubit] != source:
            raise ValueError(f"{path}: hop {index} violates evolving placement")
        if source not in range(cores) or target not in range(cores):
            raise ValueError(f"{path}: hop {index} uses invalid core")
        sr, sc = divmod(source, 4)
        tr, tc = divmod(target, 4)
        if abs(sr - tr) + abs(sc - tc) != 1:
            raise ValueError(f"{path}: hop {index} is not adjacent on the mesh")
        evolving[qubit] = target
    return {
        "path": str(path.resolve()),
        "cores": cores,
        "slots_per_core": slots,
        "qubits": qubits,
        "layers": last_layer + 1,
        "placement": placement,
        "initial_occupancy": occupancy,
        "hops": hops,
    }


def summarize(trace: dict) -> dict:
    by_layer = defaultdict(list)
    core_incidence = Counter()
    for layer, qubit, source, target in trace["hops"]:
        by_layer[layer].append((qubit, source, target))
        core_incidence[source] += 1
        core_incidence[target] += 1

    capacity_stats = {
        capacity: dict(overloaded_layers=0, overloaded_core_layers=0,
                       excess_incidences=0, affected_hops=0)
        for capacity in CAPACITIES
    }
    peak_by_core = Counter()
    overloaded_3_by_core = Counter()
    layer_details = []
    migrations = 0
    multi_hop_migrations = 0
    endpoint_necessary_3 = 0
    for layer, hops in by_layer.items():
        degree = Counter()
        for _, source, target in hops:
            degree[source] += 1
            degree[target] += 1
        for core, count in degree.items():
            peak_by_core[core] = max(peak_by_core[core], count)
            overloaded_3_by_core[core] += count > 3

        # TraceGen emits the route of each migration contiguously. Joining
        # consecutive hops of the same qubit exposes fixed endpoint demand.
        paths = []
        current = None
        for qubit, source, target in hops:
            if current is not None and current[0] == qubit and current[1][-1] == source:
                current[1].append(target)
            else:
                if current is not None:
                    paths.append(current)
                current = (qubit, [source, target])
        if current is not None:
            paths.append(current)
        migrations += len(paths)
        multi_hop_migrations += sum(len(path) > 2 for _, path in paths)
        endpoints = Counter()
        for _, path in paths:
            endpoints[path[0]] += 1
            endpoints[path[-1]] += 1
        if max(degree.values(), default=0) > 3 and max(endpoints.values(), default=0) > 3:
            endpoint_necessary_3 += 1

        for capacity, stats in capacity_stats.items():
            hot = {core for core, count in degree.items() if count > capacity}
            stats["overloaded_layers"] += bool(hot)
            stats["overloaded_core_layers"] += len(hot)
            stats["excess_incidences"] += sum(max(0, count - capacity) for count in degree.values())
            stats["affected_hops"] += sum(source in hot or target in hot for _, source, target in hops)
        layer_details.append({
            "layer": layer,
            "hop_requests": len(hops),
            "peak_demand": max(degree.values(), default=0),
            "overloaded_cores_at_3": {str(core): count for core, count in sorted(degree.items()) if count > 3},
            "peak_fixed_endpoint_demand": max(endpoints.values(), default=0),
        })

    cores = trace["cores"]
    return {
        "path": trace["path"],
        "core_count": cores,
        "qubit_count": trace["qubits"],
        "qubit_slots_per_core": trace["slots_per_core"],
        "layer_count": trace["layers"],
        "active_layers": len(by_layer),
        "hop_requests": len(trace["hops"]),
        "migrations": migrations,
        "multi_hop_migrations": multi_hop_migrations,
        "initial_occupancy": {str(core): trace["initial_occupancy"].get(core, 0) for core in range(cores)},
        "capacity_sensitivity": {str(cap): stats for cap, stats in capacity_stats.items()},
        "cores": [{
            "core": core,
            "incident_hops": core_incidence[core],
            "peak_layer_demand": peak_by_core[core],
            "overloaded_layers_at_3": overloaded_3_by_core[core],
        } for core in range(cores)],
        "hot_layers": sorted(layer_details, key=lambda row: (-row["peak_demand"], row["layer"]))[:12],
        "layers_unavoidable_from_fixed_endpoints_at_3": endpoint_necessary_3,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("traces", type=Path, nargs="+")
    args = parser.parse_args()
    summaries = [summarize(parse_trace(path)) for path in args.traces]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    for item in summaries:
        hot = item["capacity_sensitivity"]["3"]["overloaded_layers"]
        print(f"{Path(item['path']).name}: {item['qubit_count']} qubits, "
              f"{item['hop_requests']} hops, {hot}/{item['active_layers']} active layers over cap 3")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
