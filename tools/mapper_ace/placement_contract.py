"""Write the placement JSON contract that ``export.py`` consumes.

A placement is the mapper's :class:`qmap.partition.Partition`: ``assignments[t][q]`` is the core of
qubit ``q`` after timeslice ``t`` and ``initial_assignment[q]`` is its core before slice 0.  A migration
``(qubit, source, destination)`` at slice ``t`` is ``Partition.transition(t)``.

Two sources are supported, and the contract records which one was used:

``npz``
    ``mapping.npz`` written by the mapper study (arrays ``initial``, ``placements``, ``mesh``).  This is
    the mapper's own partition, so nothing is inferred.
``legacy``
    A legacy ACE request file.  Each layer's hop chains give every moved qubit's final core, and every
    other qubit stays where it was, so replaying the file rebuilds the partition exactly (checked
    against ``mapping.npz`` for all 30 archived 48-qubit traces).  Layers the file declares but leaves
    empty are kept as static slices because ACE spends a fixed gap on each empty layer.  What a legacy
    file cannot give is the mapper's reliability map: it is rebuilt from the seed and band passed in.

    python -m tools.mapper_ace.placement_contract npz mapping.npz out.json --seed 42
    python -m tools.mapper_ace.placement_contract legacy requests.txt out.json --seed 42
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.architecture.reliability import ReliabilityBand
from qmap.partition import Partition
from qmap.rng import SeedSequence

from .adapter import import_legacy_request_file

SCHEMA = "ace-placement-contract-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_architecture(
    dimensions: tuple[int, ...],
    qubits_per_core: int,
    seed: int,
    reliability_min: float,
    reliability_max: float = 1.0,
    topology: str = "mesh",
) -> MulticoreArchitecture:
    return MulticoreArchitecture.build(
        tuple(int(d) for d in dimensions),
        qubits_per_core=qubits_per_core,
        reserved_ancilla=0,
        seed=SeedSequence.from_seed(seed),
        reliability_band=ReliabilityBand(low=reliability_min, high=reliability_max),
        topology=topology,
    )


def contract(
    partition: Partition,
    *,
    dimensions: tuple[int, ...],
    qubits_per_core: int,
    seed: int,
    reliability_min: float,
    reliability_max: float,
    topology: str,
    provenance: dict,
) -> dict:
    initial = partition.initial_assignment
    if initial is None:
        raise ValueError("a placement contract needs the initial (pre-slice-0) placement")
    return {
        "schema": SCHEMA,
        "topology": topology,
        "dimensions": [int(d) for d in dimensions],
        "qubits_per_core": int(qubits_per_core),
        "reserved_ancilla": 0,
        "seed": int(seed),
        "reliability_min": float(reliability_min),
        "reliability_max": float(reliability_max),
        "initial_assignment": [int(c) for c in initial],
        "assignments": [[int(c) for c in row] for row in partition.assignments],
        "provenance": provenance,
    }


def from_npz(path: Path, *, seed: int, reliability_min: float, reliability_max: float,
             qubits_per_core: int, topology: str) -> dict:
    data = np.load(path, allow_pickle=False)
    dimensions = tuple(int(d) for d in data["mesh"])
    partition = Partition.from_sequence(
        [np.asarray(row, dtype=np.int32) for row in data["placements"]],
        initial_assignment=np.asarray(data["initial"], dtype=np.int32),
    )
    return contract(
        partition, dimensions=dimensions, qubits_per_core=qubits_per_core, seed=seed,
        reliability_min=reliability_min, reliability_max=reliability_max, topology=topology,
        provenance={"kind": "mapper-npz", "source": path.name, "source_sha256": _sha256(path),
                    "mapper_partition_exact": True},
    )


def declared_layers(path: Path) -> int:
    return len(re.findall(r"^// Layer \d+", path.read_text(encoding="utf-8"), flags=re.M))


def from_legacy(path: Path, *, dimensions: tuple[int, ...], qubits_per_core: int, seed: int,
                reliability_min: float, reliability_max: float, topology: str) -> dict:
    architecture = build_architecture(dimensions, qubits_per_core, seed, reliability_min, reliability_max, topology)
    partition, records = import_legacy_request_file(path, architecture)
    rows = [np.asarray(row, dtype=np.int32) for row in partition.assignments]
    declared = declared_layers(path)
    padded = max(0, declared - len(rows))
    rows += [rows[-1].copy()] * padded                      # empty layers: nobody moves
    padded_partition = Partition.from_sequence(rows, initial_assignment=partition.initial_assignment)
    return contract(
        padded_partition, dimensions=dimensions, qubits_per_core=qubits_per_core, seed=seed,
        reliability_min=reliability_min, reliability_max=reliability_max, topology=topology,
        provenance={"kind": "legacy-request-replay", "source": path.name, "source_sha256": _sha256(path),
                    "mapper_partition_exact": False,
                    "note": "placement rebuilt by replaying hop chains; reliability map rebuilt from seed and band",
                    "layers_declared": declared, "layers_with_requests": partition.n_slices,
                    "empty_trailing_layers_added": padded, "legacy_logical_migrations": len(records)},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kind", choices=("npz", "legacy"))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, required=True, help="architecture (reliability map) seed")
    parser.add_argument("--reliability-min", type=float, default=0.1)
    parser.add_argument("--reliability-max", type=float, default=1.0)
    parser.add_argument("--qubits-per-core", type=int, default=8)
    parser.add_argument("--dimensions", type=int, nargs=2, default=(4, 4), help="legacy only; npz carries its own")
    parser.add_argument("--topology", default="mesh", choices=("mesh", "torus"))
    args = parser.parse_args()
    common = dict(seed=args.seed, reliability_min=args.reliability_min, reliability_max=args.reliability_max,
                  qubits_per_core=args.qubits_per_core, topology=args.topology)
    payload = (from_npz(args.source, **common) if args.kind == "npz"
               else from_legacy(args.source, dimensions=tuple(args.dimensions), **common))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("schema", "topology", "dimensions", "seed", "provenance")}, indent=2))
    print(f"slices {len(payload['assignments'])} qubits {len(payload['initial_assignment'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
