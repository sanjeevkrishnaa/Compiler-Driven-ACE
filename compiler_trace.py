"""Parser and offline planner for compiler-emitted inter-core traces.

The input is the text format used by ``qft_requests.txt``.  Trace contents are
treated as data only and are validated against the evolving qubit placement.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from math import ceil, isqrt
from pathlib import Path
import re


_TUPLE_PATTERN = re.compile(r"^\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)$")
_LAYER_PATTERN = re.compile(r"^//\s*Layer\s+(\d+)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class CompilerRequest:
    request_id: int
    layer: int
    order: int
    qubit: int
    source_core: int
    destination_core: int

    @property
    def edge(self) -> tuple[int, int]:
        return tuple(sorted((self.source_core, self.destination_core)))


@dataclass(frozen=True)
class CompilerTrace:
    core_count: int
    qubit_slots_per_core: int
    qubit_count: int
    initial_placement: dict[int, int]
    requests: tuple[CompilerRequest, ...]
    layer_count: int

    @property
    def inferred_free_slots_per_core(self) -> int:
        occupancy = Counter(self.initial_placement.values())
        return self.qubit_slots_per_core - max(occupancy.values(), default=0)


@dataclass(frozen=True)
class ScheduledPreparation:
    request_id: int
    generation_layer: int


def _parse_tuple(line: str, line_number: int) -> tuple[int, ...]:
    match = _TUPLE_PATTERN.match(line)
    if match is None:
        raise ValueError(f"line {line_number}: malformed tuple {line!r}")
    return tuple(int(value.strip()) for value in match.group(1).split(","))


def parse_compiler_trace(path: str | Path) -> CompilerTrace:
    path = Path(path)
    metadata: dict[str, int] = {}
    pending_metadata: str | None = None
    section: str | None = None
    placement: dict[int, int] = {}
    requests: list[CompilerRequest] = []
    current_layer: int | None = None
    highest_layer = -1
    layer_order = 0
    markers = {
        "// number of cores": "core_count",
        "// number of qubit slots per core": "qubit_slots_per_core",
        "// number of qubits": "qubit_count",
    }

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered in markers:
            pending_metadata = markers[lowered]
            continue
        if lowered.startswith("// initial placement"):
            section = "placement"
            continue
        if lowered.startswith("// inter-core communication requests"):
            section = "requests"
            continue
        layer_match = _LAYER_PATTERN.match(line)
        if layer_match:
            section = "requests"
            current_layer = int(layer_match.group(1))
            highest_layer = max(highest_layer, current_layer)
            layer_order = 0
            continue
        if line.startswith("//"):
            continue
        if pending_metadata is not None:
            try:
                metadata[pending_metadata] = int(line)
            except ValueError as error:
                raise ValueError(
                    f"line {line_number}: expected integer value for {pending_metadata}"
                ) from error
            pending_metadata = None
            continue

        values = _parse_tuple(line, line_number)
        if section == "placement":
            if len(values) != 2:
                raise ValueError(f"line {line_number}: placement requires (qubit, core)")
            qubit, core = values
            if qubit in placement:
                raise ValueError(f"line {line_number}: duplicate placement for qubit {qubit}")
            placement[qubit] = core
        elif section == "requests":
            if current_layer is None:
                raise ValueError(f"line {line_number}: request appears before a layer marker")
            if len(values) != 3:
                raise ValueError(f"line {line_number}: request requires (qubit, src, dst)")
            qubit, source, destination = values
            requests.append(CompilerRequest(
                request_id=len(requests), layer=current_layer, order=layer_order,
                qubit=qubit, source_core=source, destination_core=destination,
            ))
            layer_order += 1
        else:
            raise ValueError(f"line {line_number}: tuple appears outside a known section")

    required = {"core_count", "qubit_slots_per_core", "qubit_count"}
    missing = required - metadata.keys()
    if missing:
        raise ValueError(f"trace metadata missing: {', '.join(sorted(missing))}")
    if any(metadata[name] < 1 for name in required):
        raise ValueError("trace counts must be positive")
    if set(placement) != set(range(metadata["qubit_count"])):
        raise ValueError("initial placement must contain every qubit exactly once")
    if any(not 0 <= core < metadata["core_count"] for core in placement.values()):
        raise ValueError("initial placement references a core outside the declared range")

    evolving_placement = dict(placement)
    for request in requests:
        if not 0 <= request.qubit < metadata["qubit_count"]:
            raise ValueError(f"request {request.request_id}: invalid qubit {request.qubit}")
        for core in request.edge:
            if not 0 <= core < metadata["core_count"]:
                raise ValueError(f"request {request.request_id}: invalid core {core}")
        if request.source_core == request.destination_core:
            raise ValueError(f"request {request.request_id}: source equals destination")
        actual_source = evolving_placement[request.qubit]
        if actual_source != request.source_core:
            raise ValueError(
                f"request {request.request_id}: qubit {request.qubit} is on core "
                f"{actual_source}, not {request.source_core}"
            )
        evolving_placement[request.qubit] = request.destination_core

    return CompilerTrace(
        core_count=metadata["core_count"],
        qubit_slots_per_core=metadata["qubit_slots_per_core"],
        qubit_count=metadata["qubit_count"],
        initial_placement=placement,
        requests=tuple(requests),
        layer_count=highest_layer + 1,
    )


def mesh_dimensions(trace: CompilerTrace, mesh: str | None = None) -> tuple[int, int]:
    if mesh:
        match = re.fullmatch(r"(\d+)x(\d+)", mesh.lower().strip())
        if match is None:
            raise ValueError("mesh must have ROWSxCOLUMNS form, for example 4x4")
        rows, columns = map(int, match.groups())
    else:
        side = isqrt(trace.core_count)
        if side * side != trace.core_count:
            raise ValueError("--mesh is required when the core count is not a square")
        rows = columns = side
    if rows * columns != trace.core_count:
        raise ValueError(f"mesh {rows}x{columns} does not contain {trace.core_count} cores")
    return rows, columns


def router_name(core: int, columns: int) -> str:
    return f"router_{core // columns}_{core % columns}"


def validate_neighbor_requests(trace: CompilerTrace, rows: int, columns: int) -> None:
    for request in trace.requests:
        src = divmod(request.source_core, columns)
        dst = divmod(request.destination_core, columns)
        if not (src[0] < rows and dst[0] < rows and abs(src[0] - dst[0]) + abs(src[1] - dst[1]) == 1):
            raise ValueError(
                f"request {request.request_id} is not an elementary mesh hop: "
                f"{request.source_core}->{request.destination_core}"
            )


def to_ace_layers(
    trace: CompilerTrace,
    *,
    columns: int,
    fidelity: float = 0.01,
) -> list[list[tuple[int, str, str, int, float, int]]]:
    layers: list[list[tuple[int, str, str, int, float, int]]] = [
        [] for _ in range(trace.layer_count)
    ]
    for request in trace.requests:
        layers[request.layer].append((
            request.request_id,
            router_name(request.source_core, columns),
            router_name(request.destination_core, columns),
            1,
            fidelity,
            1,
        ))
    return layers


def _candidate_layers(
    request: CompilerRequest,
    strategy: str,
    delta_layers: int,
    dynamic_lookahead_layers: int,
    dynamic_min_lead_layers: int,
) -> tuple[int, ...]:
    if strategy == "on-demand":
        return ()
    if strategy == "fixed":
        return (request.layer - delta_layers,)
    if strategy == "dynamic":
        lower = max(0, request.layer - dynamic_lookahead_layers)
        latest = request.layer - dynamic_min_lead_layers
        return tuple(range(latest, lower - 1, -1))
    raise ValueError(f"unknown compiler strategy {strategy!r}")


def plan_preparations(
    trace: CompilerTrace,
    *,
    strategy: str,
    compiler_memories_per_core: int,
    generation_capacity_per_core: int,
    coherence_time_layers: float,
    delta_layers: int = 2,
    dynamic_lookahead_layers: int = 8,
    dynamic_min_lead_layers: int = 1,
) -> tuple[tuple[ScheduledPreparation, ...], int, int]:
    """Plan request-specific preparations under per-layer memory limits."""

    if coherence_time_layers <= 0 or delta_layers < 1 or dynamic_lookahead_layers < 1:
        raise ValueError("coherence and lookahead values must be positive")
    if not 1 <= dynamic_min_lead_layers <= dynamic_lookahead_layers:
        raise ValueError("dynamic minimum lead must be within the dynamic lookahead")
    if strategy == "on-demand":
        return (), 0, 0
    if compiler_memories_per_core < 1 or generation_capacity_per_core < 1:
        raise ValueError("compiler memory and generation capacities must be positive")

    memory_load: defaultdict[tuple[int, int], int] = defaultdict(int)
    generation_load: defaultdict[tuple[int, int], int] = defaultdict(int)
    scheduled: list[ScheduledPreparation] = []
    blocked = 0
    for request in trace.requests:
        chosen: int | None = None
        for generation_layer in _candidate_layers(
            request, strategy, delta_layers, dynamic_lookahead_layers,
            dynamic_min_lead_layers,
        ):
            if generation_layer < 0:
                continue
            age = request.layer - generation_layer
            if age >= coherence_time_layers:
                continue
            held_until = min(request.layer, ceil(generation_layer + coherence_time_layers))
            held_layers = range(generation_layer, held_until)
            if any(
                generation_load[(core, generation_layer)] >= generation_capacity_per_core
                for core in request.edge
            ):
                continue
            if any(
                memory_load[(core, layer)] >= compiler_memories_per_core
                for core in request.edge for layer in held_layers
            ):
                continue
            chosen = generation_layer
            for core in request.edge:
                generation_load[(core, generation_layer)] += 1
                for layer in held_layers:
                    memory_load[(core, layer)] += 1
            scheduled.append(ScheduledPreparation(request.request_id, generation_layer))
            break
        if chosen is None:
            blocked += 1
    return tuple(scheduled), blocked, max(memory_load.values(), default=0)
