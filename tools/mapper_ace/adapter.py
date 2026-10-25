"""Convert qmap placements into auditable migration and ACE request traces."""

from __future__ import annotations

import itertools
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

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
    if dict(actual) != expected:
        raise ValueError(f"migration trace does not reproduce partition transitions: {actual!r} != {expected!r}")


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
