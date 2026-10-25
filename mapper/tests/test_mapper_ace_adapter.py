from __future__ import annotations

import json

import numpy as np

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.architecture.reliability import ReliabilityBand
from qmap.metrics.distance import DistanceOracle
from qmap.partition import Partition
from qmap.rng import SeedSequence
from tools.mapper_ace.adapter import (
    build_migration_records,
    write_adjacent_requests,
    write_migration_trace,
)
from tools.mapper_ace.export import export
from tools.mapper_ace.routing import route_path


def _architecture() -> MulticoreArchitecture:
    return MulticoreArchitecture.build(
        "2x2",
        qubits_per_core=2,
        reserved_ancilla=0,
        seed=SeedSequence.from_seed(7),
        reliability_band=ReliabilityBand(low=0.9, high=0.9),
    )


def test_routing_policies_are_explicit_and_adjacent() -> None:
    architecture = _architecture()
    oracle = DistanceOracle(architecture)
    # qmap's mesh coordinates are ordered lexicographically, so changing
    # coordinate dimension 0 first visits core 2 in this 2x2 example.
    assert route_path(architecture, oracle, 0, 3, "xy") == (0, 2, 3)
    assert route_path(architecture, oracle, 0, 3, "yx") == (0, 1, 3)
    assert route_path(architecture, oracle, 0, 3, "shortest_reliable") in {
        (0, 1, 3),
        (0, 2, 3),
    }


def test_migration_trace_is_authoritative_and_hop_export_is_derived(tmp_path) -> None:
    architecture = _architecture()
    oracle = DistanceOracle(architecture)
    partition = Partition.from_sequence(
        [np.array([3, 1], dtype=np.int32)],
        initial_assignment=np.array([0, 1], dtype=np.int32),
    )
    records = build_migration_records(partition, architecture, oracle, "xy")
    assert len(records) == 1
    assert records[0].path == (0, 2, 3)

    migration_path, count = write_migration_trace(
        records, architecture, tmp_path / "migrations.jsonl"
    )
    assert count == 1
    payload = json.loads(migration_path.read_text().splitlines()[0])
    assert payload["source_core"] == 0
    assert payload["destination_core"] == 3
    assert payload["path"] == [0, 2, 3]
    assert payload["path_hops"] == 2

    request_path, hop_count = write_adjacent_requests(
        records, partition, architecture, tmp_path / "requests.txt"
    )
    assert hop_count == 2
    request_text = request_path.read_text()
    assert "(0, 0, 2)" in request_text
    assert "(0, 2, 3)" in request_text


def test_export_writes_manifest_and_is_rerunnable(tmp_path) -> None:
    placement = tmp_path / "placement.json"
    placement.write_text(json.dumps({
        "topology": "mesh",
        "dimensions": [2, 2],
        "qubits_per_core": 2,
        "reserved_ancilla": 0,
        "seed": 7,
        "reliability_min": 0.9,
        "initial_assignment": [0, 1],
        "assignments": [[3, 1]],
    }))
    output = tmp_path / "export"
    manifest = export(placement, output, "yx")
    assert manifest["routing_policy"] == "yx"
    assert manifest["placement"]["logical_migrations"] == 1
    assert manifest["placement"]["physical_hops"] == 2
    assert (output / "migrations.jsonl").exists()
    assert (output / "requests.txt").exists()
    assert json.loads((output / "manifest.json").read_text())["input_sha256"]
