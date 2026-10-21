#!/usr/bin/env python3
"""Static endpoint and XY-route congestion audit for compiler traffic traces.

This tool intentionally does not simulate entanglement generation.  It answers
the prior question: given every request that becomes due in a compiler layer,
which endpoint memories and physical mesh links are simultaneously demanded?

Inputs may be the locked compiler text trace (``--trace``) or a fixed-mapping
traffic JSON produced by ``real_benchmarks/generate_fixed_mapping_traffic.py``
(``--traffic``).  Output is deterministic JSON, suitable for committing with
an experiment contract.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable

from compiler_trace import mesh_dimensions, parse_compiler_trace


ROUTER = re.compile(r"^router_(\d+)_(\d+)$")


@dataclass(frozen=True)
class Request:
    layer: int
    source: tuple[int, int]
    destination: tuple[int, int]


def xy_path(source: tuple[int, int], destination: tuple[int, int]) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Return undirected mesh links for horizontal-then-vertical XY routing."""
    x, y = source
    target_x, target_y = destination
    links = []
    while x != target_x:
        next_x = x + (1 if target_x > x else -1)
        links.append(tuple(sorted(((x, y), (next_x, y)))))
        x = next_x
    while y != target_y:
        next_y = y + (1 if target_y > y else -1)
        links.append(tuple(sorted(((x, y), (x, next_y)))))
        y = next_y
    return links


def parse_router(value: str) -> tuple[int, int]:
    match = ROUTER.fullmatch(value)
    if not match:
        raise ValueError(f"invalid router name {value!r}; expected router_X_Y")
    return int(match.group(1)), int(match.group(2))


