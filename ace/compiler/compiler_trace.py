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


def cores_adjacent(a: int, b: int, rows: int, columns: int, topology: str = "mesh") -> bool:
    """Whether cores a and b share a link on a row-major mesh or torus."""
    (ra, ca), (rb, cb) = divmod(a, columns), divmod(b, columns)
    if not (ra < rows and rb < rows):
        return False
    dr, dc = abs(ra - rb), abs(ca - cb)
    if topology == "torus":
        dr, dc = min(dr, rows - dr), min(dc, columns - dc)
    elif topology != "mesh":
        raise ValueError(f"unknown topology {topology!r}")
    return a != b and dr + dc == 1


def validate_neighbor_requests(trace: CompilerTrace, rows: int, columns: int, topology: str = "mesh") -> None:
    for request in trace.requests:
        if not cores_adjacent(request.source_core, request.destination_core, rows, columns, topology):
            raise ValueError(
                f"request {request.request_id} is not an elementary {topology} hop: "
                f"{request.source_core}->{request.destination_core}"
            )


def config_topology(config: dict, rows: int, columns: int) -> str:
    """'torus' if the topology file joins the opposite edges of the grid with direct links, else 'mesh'."""
    links = {(c["source"], c["destination"]) for c in config["cchannels"]
             if c["source"].startswith("router") and c["destination"].startswith("router")}
    wrap = (router_name(columns - 1, columns), router_name(0, columns)) in links
    return "torus" if wrap else "mesh"


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
    lead_layers: int = 1,
) -> tuple[int, ...]:
    if strategy == "on-demand":
        return ()
    if strategy == "fixed":
        return (request.layer - delta_layers,)
    if strategy == "dynamic":
        lower = max(0, request.layer - dynamic_lookahead_layers)
        return tuple(range(request.layer - lead_layers, lower - 1, -1))
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
    lead_layers: int = 1,
    planning_mode: str = "offline",
) -> tuple[tuple[ScheduledPreparation, ...], int, int | None]:
    """Plan request-specific preparations under per-layer memory limits."""

    if planning_mode not in ("offline", "runtime"):
        raise ValueError("planning_mode must be offline or runtime")
    if compiler_memories_per_core < 0:
        raise ValueError("compiler memory capacity must be non-negative")
    if generation_capacity_per_core < 1:
        raise ValueError("generation capacity must be positive")
    if coherence_time_layers <= 0 or delta_layers < 1 or dynamic_lookahead_layers < 1:
        raise ValueError("coherence and lookahead values must be positive")
    if not 1 <= lead_layers <= dynamic_lookahead_layers:
        raise ValueError("the planner lead must lie between 1 and the lookahead")
    if strategy == "on-demand":
        return (), 0, 0
    if compiler_memories_per_core == 0:
        # Zero compiler-reserved memories is a valid experimental boundary.
        # No preparation can be admitted, so every request must fall back to
        # runtime/on-demand generation rather than aborting the experiment.
        return (), len(trace.requests), 0

    if planning_mode == "runtime":
        # These are launch candidates, not capacity reservations. Let physical
        # timecards and the unchanged per-core compiler quota admit them as
        # capacity frees. Unlike the offline planner, do not discard a request
        # just because another pair occupied its logical-layer interval.
        scheduled = []
        for request in trace.requests:
            candidates = _candidate_layers(request, strategy, delta_layers,
                                           dynamic_lookahead_layers, lead_layers)
            chosen = next((g for g in candidates
                           if g >= 0 and request.layer - g < coherence_time_layers), None)
            if chosen is not None:
                scheduled.append(ScheduledPreparation(request.request_id, chosen))
        # No offline peak exists: actual occupancy is enforced by timecards.
        return tuple(scheduled), len(trace.requests) - len(scheduled), None

    memory_load: defaultdict[tuple[int, int], int] = defaultdict(int)
    generation_load: defaultdict[tuple[int, int], int] = defaultdict(int)
    scheduled: list[ScheduledPreparation] = []
    blocked = 0
    for request in trace.requests:
        chosen: int | None = None
        for generation_layer in _candidate_layers(
            request, strategy, delta_layers, dynamic_lookahead_layers, lead_layers
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
