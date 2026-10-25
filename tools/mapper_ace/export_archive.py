"""Export every trace of the mapper study archive under chosen routing policies, from the mapper's own partitions.

For each workload and seed the archive holds ``mapping.npz`` (the mapper's Partition).  This writes the placement contract
(provenance ``mapper-npz``, partition exact), exports it under every requested policy, and checks that re-importing each exported
hop file replays to the contract's partition.

    PYTHONPATH=mapper:. python -m tools.mapper_ace.export_archive ARCHIVE.zip OUT_DIR --policies xy yx
Output: OUT_DIR/<policy>/<workload>/seed_<n>/{requests.txt,migrations.jsonl,manifest.json} and OUT_DIR/summary.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
import zipfile
from pathlib import Path

import numpy as np

from .adapter import import_legacy_request_file
from .export import export
from .placement_contract import build_architecture, from_npz
from .routing import ROUTING_POLICIES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--policies", nargs="+", default=["xy", "yx"], choices=ROUTING_POLICIES)
    parser.add_argument("--reliability-min", type=float, default=0.1)
    parser.add_argument("--qubits-per-core", type=int, default=8)
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as scratch, zipfile.ZipFile(args.archive) as archive:
        names = sorted(n for n in archive.namelist() if n.endswith("/mapping.npz"))
        for name in names:
            workload, seed_dir = name.split("/")[-3], name.split("/")[-2]
            seed = int(seed_dir.split("_")[1])
            archive.extract(name, scratch)
            archive.extract(name.replace("mapping.npz", "requests.txt"), scratch)
            npz = Path(scratch) / name
            contract_path = args.output / "contracts" / workload / f"{seed_dir}.json"
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            payload = from_npz(npz, seed=seed, reliability_min=args.reliability_min, reliability_max=1.0,
                               qubits_per_core=args.qubits_per_core, topology="mesh")
            contract_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            expected = np.asarray(payload["assignments"], dtype=np.int32)
            architecture = build_architecture(tuple(payload["dimensions"]), args.qubits_per_core, seed, args.reliability_min)
            for policy in args.policies:
                directory = args.output / policy / workload / seed_dir
                manifest = export(contract_path, directory, policy)
                partition, records = import_legacy_request_file(directory / "requests.txt", architecture)
                replay = partition.assignments
                if replay.shape[0] < expected.shape[0]:
                    replay = np.vstack([replay, np.repeat(replay[-1:], expected.shape[0] - replay.shape[0], axis=0)])
                ok = bool(np.array_equal(replay, expected) and np.array_equal(partition.initial_assignment, np.asarray(payload["initial_assignment"])))
                rows.append({"workload": workload, "seed": seed, "policy": policy, "replay_equals_contract": ok,
                             "logical_migrations": manifest["placement"]["logical_migrations"],
                             "physical_hops": manifest["placement"]["physical_hops"], "slices": manifest["placement"]["timeslices"]})
    with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    bad = [r for r in rows if not r["replay_equals_contract"]]
    print(f"{len(rows)} exports, {len(bad)} failed replay validation")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
