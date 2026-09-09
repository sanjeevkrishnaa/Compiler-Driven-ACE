"""Strict loader for cross-repository compiler experiment contracts."""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path

import networkx as nx


POLICIES = {"full-odg", "matched-odg", "fixed", "dynamic"}


def contract_sha256(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def load_contract(path: str | Path) -> dict:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("experiment contract schema_version must be 1")
    workload = payload.get("workload", {})
    required_workload = {
        "trace_sha256", "mesh", "cores", "logical_qubits", "layers", "requests",
        "serialized_sublayers", "serialization_map_sha256",
    }
    missing = required_workload - set(workload)
    if missing:
        raise ValueError(f"experiment contract workload is missing {sorted(missing)}")
    replications = payload.get("replications", {})
    for field in ("seed_start", "seed_count"):
        value = replications.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"replications.{field} must be a nonnegative integer")
    if replications["seed_count"] < 1:
        raise ValueError("replications.seed_count must be positive")
    scheduler = payload.get("scheduler", {})
    for field in ("fixed_delta_layers", "dynamic_lookahead_layers",
                  "dynamic_minimum_lead_layers"):
        value = scheduler.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"scheduler.{field} must be a positive integer")
    coherence = scheduler.get("coherence_time_layers")
    if isinstance(coherence, bool) or not isinstance(coherence, (int, float)) \
            or coherence <= 0:
        raise ValueError("scheduler.coherence_time_layers must be positive")
    if scheduler["dynamic_minimum_lead_layers"] > scheduler["dynamic_lookahead_layers"]:
        raise ValueError("dynamic minimum lead cannot exceed lookahead")
    if scheduler.get("generation_capacity_rule") != "equal_to_compiler_memories":
        raise ValueError("unsupported generation capacity rule")
    layer_duration = payload.get("timing", {}).get("logical_layer_duration_ps")
    if isinstance(layer_duration, bool) or not isinstance(layer_duration, int) \
            or layer_duration < 1:
        raise ValueError("timing.logical_layer_duration_ps must be a positive integer")
    runtime = payload.get("runtime_overrides", {})
    if not isinstance(runtime.get("ace"), dict) or not isinstance(runtime.get("native"), dict):
        raise ValueError("runtime_overrides must define ace and native mappings")
    profiles = payload.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("experiment contract must contain profiles")
    identifiers = set()
    for profile in profiles:
        identifier = profile.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("profile ids must be unique nonempty strings")
        identifiers.add(identifier)
        values = [profile.get(name) for name in (
            "total_entanglement_memories_per_core",
            "compiler_memories_per_core",
            "on_demand_memories_per_core",
        )]
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
               for value in values):
            raise ValueError(f"profile {identifier} memory counts must be nonnegative integers")
        total, compiler, demand = values
        execution_mode = profile.get("execution_mode", "fallback-enabled")
        if execution_mode not in {"fallback-enabled", "strict-compiler-only"}:
            raise ValueError(f"profile {identifier} has unsupported execution_mode")
        allocation = profile.get("memory_allocation", "static")
        if allocation not in {"static", "shared"}:
            raise ValueError(f"profile {identifier} has unsupported memory_allocation")
        if total < 1:
            raise ValueError(f"profile {identifier} must have at least one memory")
        if allocation == "static" and compiler + demand != total:
            raise ValueError(
                f"profile {identifier} must partition total memory into compiler + demand"
            )
        if allocation == "shared" and not (0 < compiler <= total and demand == total):
            raise ValueError(
                f"shared profile {identifier} must use a positive compiler cap no larger "
                "than total memory, with all total memories demand-eligible"
            )
        policies = profile.get("policies")
        if not isinstance(policies, list) or not policies or set(policies) - POLICIES:
            raise ValueError(f"profile {identifier} contains invalid policies")
        if compiler == 0 and policies != ["full-odg"]:
            raise ValueError(f"profile {identifier} with no compiler bank must be full-odg only")
        if compiler > 0 and "full-odg" in policies:
            raise ValueError(f"profile {identifier} cannot mix full-odg with a static partition")
        if allocation == "shared" and execution_mode != "fallback-enabled":
            raise ValueError(f"shared profile {identifier} must be fallback-enabled")
        if demand == 0:
            if execution_mode != "strict-compiler-only":
                raise ValueError(f"profile {identifier} with no demand bank must be strict")
            if set(policies) - {"fixed", "dynamic"}:
                raise ValueError(f"strict profile {identifier} supports fixed and dynamic only")
        elif execution_mode != "fallback-enabled":
            raise ValueError(f"profile {identifier} with a demand bank must use fallback-enabled mode")
    return payload


