#!/usr/bin/env python3
"""Verify the vendored QM2026 (TraceGen ``qmap``) mapper against the characterization archive.

The archive ``results/congestion/mqt_ten_workload_congestion_results.zip`` holds the
mapped traces that every congestion study in this repository consumes.  Two checks
tie this folder to those traces.

``sources``
    Every ``qmap/*.py`` file here hashes to the value the pipeline recorded in the
    archive's ``study.json`` when the archived traces were generated.

``outputs``
    A fresh pipeline run (``tools/congestion_study/run_study.py --mapper-dir mapper``)
    reproduces every archived per-trial file.  Each permitted difference is checked,
    never skipped:

    * line endings -- the archive was produced on Windows (CRLF);
    * file-hash fields -- ``trace_sha256`` and ``normalized_circuit_sha256`` must each
      equal the SHA-256 of their own file, in the archive and in the fresh run;
    * wall-clock and environment fields -- ``seconds``, ``runtime_seconds``,
      ``versions.python`` and ``source.factory_source``;
    * floating-point values in JSON summaries, within ``--max-ulp`` units in the last
      place.

    Any other difference is a mismatch and fails the check.

Usage::

    python mapper/verification/verify_mapper.py sources
    python mapper/verification/verify_mapper.py outputs --fresh <run_study.py --output folder>
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = REPO_ROOT / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
DEFAULT_MAPPER = REPO_ROOT / "mapper"

TEXT_SUFFIXES = {".qasm", ".txt", ".csv", ".html", ".svg", ".md"}
# JSON field -> the trial file whose SHA-256 it records (verified against the archive).
HASH_FIELDS = {"trace_sha256": "requests.txt", "normalized_circuit_sha256": "circuit.qasm"}
ENVIRONMENT_FIELDS = {"seconds", "runtime_seconds", "versions.python", "source.factory_source"}
TRIAL_PATH = re.compile(r"^(?P<workload>[^/]+)/seed_(?P<seed>\d+)/(?P<name>[^/]+)$")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ulp_distance(a: float, b: float) -> int:
    """Number of representable float64 values between a and b (0 when equal)."""
    if a == b:
        return 0
    return abs(int(np.float64(a).view(np.int64)) - int(np.float64(b).view(np.int64)))


def json_leaf_differences(old, new, path: str = ""):
    """Yield ``(dotted_path, old_value, new_value)`` for every differing JSON leaf."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            yield from json_leaf_differences(old.get(key), new.get(key), f"{path}.{key}" if path else key)
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for index, (a, b) in enumerate(zip(old, new)):
            yield from json_leaf_differences(a, b, f"{path}[{index}]")
    elif old != new:
        yield path, old, new


class Archive:
    """Read-only view of the characterization archive."""

    def __init__(self, path: Path) -> None:
        self.zip = zipfile.ZipFile(path)
        study = [n for n in self.zip.namelist() if n.endswith("/study.json") and n.count("/") == 1]
        if len(study) != 1:
            raise ValueError(f"{path}: expected exactly one top-level study.json, found {len(study)}")
        self.prefix = study[0][: -len("study.json")]

    def read(self, relative: str) -> bytes:
        return self.zip.read(self.prefix + relative)

    def study(self) -> dict:
        return json.loads(self.read("study.json"))

    def trial_files(self) -> list[str]:
        names = (n[len(self.prefix):] for n in self.zip.namelist() if n.startswith(self.prefix))
        return sorted(n for n in names if TRIAL_PATH.match(n))


def check_sources(archive: Archive, mapper_dir: Path) -> int:
    recorded = {k.replace("\\", "/"): v for k, v in archive.study()["mapper_source_sha256"].items()}
    present = {p.relative_to(mapper_dir).as_posix(): sha256(p.read_bytes())
               for p in sorted((mapper_dir / "qmap").rglob("*.py"))}
    identical = sorted(k for k in recorded if present.get(k) == recorded[k])
    differ = sorted(k for k in recorded if k in present and present[k] != recorded[k])
    missing = sorted(set(recorded) - set(present))
    extra = sorted(set(present) - set(recorded))
    print(f"qmap source files recorded when the archived traces were generated: {len(recorded)}")
    print(f"  identical: {len(identical)}   different: {len(differ)}   "
          f"missing here: {len(missing)}   present but unrecorded: {len(extra)}")
    for label, items in (("DIFFERENT", differ), ("MISSING", missing), ("UNRECORDED", extra)):
        for item in items:
            print(f"  {label}: {item}")
    ok = not (differ or missing or extra)
    print("RESULT:", "PASS -- this folder is the code that generated the archive" if ok else "FAIL")
    return 0 if ok else 1


@dataclass
class OutputReport:
    identical: Counter = field(default_factory=Counter)      # byte-identical, per file name
    equivalent: Counter = field(default_factory=Counter)     # equal up to permitted differences
    mismatched: list = field(default_factory=list)           # (trial file, reason)
    permitted: Counter = field(default_factory=Counter)      # permitted difference, by category
    max_ulp: int = 0


