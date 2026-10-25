"""Controlled route interventions on a fixed placement (the causal tests of docs/plans/why-xy-wins-test-design.md).

Every intervention keeps each migration's layer, qubit, source and destination and only changes the route of some migrations.  All
routes are shortest paths on the mesh, so hop counts are unchanged (checked: output hops == input hops).  Each trace is validated
(endpoints, adjacency, partition replay) by the same adapter code as the policy exports.

Interventions (name pattern -> rule):
  mix_p<P>_s<S>       migration takes its XY path with probability P/100 (coin seeded by S, layer, qubit), else keeps its supplied route
  rand_shortest_s<S>  uniform random shortest path (seeded)
  o1turn_s<S>         XY or YX with equal probability (seeded)
  concentrate         per layer, greedily the shortest path through the cores that already carry the most demand
  balance             per layer, greedily the shortest path that minimises the largest resulting core demand
  avoid_hot<K>        migrations whose supplied route relays through any of the K busiest relay cores of the supplied routes take XY, then YX,
                      then the shortest path with the fewest hot relays; others keep their supplied route

Demand while choosing is the group's definition (endpoint touch 1, relay touch 2, per layer).
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from qmap.metrics.distance import DistanceOracle

from .adapter import import_legacy_request_file, validate_migration_records, write_adjacent_requests, write_migration_trace
from .placement_contract import build_architecture
from .routing import route_path


def _distances(neighbours: dict[int, list[int]], origin: int) -> dict[int, int]:
    dist, frontier = {origin: 0}, [origin]
    while frontier:
        nxt = []
        for core in frontier:
            for other in neighbours[core]:
                if other not in dist:
                    dist[other] = dist[core] + 1
                    nxt.append(other)
        frontier = nxt
    return dist


def shortest_paths(architecture, source: int, target: int) -> list[tuple[int, ...]]:
    """All shortest paths between two cores, in lexicographic order of the core numbers."""
    neighbours = {c: sorted(architecture.index_of(n) for n in architecture.graph.neighbors(architecture.coordinate_of(c)))
                  for c in range(architecture.n_cores)}
    from_source, to_target = _distances(neighbours, source), _distances(neighbours, target)
    length = from_source[target]
    out: list[tuple[int, ...]] = []

    def walk(path):
        node = path[-1]
        if node == target:
            out.append(tuple(path))
            return
        for other in neighbours[node]:
            if from_source[other] == len(path) and from_source[other] + to_target[other] == length:
                walk(path + [other])

    walk([source])
    return out


def touches(path: tuple[int, ...]) -> dict[int, int]:
    return {c: (1 if i in (0, len(path) - 1) else 2) for i, c in enumerate(path)}


def build(records, architecture, oracle, name: str) -> list:
    match_seed, match_p = re.search(r"_s(\d+)", name), re.search(r"_p(\d+)", name)
    seed = int(match_seed.group(1)) if match_seed else 0
    def xy(r): return route_path(architecture, oracle, r.source_core, r.destination_core, "xy")
    def yx(r): return route_path(architecture, oracle, r.source_core, r.destination_core, "yx")
    out = []
    if name.startswith("mix_"):
        p = int(match_p.group(1)) / 100
        for r in records:
            coin = random.Random(f"mix:{seed}:{r.layer}:{r.qubit}").random()
            out.append(replace(r, path=xy(r), route_policy=name) if coin < p else replace(r, route_policy=name))
    elif name.startswith("rand_shortest_"):
        for r in records:
            options = shortest_paths(architecture, r.source_core, r.destination_core)
            out.append(replace(r, path=random.Random(f"rs:{seed}:{r.layer}:{r.qubit}").choice(options), route_policy=name))
    elif name.startswith("o1turn_"):
        for r in records:
            choose = xy if random.Random(f"o1:{seed}:{r.layer}:{r.qubit}").random() < 0.5 else yx
            out.append(replace(r, path=choose(r), route_policy=name))
    elif name in ("concentrate", "balance"):
        by_layer = defaultdict(list)
        for i, r in enumerate(records):
            by_layer[r.layer].append(i)
        chosen = {}
        for layer, indices in by_layer.items():
            demand: Counter = Counter()
            for i in indices:
                r = records[i]
                options = shortest_paths(architecture, r.source_core, r.destination_core)
                if len(options) == 1:
                    path = options[0]
                elif name == "concentrate":
                    path = max(options, key=lambda p: (sum(demand[c] * t for c, t in touches(p).items()), p == r.path))
                else:
                    path = min(options, key=lambda p: (max(demand[c] + t for c, t in touches(p).items()),
                                                       sum(demand[c] * t for c, t in touches(p).items()), p != r.path))
                for c, t in touches(path).items():
                    demand[c] += t
                chosen[i] = path
        out = [replace(r, path=chosen[i], route_policy=name) for i, r in enumerate(records)]
    elif name.startswith("avoid_hot"):
        k = int(name[len("avoid_hot"):])
        relay = Counter(c for r in records for c in r.path[1:-1])
        hot = {c for c, _ in relay.most_common(k)}
        for r in records:
            if not hot.intersection(r.path[1:-1]):
                out.append(replace(r, route_policy=name))
                continue
            options = [xy(r), yx(r)] + shortest_paths(architecture, r.source_core, r.destination_core)
            best = min(options, key=lambda p: len(hot.intersection(p[1:-1])))
            out.append(replace(r, path=best, route_policy=name))
    else:
        raise ValueError(f"unknown intervention {name!r}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", type=Path, required=True, help="supplied hop file whose routes are intervened on")
    parser.add_argument("--contract", type=Path, required=True, help="placement contract of the same trace")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    architecture = build_architecture(tuple(contract["dimensions"]), contract["qubits_per_core"], contract["seed"],
                                      contract["reliability_min"], contract.get("reliability_max", 1.0), contract["topology"])
    oracle = DistanceOracle(architecture)
    partition, records = import_legacy_request_file(args.base, architecture)
    summary = {}
    for name in args.names:
        new = build(records, architecture, oracle, name)
        assert [(r.layer, r.qubit, r.source_core, r.destination_core) for r in new] == \
               [(r.layer, r.qubit, r.source_core, r.destination_core) for r in records], "endpoints changed"
        assert sum(r.path_hops for r in new) == sum(r.path_hops for r in records), "hop count changed"
        validate_migration_records(partition, architecture, new)
        directory = args.output / name
        write_migration_trace(new, architecture, directory / "migrations.jsonl")
        _, hops = write_adjacent_requests(new, partition, architecture, directory / "requests.txt")
        changed = sum(a.path != b.path for a, b in zip(new, records))
        summary[name] = {"migrations": len(new), "hops": hops, "routes_changed": changed}
        print(f"{name:24s} hops {hops}  routes changed {changed}/{len(new)}")
    (args.output / "interventions.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
