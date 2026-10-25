"""Independent check of exported routing-policy traces against the placement contract and the original file.

For every policy directory: re-import its ``requests.txt`` (which also checks contiguity, adjacency and replay),
require the replayed partition to equal the contract's, and report how its routes differ from the original trace.
    python -m tools.mapper_ace.validate_policies <dir with placement.json and policy subdirs> [--original requests.txt]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

from .adapter import import_legacy_request_file
from .placement_contract import build_architecture
from .routing import ROUTING_POLICIES


def validate(directory: Path, original: Path | None) -> dict:
    contract = json.loads((directory / "placement.json").read_text(encoding="utf-8"))
    architecture = build_architecture(tuple(contract["dimensions"]), contract["qubits_per_core"], contract["seed"],
                                      contract["reliability_min"], contract.get("reliability_max", 1.0), contract["topology"])
    expected = np.asarray(contract["assignments"], dtype=np.int32)
    base = None
    if original is not None:
        _, base_records = import_legacy_request_file(original, architecture)
        base = {(r.layer, r.qubit): r.path for r in base_records}
    report = {}
    for policy in ROUTING_POLICIES:
        requests = directory / policy / "requests.txt"
        if not requests.exists():
            continue
        partition, records = import_legacy_request_file(requests, architecture)
        replay = partition.assignments
        rows = expected.shape[0]
        padded = np.vstack([replay, np.repeat(replay[-1:], rows - replay.shape[0], axis=0)]) if replay.shape[0] < rows else replay
        entry = {
            "partition_equals_contract": bool(np.array_equal(padded, expected)
                                              and np.array_equal(partition.initial_assignment, np.asarray(contract["initial_assignment"]))),
            "logical_migrations": len(records),
            "physical_hops": sum(r.path_hops for r in records),
            "hop_histogram": dict(sorted(Counter(r.path_hops for r in records).items())),
            "max_core_relay_visits": None,
        }
        relays = Counter(core for r in records for core in r.path[1:-1])
        entry["relay_visits"] = sum(relays.values())
        entry["busiest_relay_core"] = relays.most_common(1)[0] if relays else None
        if base is not None:
            mine = {(r.layer, r.qubit): r.path for r in records}
            entry["same_keys_as_original"] = mine.keys() == base.keys()
            entry["routes_identical_to_original"] = sum(mine[k] == base[k] for k in base if k in mine)
            entry["routes_different_from_original"] = sum(mine[k] != base[k] for k in base if k in mine)
            entry["hop_count_differs_from_original"] = sum(len(mine[k]) != len(base[k]) for k in base if k in mine)
        report[policy] = entry
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--original", type=Path, default=None)
    args = parser.parse_args()
    report = validate(args.directory, args.original)
    (args.directory / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(v["partition_equals_contract"] for v in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
