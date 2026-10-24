"""Offline (compile-time) re-routing of a mapped trace: can choosing different paths reduce core congestion?

The mapping is held fixed: every qubit still moves from the same source core to the same destination core in the same
layer.  Only the *path* of each such move (a route) is re-chosen, per layer and independently, to minimise the demand
that exceeds the communication capacity.  Layers are independent because a layer's routes start and end at fixed cores.

Demand (see tools/experiment2/split_congestion.py): variant ``hop`` counts hop touches (an endpoint 1, a relay 2);
variant ``route`` counts routes touching a core once.  The objective is the *excess* sum over cores of max(0, D - C).

**Lower bound.**  Endpoints do not depend on the path, so D >= D_end for every core and every routing; hence the excess is at
least  sum over cores of max(0, D_end - C).  No re-routing, however clever, can go below it (tested).

The optimiser solves one small mixed-integer program per overloaded layer exactly (scipy.optimize.milp / HiGHS), choosing one
candidate path per route: all simple paths of at most shortest + ``extra`` hops.  The mapper's own path is always a candidate,
so the result is never worse than the baseline (tested).  A tiny per-hop cost prefers fewer hops among equal-excess choices.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "congestion_study"))
sys.path.insert(0, str(REPO / "tools" / "experiment2"))
from hotspot_analysis import adjacent, read_trace                         # noqa: E402
from split_congestion import routes_of_layer                              # noqa: E402

HOP_COST = 1e-4          # prefers fewer hops among equal-excess choices; far below one unit of excess


def adjacency(topology: str, rows: int = 4, columns: int = 4) -> dict[int, list[int]]:
    n = rows * columns
    return {a: [b for b in range(n) if adjacent(a, b, rows, columns, topology)] for a in range(n)}


def shortest_length(adj, source: int, target: int) -> int:
    seen, frontier, steps = {source}, [source], 0
    while frontier:
        if target in frontier:
            return steps
        frontier = [n for c in frontier for n in adj[c] if not (n in seen or seen.add(n))]
        steps += 1
    raise ValueError("unreachable")


def simple_paths(adj, source: int, target: int, max_hops: int) -> list[tuple[int, ...]]:
    """All simple paths source -> target with at most max_hops hops."""
    out: list[tuple[int, ...]] = []

    def walk(path):
        node = path[-1]
        if node == target:
            out.append(tuple(path))
            return
        if len(path) - 1 >= max_hops:
            return
        for nxt in adj[node]:
            if nxt not in path:
                walk(path + [nxt])
    walk([source])
    return out


def touches(path: tuple[int, ...], variant: str) -> dict[int, tuple[int, int]]:
    """core -> (demand, endpoint demand) this one route puts on each core it visits."""
    last = len(path) - 1
    result: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    if variant == "hop":
        for index, core in enumerate(path):
            at_end = index in (0, last)
            result[core][0] += 1 if at_end else 2
            result[core][1] += 1 if at_end else 0
    elif variant == "route":
        for core in set(path):
            result[core][0] += 1
            result[core][1] += core in (path[0], path[-1])
    else:
        raise ValueError(variant)
    return {c: (v[0], v[1]) for c, v in result.items()}


def demand(paths, variant: str) -> Counter:
    total: Counter = Counter()
    for path in paths:
        for core, (d, _) in touches(path, variant).items():
            total[core] += d
    return total


def excess(paths, capacity: int, variant: str) -> int:
    return sum(max(0, d - capacity) for d in demand(paths, variant).values())


def lower_bound(paths, capacity: int, variant: str) -> int:
    """Smallest excess any routing of these routes can have (endpoint demand alone)."""
    end: Counter = Counter()
    for path in paths:
        for core, (_, e) in touches(path, variant).items():
            end[core] += e
    return sum(max(0, e - capacity) for e in end.values())


def volume_bound(paths, capacity: int, variant: str, adj) -> int:
    """A second lower bound on the excess, from the total demand alone.

    However the routes are chosen, a route of shortest length k puts at least 2k hop touches (variant ``hop``) or k + 1 route
    touches (variant ``route``) on the cores, and a core absorbs at most ``capacity`` of them without excess.  So
    excess >= total minimum demand - cores * capacity.  (Detours only raise the total.)  Routes that return to their start are
    counted as the mapper routed them.
    """
    cores = len(adj)
    total = 0
    for path in paths:
        k = shortest_length(adj, path[0], path[-1]) if path[0] != path[-1] else len(path) - 1
        total += 2 * k if variant == "hop" else k + 1
    return max(0, total - cores * capacity)


@dataclass
class LayerResult:
    paths: list[tuple[int, ...]]
    baseline_excess: int
    excess: int
    optimal: bool


def optimize_layer(paths, capacity: int, variant: str, adj, extra: int = 0, time_limit: float = 20.0) -> LayerResult:
    """Choose one candidate path per route minimising the excess; never worse than the given paths."""
    paths = [tuple(p) for p in paths]
    base = excess(paths, capacity, variant)
    if base == 0:
        return LayerResult(paths, 0, 0, True)
    candidates = []
    for path in paths:
        source, target = path[0], path[-1]
        if source == target:                       # a route that returns to its start is left as the mapper made it
            candidates.append([path])
            continue
        options = simple_paths(adj, source, target, shortest_length(adj, source, target) + extra)
        if path not in options:
            options.append(path)
        candidates.append(options)
    cores = sorted({c for options in candidates for path in options for c in path})
    column_of = {}
    for r, options in enumerate(candidates):
        for p in range(len(options)):
            column_of[(r, p)] = len(column_of)
    nx_, ne = len(column_of), len(cores)
    cost = np.zeros(nx_ + ne)
    rows_a, rhs_hi = [], []
    a_demand = np.zeros((ne, nx_ + ne))
    for (r, p), col in column_of.items():
        path = candidates[r][p]
        cost[col] = HOP_COST * (len(path) - 1)
        for core, (d, _) in touches(path, variant).items():
            a_demand[cores.index(core), col] += d
    for i in range(ne):
        a_demand[i, nx_ + i] = -1.0               # demand - e <= capacity
    cost[nx_:] = 1.0
    a_choice = np.zeros((len(candidates), nx_ + ne))
    for (r, p), col in column_of.items():
        a_choice[r, col] = 1.0
    constraints = [LinearConstraint(a_demand, -np.inf, capacity), LinearConstraint(a_choice, 1.0, 1.0)]
    integrality = np.concatenate([np.ones(nx_), np.zeros(ne)])
    bounds = Bounds(np.zeros(nx_ + ne), np.concatenate([np.ones(nx_), np.full(ne, np.inf)]))
    result = milp(cost, constraints=constraints, integrality=integrality, bounds=bounds,
                  options={"time_limit": time_limit, "mip_rel_gap": 0.0})
    if result.x is None:
        return LayerResult(paths, base, base, False)
    chosen = []
    for r, options in enumerate(candidates):
        values = [result.x[column_of[(r, p)]] for p in range(len(options))]
        chosen.append(options[int(np.argmax(values))])
    new = excess(chosen, capacity, variant)
    if new > base:                                 # cannot happen with an exact solve; never return a worse routing
        return LayerResult(paths, base, base, False)
    return LayerResult(chosen, base, new, bool(result.status == 0))


def layer_routes(trace) -> dict[int, list[tuple[int, ...]]]:
    by_layer = defaultdict(list)
    for hop in trace.hops:
        by_layer[hop.layer].append(hop)
    return {layer: [tuple(p) for p in routes_of_layer(hops)] for layer, hops in by_layer.items()}


def reroute_trace(trace, capacity: int, variant: str, adj, extra: int = 0, time_limit: float = 20.0):
    """New route per layer; returns ({layer: [paths]}, per-layer results)."""
    new, results = {}, {}
    for layer, paths in sorted(layer_routes(trace).items()):
        res = optimize_layer(paths, capacity, variant, adj, extra, time_limit)
        new[layer], results[layer] = res.paths, res
    return new, results


def write_trace(trace, routes_by_layer, qubits_by_layer, path: Path) -> Path:
    """Write ``routes_by_layer`` in the mapper's request-file format; each route keeps its qubit and its place in the layer."""
    lines = ["// Number of cores", str(trace.cores), "// Number of qubit slots per core", str(trace.slots),
             "// Number of qubits", str(trace.qubits), "// Initial placement: (qubit, core)"]
    lines += [f"({q}, {c})" for q, c in sorted(trace.initial.items())]
    lines.append("// Inter-core communication requests: (qubit, src, dst)")
    for layer in range(trace.layers):
        lines.append(f"// Layer {layer}")
        for qubit, route in zip(qubits_by_layer.get(layer, []), routes_by_layer.get(layer, [])):
            lines += [f"({qubit}, {a}, {b})" for a, b in zip(route, route[1:])]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def route_qubits(trace) -> dict[int, list[int]]:
    """Qubit of each route of each layer, in the same order as ``layer_routes``."""
    by_layer = defaultdict(list)
    for hop in trace.hops:
        by_layer[hop.layer].append(hop)
    out = {}
    for layer, hops in by_layer.items():
        qubits, chains = [], []
        for hop in hops:
            if chains and chains[-1][0] == hop.qubit and chains[-1][1][-1] == hop.source:
                chains[-1][1].append(hop.target)
            else:
                chains.append((hop.qubit, [hop.source, hop.target]))
                qubits.append(hop.qubit)
        out[layer] = qubits
    return out