def load_compiler_trace(path: Path, mesh: str | None) -> tuple[str, int, int, int, list[Request]]:
    trace = parse_compiler_trace(path)
    rows, columns = mesh_dimensions(trace, mesh)
    return (
        path.stem,
        rows,
        columns,
        trace.layer_count,
        [Request(item.layer, (item.source_core % columns, item.source_core // columns),
                 (item.destination_core % columns, item.destination_core // columns))
         for item in trace.requests],
    )


def load_traffic(path: Path) -> tuple[str, int, int, int, list[Request]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        rows, columns, layers = payload["num_rows"], payload["num_cols"], payload["layers"]
    except KeyError as error:
        raise ValueError(f"{path}: missing traffic JSON field {error.args[0]!r}") from error
    requests = []
    for layer_index, layer in enumerate(layers):
        for item in layer:
            if len(item) < 3:
                raise ValueError(f"{path}: malformed request in layer {layer_index}")
            requests.append(Request(layer_index, parse_router(item[1]), parse_router(item[2])))
    return f"{payload.get('circuit_type', path.stem)}:{path.stem}", rows, columns, len(layers), requests


def percentile(values: Iterable[int], fraction: float) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def audit(name: str, rows: int, columns: int, source_layers: int, requests: list[Request], capacities: list[int]) -> dict:
    by_layer: dict[int, list[Request]] = defaultdict(list)
    for request in requests:
        if not (0 <= request.source[0] < columns and 0 <= request.source[1] < rows and
                0 <= request.destination[0] < columns and 0 <= request.destination[1] < rows):
            raise ValueError(f"{name}: request endpoint lies outside {rows}x{columns} mesh")
        by_layer[request.layer].append(request)
    endpoint_by_layer: dict[int, Counter] = {}
    link_by_layer: dict[int, Counter] = {}
    endpoint_samples: list[int] = []
    link_samples: list[int] = []
    total_route_hops = 0
    worst_endpoint = (0, None, None)
    worst_link = (0, None, None)
    for layer, layer_requests in by_layer.items():
        endpoints: Counter = Counter()
        links: Counter = Counter()
        for request in layer_requests:
            endpoints.update((request.source, request.destination))
            route = xy_path(request.source, request.destination)
            links.update(route)
            total_route_hops += len(route)
        endpoint_by_layer[layer] = endpoints
        link_by_layer[layer] = links
        endpoint_samples.extend(endpoints.values())
        link_samples.extend(links.values())
        if endpoints:
            core, demand = endpoints.most_common(1)[0]
            worst_endpoint = max(worst_endpoint, (demand, layer, core))
        if links:
            link, demand = links.most_common(1)[0]
            worst_link = max(worst_link, (demand, layer, link))
    capacity_stats = {}
    for capacity in capacities:
        overloaded_layers = []
        affected_requests = 0
        endpoint_excess = 0
        for layer, layer_requests in by_layer.items():
            demand = endpoint_by_layer[layer]
            overloaded = {core for core, value in demand.items() if value > capacity}
            endpoint_excess += sum(value - capacity for value in demand.values() if value > capacity)
            if overloaded:
                overloaded_layers.append(layer)
                affected_requests += sum(
                    request.source in overloaded or request.destination in overloaded
                    for request in layer_requests
                )
        capacity_stats[str(capacity)] = {
            "overloaded_layers": len(overloaded_layers),
            "overloaded_layer_percent_of_active": round(100 * len(overloaded_layers) / len(by_layer), 3) if by_layer else 0,
            "affected_requests": affected_requests,
            "affected_request_percent": round(100 * affected_requests / len(requests), 3) if requests else 0,
            "endpoint_demand_excess": endpoint_excess,
        }
    return {
        "name": name,
        "definition": {
            "endpoint_demand": "number of due requests in one source layer incident on a core",
            "overload": "a core has endpoint demand strictly greater than memory capacity K",
            "affected_request": "a request has at least one endpoint overloaded at K in its source layer",
            "route": "horizontal-then-vertical XY, counted over undirected physical mesh links",
        },
        "configuration": {"mesh_rows": rows, "mesh_columns": columns, "cores": rows * columns},
        "workload": {
            "source_layers": source_layers,
            "active_layers": len(by_layer),
            "requests": len(requests),
            "mean_requests_per_active_layer": round(mean(map(len, by_layer.values())), 4) if by_layer else 0,
            "max_requests_in_one_layer": max(map(len, by_layer.values()), default=0),
            "total_xy_route_hops": total_route_hops,
            "mean_xy_hops_per_request": round(total_route_hops / len(requests), 4) if requests else 0,
        },
        "endpoint_pressure": {
            "mean_nonzero_demand": round(mean(endpoint_samples), 4) if endpoint_samples else 0,
            "p95_nonzero_demand": percentile(endpoint_samples, 0.95),
            "peak_demand": worst_endpoint[0],
            "peak_layer": worst_endpoint[1],
            "peak_core_xy": worst_endpoint[2],
        },
        "route_link_pressure": {
            "mean_nonzero_link_demand": round(mean(link_samples), 4) if link_samples else 0,
            "p95_nonzero_link_demand": percentile(link_samples, 0.95),
            "peak_link_demand": worst_link[0],
            "peak_layer": worst_link[1],
            "peak_link_xy": worst_link[2],
        },
        "capacity_sweep": capacity_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--trace", type=Path, help="compiler text trace")
    group.add_argument("--traffic", type=Path, help="fixed-mapping traffic JSON")
    parser.add_argument("--mesh", help="ROWSxCOLUMNS; required only when a text trace is non-square")
    parser.add_argument("--capacities", default="1,2,3,4", help="comma-separated endpoint capacities K")
    parser.add_argument("--output", type=Path, help="write audit JSON here; otherwise print it")
    args = parser.parse_args()
    capacities = [int(item) for item in args.capacities.split(",")]
    if not capacities or any(item < 1 for item in capacities):
        parser.error("capacities must be positive integers")
    loaded = load_compiler_trace(args.trace, args.mesh) if args.trace else load_traffic(args.traffic)
    report = audit(*loaded, capacities=capacities)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
