from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.metrics.distance import DistanceOracle
from qmap.partition import Partition

__all__ = ["HopRequest", "build_hop_requests", "write_request_file"]


@dataclass(frozen=True, slots=True)
class HopRequest:
    """One directed link request induced by a logical-qubit migration."""

    timeslice: int
    qubit: int
    source_core: int
    target_core: int


def build_hop_requests(
    partition: Partition,
    oracle: DistanceOracle,
) -> list[HopRequest]:
    """Expand every mapped migration into one request per physical path edge."""
    requests: list[HopRequest] = []
    for timeslice in range(partition.n_slices):
        qubits, sources, targets = partition.transition(timeslice)
        for qubit, source, target in zip(qubits, sources, targets, strict=True):
            path = oracle.route_path(int(source), int(target), partition.route_model)
            requests.extend(
                HopRequest(
                    timeslice=timeslice,
                    qubit=int(qubit),
                    source_core=hop_source,
                    target_core=hop_target,
                )
                for hop_source, hop_target in itertools.pairwise(path)
            )
    return requests


def write_request_file(
    partition: Partition,
    architecture: MulticoreArchitecture,
    oracle: DistanceOracle,
    path: Path,
) -> tuple[Path, int]:
    """Write initial placement and layer-grouped, edge-level requests as text."""
    initial = partition.initial_assignment
    if initial is None:
        initial = partition.previous_placement(0)

    requests = build_hop_requests(partition, oracle)
    by_layer: dict[int, list[HopRequest]] = defaultdict(list)
    for request in requests:
        by_layer[request.timeslice].append(request)

    lines = [
        "// Number of cores",
        str(architecture.n_cores),
        "// Number of qubit slots per core",
        str(architecture.qubits_per_core),
        "// Number of qubits",
        str(partition.n_qubits),
        "// Initial placement: (qubit, core)",
    ]
    lines.extend(f"({qubit}, {int(core)})" for qubit, core in enumerate(initial))
    lines.append("// Inter-core communication requests: (qubit, src, dst)")
    for timeslice in range(partition.n_slices):
        lines.append(f"// Layer {timeslice}")
        lines.extend(
            f"({request.qubit}, {request.source_core}, {request.target_core})"
            for request in by_layer[timeslice]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, len(requests)
