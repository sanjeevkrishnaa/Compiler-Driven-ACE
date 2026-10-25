#!/usr/bin/env python3
"""Import a declared circuit corpus into a Golden-study directory.

The source archive is *input evidence*, not a Golden-study result.  The tool
extracts only the QASM members named by ``mapping_inputs.json`` and records both
the archive-member and extracted-file SHA-256 digests.  It deliberately never
guesses workload names, archive paths, or source files.

    python -m tools.golden_study.prepare_inputs \
      --root results/golden_study_2026-10-25
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_spec(spec: dict[str, Any]) -> list[dict[str, str]]:
    archive = spec.get("source_archive")
    workloads = spec.get("workloads")
    if not isinstance(archive, str) or not archive:
        raise ValueError("mapping input spec needs a non-empty source_archive")
    if not isinstance(workloads, list) or not workloads:
        raise ValueError("mapping input spec needs a non-empty workloads list")
    normalized: list[dict[str, str]] = []
    identifiers: set[str] = set()
    members: set[str] = set()
    for value in workloads:
        if not isinstance(value, dict):
            raise ValueError("every mapping input must be an object")
        identifier = value.get("id")
        member = value.get("archive_member")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("every mapping input needs a non-empty id")
        if not isinstance(member, str) or not member.endswith(".qasm"):
            raise ValueError(f"mapping input {identifier!r} needs a .qasm archive_member")
        if identifier in identifiers:
            raise ValueError(f"duplicate workload id {identifier!r}")
        if member in members:
            raise ValueError(f"duplicate archive member {member!r}")
        identifiers.add(identifier)
        members.add(member)
        normalized.append({"id": identifier, "archive_member": member})
    return normalized


def prepare(root: Path, spec_path: Path, *, overwrite: bool) -> Path:
    spec = read_json(spec_path)
    workloads = validate_spec(spec)
    archive = (root / spec["source_archive"]).resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"declared source archive does not exist: {archive}")
    output = root / "inputs"
    output.mkdir(parents=True, exist_ok=True)
    source_root = root.resolve()
    try:
        archive.relative_to(source_root)
    except ValueError as exc:
        raise ValueError("source_archive must be inside the Golden-study root") from exc

    archive_hash = sha256_file(archive)
    entries: list[dict[str, str]] = []
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        missing = [row["archive_member"] for row in workloads if row["archive_member"] not in names]
        if missing:
            raise ValueError("archive misses declared QASM members: " + ", ".join(missing))
        for row in workloads:
            payload = bundle.read(row["archive_member"])
            target = output / row["id"] / "circuit.qasm"
            if target.exists() and not overwrite:
                if target.read_bytes() != payload:
                    raise FileExistsError(
                        f"refusing to overwrite non-matching input {target}; use --overwrite explicitly"
                    )
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            entries.append({
                "id": row["id"],
                "source_archive_member": row["archive_member"],
                "source_member_sha256": sha256_bytes(payload),
                "qasm_path": str(target.relative_to(root)),
                "qasm_sha256": sha256_file(target),
            })
    manifest = {
        "schema": "golden-study-input-corpus-v1",
        "source_archive": str(archive.relative_to(root)),
        "source_archive_sha256": archive_hash,
        "inputs": entries,
    }
    target = output / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--spec", type=Path, help="defaults to <root>/mapping_inputs.json")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing non-matching extracted input")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = prepare(root, (args.spec or root / "mapping_inputs.json").resolve(), overwrite=args.overwrite)
    print(f"wrote {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