def select_profile(contract: dict, identifier: str) -> dict:
    for profile in contract["profiles"]:
        if profile["id"] == identifier:
            return profile
    choices = ", ".join(profile["id"] for profile in contract["profiles"])
    raise ValueError(f"unknown experiment profile {identifier!r}; choose one of: {choices}")


def validate_workload(contract: dict, *, trace_sha256: str, mesh: str,
                      cores: int, logical_qubits: int, layers: int,
                      requests: int) -> None:
    expected = contract["workload"]
    actual = {
        "trace_sha256": trace_sha256,
        "mesh": mesh,
        "cores": cores,
        "logical_qubits": logical_qubits,
        "layers": layers,
        "requests": requests,
    }
    mismatches = {
        name: {"expected": expected[name], "actual": value}
        for name, value in actual.items() if value != expected[name]
    }
    if mismatches:
        raise ValueError(f"trace/workload does not satisfy experiment contract: {mismatches}")


def serialize_conflict_layers(requests, layer_count: int):
    """Return request-to-sublayer mapping using stable selective edge coloring."""
    def endpoints(request):
        if hasattr(request, "source_core"):
            return request.source_core, request.destination_core
        return request.source, request.destination

    by_layer = defaultdict(list)
    for request in requests:
        by_layer[request.layer].append(request)
    batches = []
    origins = []
    for layer_index in range(layer_count):
        layer = by_layer[layer_index]
        if not layer:
            batches.append([])
            origins.append(layer_index)
            continue
        pending = list(layer)
        greedy = []
        while pending:
            used = set()
            batch = []
            deferred = []
            for request in pending:
                request_endpoints = set(endpoints(request))
                if used.isdisjoint(request_endpoints):
                    batch.append(request)
                    used.update(request_endpoints)
                else:
                    deferred.append(request)
            greedy.append(batch)
            pending = deferred
        degrees = Counter(
            endpoint for request in layer
            for endpoint in endpoints(request)
        )
        maximum_degree = max(degrees.values())
        if len(greedy) == maximum_degree:
            batches.extend(greedy)
            origins.extend([layer_index] * len(greedy))
            continue

        support = nx.Graph()
        support.add_edges_from(endpoints(request) for request in layer)
        coloring = nx.algorithms.bipartite.color(support)
        left = sorted(node for node, color in coloring.items() if color == 0)
        right = sorted(node for node, color in coloring.items() if color == 1)
        size = max(len(left), len(right))
        left.extend(("__dummy_left__", layer_index, index)
                    for index in range(size - len(left)))
        right.extend(("__dummy_right__", layer_index, index)
                     for index in range(size - len(right)))
        left_set = set(left)
        edge_buckets = defaultdict(list)
        for request in layer:
            source, destination = endpoints(request)
            edge = ((source, destination) if source in left_set else (destination, source))
            edge_buckets[edge].append(request)
        degree = Counter()
        for (source, destination), records in edge_buckets.items():
            degree[source] += len(records)
            degree[destination] += len(records)
        left_slots = [node for node in left for _ in range(maximum_degree - degree[node])]
        right_slots = [node for node in right for _ in range(maximum_degree - degree[node])]
        if len(left_slots) != len(right_slots):
            raise RuntimeError("bipartite regularization produced unequal deficits")
        for source, destination in zip(left_slots, right_slots):
            edge_buckets[(source, destination)].append(None)
        for _ in range(maximum_degree):
            graph = nx.Graph()
            graph.add_nodes_from(left, bipartite=0)
            graph.add_nodes_from(right, bipartite=1)
            bonus = len(layer) + 1
            for edge, records in edge_buckets.items():
                real = [record for record in records if record is not None]
                weight = bonus * len(layer) - min(
                    (record.request_id for record in real), default=bonus * len(layer)
                )
                if records:
                    graph.add_edge(*edge, weight=weight)
            pairs = nx.algorithms.matching.max_weight_matching(
                graph, maxcardinality=True, weight="weight"
            )
            matching = {source: destination for pair in pairs
                        for source, destination in (tuple(pair), tuple(reversed(tuple(pair))))}
            if any(node not in matching for node in left):
                raise RuntimeError("regularized bipartite layer has no perfect matching")
            batch = []
            for source in left:
                records = edge_buckets[(source, matching[source])]
                real_index = min(
                    (index for index, record in enumerate(records) if record is not None),
                    key=lambda index: records[index].request_id,
                    default=len(records) - 1,
                )
                record = records.pop(real_index)
                if record is not None:
                    batch.append(record)
            batch.sort(key=lambda request: request.request_id)
            if batch:
                batches.append(batch)
                origins.append(layer_index)
    request_layers = {
        request.request_id: sublayer
        for sublayer, batch in enumerate(batches) for request in batch
    }
    return request_layers, batches, origins


def serialization_sha256(request_layers: dict[int, int]) -> str:
    payload = json.dumps(request_layers, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()
