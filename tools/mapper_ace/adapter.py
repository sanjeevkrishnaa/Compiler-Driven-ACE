"""Convert qmap placements into auditable migration and ACE request traces."""

from __future__ import annotations

import itertools
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

import numpy as np

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.metrics.distance import DistanceOracle
from qmap.partition import Partition

from .routing import route_path, validate_path

SCHEMA = "ace-migration-v2"


@dataclass(frozen=True, slots=True)
class MigrationRecord:
    migration_id: str
    layer: int
    qubit: int
    source_core: int
    destination_core: int
    path: tuple[int, ...]
    route_policy: str
    topology: str

    @property
    def path_hops(self) -> int:
        return len(self.path) - 1

    def to_json(self, architecture: MulticoreArchitecture) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            **asdict(self),
            "path": list(self.path),
            "source_coordinate": list(architecture.coordinate_of(self.source_core)),
            "destination_coordinate": list(
                architecture.coordinate_of(self.destination_core)
            ),
            "path_hops": self.path_hops,
        }


def build_migration_records(
    partition: Partition,
    architecture: MulticoreArchitecture,
    oracle: DistanceOracle,
    policy: str,
) -> list[MigrationRecord]:
    """Build one record per logical migration, without expanding it into hops."""
    records: list[MigrationRecord] = []
    sequence = 0
    for layer in range(partition.n_slices):
        qubits, sources, destinations = partition.transition(layer)
        for qubit, source, destination in zip(qubits, sources, destinations, strict=True):
            source_i, destination_i = int(source), int(destination)
            path = route_path(architecture, oracle, source_i, destination_i, policy)
            records.append(
                MigrationRecord(
                    migration_id=f"m{sequence:06d}",
                    layer=layer,
                    qubit=int(qubit),
                    source_core=source_i,
                    destination_core=destination_i,
                    path=path,
                    route_policy=policy,
                    topology=architecture.label,
                )
            )
            sequence += 1
    validate_migration_records(partition, architecture, records)
    return records


def validate_migration_records(
    partition: Partition,
    architecture: MulticoreArchitecture,
    records: list[MigrationRecord],
) -> None:
    """Check paths and replay every migration against the mapped placements."""
    expected: dict[int, list[tuple[int, int, int]]] = {}
    for layer in range(partition.n_slices):
        qubits, sources, destinations = partition.transition(layer)
        expected[layer] = [
            (int(q), int(s), int(d))
            for q, s, d in zip(qubits, sources, destinations, strict=True)
        ]
    actual: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for record in records:
        if record.topology != architecture.label:
            raise ValueError(f"{record.migration_id} has topology {record.topology!r}")
        validate_path(architecture, record.path, record.source_core, record.destination_core)
        actual[record.layer].append(
            (record.qubit, record.source_core, record.destination_core)
        )
    normalized_actual = {layer: actual.get(layer, []) for layer in expected}
    if normalized_actual != expected:
        raise ValueError(
            "migration trace does not reproduce partition transitions: "
            f"{normalized_actual!r} != {expected!r}"
        )


