"""CLI for exporting a qmap placement into the ACE trace boundary.

The input is deliberately a small JSON placement contract rather than an
implicit Python pickle. This makes mapper output portable and auditable:

``{"topology":"mesh", "dimensions":[4,4], "qubits_per_core":8,
"reserved_ancilla":0, "seed":42, "reliability_min":0.95,
"initial_assignment":[...], "assignments":[[...], ...]}``
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.architecture.reliability import ReliabilityBand
from qmap.metrics.distance import DistanceOracle
from qmap.partition import Partition
from qmap.rng import SeedSequence

from .adapter import build_migration_records, write_adjacent_requests, write_migration_trace
from .routing import ROUTING_POLICIES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_partition(path: Path) -> tuple[Partition, MulticoreArchitecture, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"topology", "dimensions", "qubits_per_core", "reserved_ancilla", "assignments"}
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"placement JSON missing fields: {', '.join(sorted(missing))}")
    seed = int(payload.get("seed", 20260519))
    reliability_min = float(payload.get("reliability_min", 1.0))
    architecture = MulticoreArchitecture.build(
        tuple(int(value) for value in payload["dimensions"]),
        qubits_per_core=int(payload["qubits_per_core"]),
        reserved_ancilla=int(payload["reserved_ancilla"]),
        seed=SeedSequence.from_seed(seed),
        reliability_band=ReliabilityBand(low=reliability_min, high=1.0),
        topology=str(payload["topology"]),
    )
    assignments = [np.asarray(row, dtype=np.int32) for row in payload["assignments"]]
    initial = payload.get("initial_assignment")
    initial_array = None if initial is None else np.asarray(initial, dtype=np.int32)
    partition = Partition.from_sequence(
        assignments,
        initial_assignment=initial_array,
        route_model="shortest",
    )
    return partition, architecture, payload


def export(input_path: Path, output_dir: Path, policy: str) -> dict[str, object]:
    partition, architecture, payload = load_partition(input_path)
    records = build_migration_records(
        partition, architecture, DistanceOracle(architecture), policy
    )
    migration_path, migration_count = write_migration_trace(
        records, architecture, output_dir / "migrations.jsonl"
    )
    request_path, hop_count = write_adjacent_requests(
        records, partition, architecture, output_dir / "requests.txt"
    )
    manifest = {
        "schema": "ace-mapper-export-v1",
        "input_sha256": _sha256(input_path),
        "migration_trace": migration_path.name,
        "request_file": request_path.name,
        "routing_policy": policy,
        "topology": architecture.describe(),
        "placement": {
            "timeslices": partition.n_slices,
            "qubits": partition.n_qubits,
            "logical_migrations": migration_count,
            "physical_hops": hop_count,
        },
        "input_parameters": payload,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="qmap placement-contract JSON")
    parser.add_argument("output", type=Path, help="directory for trace artifacts")
    parser.add_argument("--policy", choices=ROUTING_POLICIES, default="shortest_reliable")
    args = parser.parse_args()
    manifest = export(args.input, args.output, args.policy)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