def compare_json(archive: Archive, fresh: Path, relative: str, old: bytes, new: bytes,
                 max_ulp: int, report: OutputReport) -> bool:
    trial_dir = relative.rsplit("/", 1)[0]
    clean = True
    for path, a, b in json_leaf_differences(json.loads(old), json.loads(new)):
        leaf = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if leaf in HASH_FIELDS:
            target = f"{trial_dir}/{HASH_FIELDS[leaf]}"
            if a == sha256(archive.read(target)) and b == sha256((fresh / target).read_bytes()):
                report.permitted[f"{leaf} (matches its own file)"] += 1
                continue
            reason = f"{path}: does not match the SHA-256 of {HASH_FIELDS[leaf]}"
        elif path in ENVIRONMENT_FIELDS or leaf in ENVIRONMENT_FIELDS:
            report.permitted[f"environment: {path}"] += 1
            continue
        elif isinstance(a, float) and isinstance(b, float):
            distance = ulp_distance(a, b)
            report.max_ulp = max(report.max_ulp, distance)
            if distance <= max_ulp:
                report.permitted["float within ULP tolerance"] += 1
                continue
            reason = f"{path}: {a!r} vs {b!r} ({distance} ULP)"
        else:
            reason = f"{path}: {a!r} vs {b!r}"
        report.mismatched.append((relative, reason))
        clean = False
    return clean


def compare_npz(old: bytes, new: bytes) -> str | None:
    a, b = np.load(io.BytesIO(old)), np.load(io.BytesIO(new))
    if sorted(a.files) != sorted(b.files):
        return f"array names differ: {sorted(a.files)} vs {sorted(b.files)}"
    for key in a.files:
        if a[key].shape != b[key].shape or a[key].dtype != b[key].dtype or not np.array_equal(a[key], b[key]):
            return f"array {key!r} differs"
    return None


def check_outputs(archive: Archive, fresh: Path, max_ulp: int) -> int:
    report = OutputReport()
    trial_files = archive.trial_files()
    for relative in trial_files:
        name = relative.rsplit("/", 1)[1]
        target = fresh / relative
        if not target.exists():
            report.mismatched.append((relative, "missing from the fresh run"))
            continue
        old, new = archive.read(relative), target.read_bytes()
        if old == new:
            report.identical[name] += 1
            continue
        suffix = Path(name).suffix
        if suffix in TEXT_SUFFIXES:
            if old.replace(b"\r\n", b"\n") == new.replace(b"\r\n", b"\n"):
                report.permitted["line endings (CRLF vs LF)"] += 1
                report.equivalent[name] += 1
            else:
                report.mismatched.append((relative, "content differs after normalising line endings"))
        elif suffix == ".npz":
            reason = compare_npz(old, new)
            if reason is None:
                report.permitted["npz container bytes (arrays identical)"] += 1
                report.equivalent[name] += 1
            else:
                report.mismatched.append((relative, reason))
        elif suffix == ".json":
            if compare_json(archive, fresh, relative, old, new, max_ulp, report):
                report.equivalent[name] += 1
        else:
            report.mismatched.append((relative, "binary content differs"))

    trials = {relative.rsplit("/", 1)[0] for relative in trial_files}
    names = sorted({relative.rsplit("/", 1)[1] for relative in trial_files})
    print(f"archived trials: {len(trials)}   archived per-trial files: {len(trial_files)}")
    print(f"\n{'file':26s} {'byte-identical':>14s} {'equivalent':>11s} {'mismatched':>11s}")
    mismatched_by_name = Counter(rel.rsplit("/", 1)[1] for rel, _ in report.mismatched)
    for name in names:
        print(f"{name:26s} {report.identical[name]:14d} {report.equivalent[name]:11d} {mismatched_by_name[name]:11d}")
    print("\npermitted differences found (each one checked):")
    for category, count in sorted(report.permitted.items()):
        print(f"  {count:6d}  {category}")
    print(f"  largest float difference observed: {report.max_ulp} ULP (tolerance {max_ulp})")
    for relative, reason in report.mismatched[:25]:
        print(f"  MISMATCH {relative}: {reason}")
    ok = not report.mismatched
    print("RESULT:", "PASS -- the fresh run reproduces every archived trial" if ok
          else f"FAIL -- {len(report.mismatched)} mismatches")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE, help="characterization archive (.zip)")
    sub = parser.add_subparsers(dest="command", required=True)
    sources = sub.add_parser("sources", help="compare qmap/*.py with the hashes recorded in the archive")
    sources.add_argument("--mapper-dir", type=Path, default=DEFAULT_MAPPER)
    outputs = sub.add_parser("outputs", help="compare a fresh pipeline run with the archived trials")
    outputs.add_argument("--fresh", type=Path, required=True, help="the --output folder of run_study.py")
    outputs.add_argument("--max-ulp", type=int, default=16, help="float tolerance in units in the last place")
    args = parser.parse_args(argv)
    archive = Archive(args.archive)
    if args.command == "sources":
        return check_sources(archive, args.mapper_dir)
    return check_outputs(archive, args.fresh, args.max_ulp)


if __name__ == "__main__":
    sys.exit(main())