def write_migration_trace(
    records: list[MigrationRecord],
    architecture: MulticoreArchitecture,
    path: Path,
) -> tuple[Path, int]:
    """Write authoritative migration-level JSONL trace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.to_json(architecture), sort_keys=True) + "\n")
    return path, len(records)


def import_legacy_request_file(
    path: Path,
    architecture: MulticoreArchitecture,
) -> tuple[Partition, list[MigrationRecord]]:
    """Import an existing ACE request file without changing its chosen paths.

    Legacy files contain only adjacent `(qubit, source, destination)` requests.
    Consecutive hops for the same qubit in a layer are joined into one logical
    migration. The importer is intentionally conservative: a qubit may have
    only one contiguous path per layer, and every hop must be physically
    adjacent. The returned synthetic partition captures the placement replay;
    it is useful for archival conversion, not as a replacement for the mapper's
    original circuit placement artifact.
    """
    metadata: dict[str, int] = {}
    initial: dict[int, int] = {}
    layer_hops: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    pending: str | None = None
    section: str | None = None
    layer: int | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if lower == "// number of cores":
            pending, section = "core_count", None
            continue
        if lower == "// number of qubit slots per core":
            pending, section = "qubit_slots_per_core", None
            continue
        if lower == "// number of qubits":
            pending, section = "qubit_count", None
            continue
        if lower.startswith("// initial placement"):
            section, pending = "placement", None
            continue
        if lower.startswith("// inter-core communication requests"):
            section, pending = "requests", None
            continue
        if lower.startswith("// layer "):
            layer = int(lower.split()[-1])
            section = "requests"
            continue
        if lower.startswith("//"):
            continue
        values = tuple(int(value.strip()) for value in line.strip("()").split(","))
        if pending is not None:
            metadata[pending] = values[0] if len(values) == 1 else int(line)
            pending = None
        elif section == "placement":
            if len(values) != 2:
                raise ValueError(f"invalid placement tuple in {path}: {line}")
            initial[values[0]] = values[1]
        elif section == "requests" and layer is not None:
            if len(values) != 3:
                raise ValueError(f"invalid request tuple in {path}: {line}")
            layer_hops[layer].append(values)
        else:
            raise ValueError(f"tuple outside a recognized section in {path}: {line}")
    required = {"core_count", "qubit_slots_per_core", "qubit_count"}
    if required - metadata.keys() or set(initial) != set(range(metadata.get("qubit_count", 0))):
        raise ValueError(f"legacy request file lacks complete metadata/placement: {path}")
    placement = dict(initial)
    records: list[MigrationRecord] = []
    migration_number = 0
    assignments: list[list[int]] = []
    for layer_index in range(max(layer_hops, default=-1) + 1):
        grouped: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for qubit, source, destination in layer_hops.get(layer_index, []):
            grouped[qubit].append((source, destination))
        for qubit, hops in grouped.items():
            if placement[qubit] != hops[0][0]:
                raise ValueError(
                    f"layer {layer_index} qubit {qubit} starts at {hops[0][0]}, "
                    f"but replay placement is {placement[qubit]}"
                )
            path_cores = [hops[0][0]]
            for source, destination in hops:
                if source != path_cores[-1]:
                    raise ValueError(f"non-contiguous legacy path for qubit {qubit}")
                validate_path(architecture, (source, destination), source, destination)
                path_cores.append(destination)
            placement[qubit] = path_cores[-1]
            records.append(MigrationRecord(
                migration_id=f"m{migration_number:06d}", layer=layer_index,
                qubit=qubit, source_core=path_cores[0],
                destination_core=path_cores[-1], path=tuple(path_cores),
                route_policy="mapper-imported", topology=architecture.label,
            ))
            migration_number += 1
        assignments.append([placement[q] for q in range(metadata["qubit_count"])])
    partition = Partition.from_sequence(
        [np.asarray(row, dtype=np.int32) for row in (assignments or [list(initial)])],
        initial_assignment=np.asarray([initial[q] for q in range(metadata["qubit_count"])], dtype=np.int32),
    )
    validate_migration_records(partition, architecture, records)
    return partition, records


def _write_request_header(handle: TextIO, partition: Partition, architecture: MulticoreArchitecture) -> None:
    initial = partition.initial_assignment
    if initial is None:
        initial = partition.previous_placement(0)
    handle.write("// Number of cores\n")
    handle.write(f"{architecture.n_cores}\n")
    handle.write("// Number of qubit slots per core\n")
    handle.write(f"{architecture.qubits_per_core}\n")
    handle.write("// Number of qubits\n")
    handle.write(f"{partition.n_qubits}\n")
    handle.write("// Initial placement: (qubit, core)\n")
    for qubit, core in enumerate(initial):
        handle.write(f"({qubit}, {int(core)})\n")
    handle.write("// Inter-core communication requests: (qubit, src, dst)\n")


def write_adjacent_requests(
    records: list[MigrationRecord],
    partition: Partition,
    architecture: MulticoreArchitecture,
    path: Path,
) -> tuple[Path, int]:
    """Write legacy requests with the architecture metadata required by ACE."""
    by_layer: dict[int, list[MigrationRecord]] = defaultdict(list)
    for record in records:
        by_layer[record.layer].append(record)
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        _write_request_header(handle, partition, architecture)
        for layer in range(partition.n_slices):
            handle.write(f"// Layer {layer}\n")
            for record in by_layer[layer]:
                for source, destination in itertools.pairwise(record.path):
                    handle.write(f"({record.qubit}, {source}, {destination})\n")
                    count += 1
    return path, count
