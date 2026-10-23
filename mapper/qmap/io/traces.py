
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from qmap.architecture.architecture import MulticoreArchitecture
from qmap.metrics.distance import DistanceOracle
from qmap.partition import Partition

__all__ = ["Transfer", "build_trace", "trace_summary", "write_trace"]

@dataclass(frozen=True, slots=True)
class Transfer:

    timeslice: int
    qubit: int
    source_core: int
    target_core: int
    source_coordinate: tuple[int, ...]
    target_coordinate: tuple[int, ...]
    hops: float
    reliability: float
    epr_latency: float
    cost: float

def build_trace(
    partition: Partition,
    architecture: MulticoreArchitecture,
    oracle: DistanceOracle,
) -> list[Transfer]:
    transfer_hops, transfer_reliability, transfer_cost = oracle.route_matrices(
        partition.route_model
    )
    transfer_epr_latency = oracle.route_epr_latency(partition.route_model)
    transfers: list[Transfer] = []
    for t in range(partition.n_slices):
        qubits, sources, targets = partition.transition(t)
        for qubit, source, target in zip(qubits, sources, targets, strict=True):
            source_index = int(source)
            target_index = int(target)
            transfers.append(
                Transfer(
                    timeslice=t,
                    qubit=int(qubit),
                    source_core=source_index,
                    target_core=target_index,
                    source_coordinate=architecture.coordinate_of(source_index),
                    target_coordinate=architecture.coordinate_of(target_index),
                    hops=float(transfer_hops[source_index, target_index]),
                    reliability=float(
                        transfer_reliability[source_index, target_index]
                    ),
                    epr_latency=float(
                        transfer_epr_latency[source_index, target_index]
                    ),
                    cost=float(transfer_cost[source_index, target_index]),
                )
            )
    return transfers

def trace_summary(
    transfers: list[Transfer], architecture: MulticoreArchitecture
) -> dict[str, object]:
    n_cores = architecture.n_cores
    outbound = [0] * n_cores
    inbound = [0] * n_cores
    for transfer in transfers:
        outbound[transfer.source_core] += 1
        inbound[transfer.target_core] += 1

    costs = [transfer.cost for transfer in transfers]
    return {
        "n_transfers": len(transfers),
        "total_cost": sum(costs),
        "mean_cost": (sum(costs) / len(costs)) if costs else 0.0,
        "max_cost": max(costs, default=0.0),
        "total_hops": sum(transfer.hops for transfer in transfers),
        "total_epr_latency": sum(transfer.epr_latency for transfer in transfers),
        "total_path_quality": sum(transfer.reliability for transfer in transfers),
        "per_core": [
            {
                "core": index,
                "coordinate": list(architecture.coordinate_of(index)),
                "outbound": outbound[index],
                "inbound": inbound[index],
                "total": outbound[index] + inbound[index],
            }
            for index in range(n_cores)
        ],
    }

def write_trace(
    transfers: list[Transfer],
    path: Path,
    *,
    summary: dict[str, object] | None = None,
) -> dict[str, Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for transfer in transfers:
            record = asdict(transfer)
            record["source_coordinate"] = list(transfer.source_coordinate)
            record["target_coordinate"] = list(transfer.target_coordinate)
            handle.write(json.dumps(record) + "\n")

    written = {"trace": path}
    if summary is not None:
        summary_path = path.with_suffix(".summary.json")
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        written["summary"] = summary_path
    return written
