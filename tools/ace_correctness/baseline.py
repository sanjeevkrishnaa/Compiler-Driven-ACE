#!/usr/bin/env python3
"""Record and check a bit-for-bit baseline of ACE's current (legacy) behaviour.

Every change to ACE's scheduler or reservation layer must leave the legacy mode
exactly as it was.  This tool makes that testable.  ``record`` runs a fixed set
of cases through ``run_trace_comparison.py`` and stores every output column as
the exact text the runner wrote.  ``check`` reruns them and compares the text
column by column, so a difference in the last digit of a float is a failure.

Subcommands
-----------
``record``           run all cases and write ``baseline.csv`` and ``manifest.json``
``check``            rerun the cases and compare with a recorded baseline
``verify-locked``    compare recorded means with ``results/compiler_repaired_validation.csv``
``verify-published`` compare recorded rows with the published ACE congestion budget study

Comparison rules
----------------
* A row is identified by (case, strategy, physics seed).
* Every column in the recorded baseline must be present in the fresh row and
  equal as text.  Columns that only the fresh run has are reported, not failed,
  so later gates may add metrics.
* A case whose input trace is unavailable is reported as SKIPPED, never silently
  dropped.  ``--strict`` turns skipped cases into a failure.

Cases that need a trace outside the repository (``--external NAME=PATH``) have
their SHA-256 verified before use.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from ace.paths import source_path
RUNNER = REPO_ROOT / "run_trace_comparison.py"
ARCHIVE = REPO_ROOT / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
ARCHIVE_PREFIX = "mqt_ten_workload_study/"
LOCKED_CSV = REPO_ROOT / "results" / "compiler_repaired_validation.csv"
PUBLISHED_CSV = REPO_ROOT / "results" / "ace_congestion_budget_2026-10-23" / "results.csv"

# The locked QFT-96 trace lives outside the repository; its hash is recorded in
# the project handoff and in docs/reports/compiler-repair-validation.md.
QFT96_SHA256 = "61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1"

ALL_STRATEGIES = ("on-demand", "fixed", "dynamic", "continuous", "adaptive-continuous")
# Source files whose hashes identify the code a baseline was recorded from.
TRACKED_SOURCES = (
    "node.py", "reservation.py", "resource_manager.py", "generation.py",
    "adaptive_continuous.py", "request_app_parallel.py", "parallel_core.py",
    "compiler_scheduler.py", "compiler_trace.py", "run_trace_comparison.py",
)

Key = tuple[str, str, str]          # (case, strategy, physics seed)


class MissingTrace(Exception):
    """A case's input trace is not available on this machine."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- cases
@dataclass(frozen=True)
class TraceSource:
    """Where a case's trace comes from.

    ``repo``     a file inside this repository
    ``archive``  a ``requests.txt`` inside the committed characterization archive
    ``external`` a file named on the command line, verified against ``expected_sha256``
    """

    kind: str
    ref: str
    expected_sha256: str | None = None

    def materialize(self, workdir: Path, externals: Mapping[str, Path]) -> tuple[Path, str]:
        """Return a readable path for the trace and its SHA-256."""
        if self.kind == "repo":
            path = REPO_ROOT / self.ref
            if not path.is_file():
                raise MissingTrace(f"{path} does not exist")
            return path, sha256_bytes(path.read_bytes())
        if self.kind == "archive":
            return self._from_archive(workdir)
        if self.kind == "external":
            path = externals.get(self.ref)
            if path is None:
                raise MissingTrace(f"no --external {self.ref}=PATH was given")
            if not path.is_file():
                raise MissingTrace(f"{path} does not exist")
            digest = sha256_bytes(path.read_bytes())
            if self.expected_sha256 and digest != self.expected_sha256:
                raise ValueError(f"{path}: SHA-256 {digest} != expected {self.expected_sha256}")
            return path, digest
        raise ValueError(f"unknown trace kind {self.kind!r}")

    def _from_archive(self, workdir: Path) -> tuple[Path, str]:
        if not ARCHIVE.is_file():
            raise MissingTrace(f"{ARCHIVE} does not exist")
        with zipfile.ZipFile(ARCHIVE) as archive:
            data = archive.read(ARCHIVE_PREFIX + self.ref)
            recorded = _archive_checksums(archive)
        digest = sha256_bytes(data)
        # The archive carries its own checksum list; use it rather than a copy of
        # the hashes in this file, and fail if the archive disagrees with itself.
        want = recorded.get(self.ref)
        if want is not None and want != digest:
            raise ValueError(f"archive member {self.ref}: SHA-256 {digest} != SHA256SUMS.csv {want}")
        target = workdir / (self.ref.replace("/", "__"))
        target.write_bytes(data)
        return target, digest


def _archive_checksums(archive: zipfile.ZipFile) -> dict[str, str]:
    raw = archive.read(ARCHIVE_PREFIX + "SHA256SUMS.csv").decode("utf-8")
    return {row["path"].replace("\\", "/"): row["sha256"] for row in csv.DictReader(raw.splitlines())}


@dataclass(frozen=True)
class Case:
    """One invocation of ``run_trace_comparison.py`` and what it must reproduce."""

    name: str
    source: TraceSource
    strategies: tuple[str, ...]
    seeds: tuple[int, ...]
    total_memories: int = 4
    compiler_memories: int = 3
    generation_capacity: int = 3
    stop_time_s: float = 300.0

    def command(self, trace: Path, output: Path) -> list[str]:
        """The exact command line; every flag is explicit so the case is self-describing."""
        return [
            sys.executable, "-B", str(RUNNER),
            "--trace", str(trace), "--mesh", "4x4",
            "--strategies", ",".join(self.strategies),
            "--seeds", ",".join(str(s) for s in self.seeds),
            "--total-memories", str(self.total_memories),
            "--compiler-memories", str(self.compiler_memories),
            "--generation-capacity", str(self.generation_capacity),
            "--delta-layers", "6", "--dynamic-lookahead-layers", "8",
            "--coherence-time-layers", "10", "--compiler-reservation-ms", "1000",
            "--stop-time-s", f"{self.stop_time_s:g}",
            "--output", str(output),
        ]


def build_cases() -> tuple[Case, ...]:
    """The baseline matrix.

    CGP and ACGP run only on Random-16: they generate continuously until the
    stop time, so on the MQT traces they cost minutes per run.
    """
    cases = [
        Case("random16", TraceSource("repo", "data/tracegen/random16_d80_seed303.txt"),
             ALL_STRATEGIES, tuple(range(10)), stop_time_s=5.0),
        Case("qft96", TraceSource("external", "qft96", QFT96_SHA256),
             ("on-demand", "fixed", "dynamic"), (0, 1, 2)),
    ]
    for workload in ("ghz", "graphstate", "draper_qft_adder", "qft", "qaoa"):
        source = TraceSource("archive", f"{workload}/seed_42/requests.txt")
        for budget in (2, 4, 32):
            partition = max(1, budget - 1)      # one memory stays with demand
            cases.append(Case(
                f"mqt-{workload}-s42-c{budget}", source, ("on-demand", "dynamic"), (0, 1, 2),
                total_memories=budget, compiler_memories=partition, generation_capacity=partition))
        cases.append(Case(f"mqt-{workload}-s42-c4-fixed", source, ("fixed",), (0, 1, 2)))
    return tuple(cases)


# --------------------------------------------------------------------------- running
def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def run_case(case: Case, trace: Path, workdir: Path, hash_seed: str | None) -> dict[Key, dict[str, str]]:
    """Run one case and return its rows keyed by (case, strategy, seed)."""
    output = workdir / f"out_{case.name}"
    env = dict(os.environ)
    if hash_seed is not None:
        env["PYTHONHASHSEED"] = hash_seed
    done = subprocess.run(case.command(trace, output), cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True)
    if done.returncode != 0:
        tail = "\n".join(done.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"case {case.name} failed (exit {done.returncode}):\n{tail}")
    with (output / "summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    expected = len(case.strategies) * len(case.seeds)
    if len(rows) != expected:
        raise RuntimeError(f"case {case.name}: expected {expected} rows, got {len(rows)}")
    keyed: dict[Key, dict[str, str]] = {}
    for row in rows:
        key = (case.name, row["strategy"], row["seed"])
        if key in keyed:
            raise RuntimeError(f"case {case.name}: duplicate row {key}")
        keyed[key] = row
    return keyed


def run_cases(
    cases: Sequence[Case], externals: Mapping[str, Path], hash_seed: str | None,
) -> tuple[dict[Key, dict[str, str]], dict[str, dict], dict[str, str]]:
    """Run every case; return (rows, per-case trace info, skipped case -> reason)."""
    rows: dict[Key, dict[str, str]] = {}
    traces: dict[str, dict] = {}
    skipped: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="ace-baseline-") as tmp:
        workdir = Path(tmp)
        for index, case in enumerate(cases, 1):
            try:
                trace, digest = case.source.materialize(workdir, externals)
            except MissingTrace as reason:
                skipped[case.name] = str(reason)
                log(f"[{index}/{len(cases)}] {case.name}: SKIPPED ({reason})")
                continue
            rows.update(run_case(case, trace, workdir, hash_seed))
            traces[case.name] = {"kind": case.source.kind, "ref": case.source.ref, "sha256": digest}
            log(f"[{index}/{len(cases)}] {case.name}: {len(case.strategies) * len(case.seeds)} rows")
    return rows, traces, skipped


# --------------------------------------------------------------------------- comparison
@dataclass(frozen=True)
class Mismatch:
    key: Key
    column: str
    recorded: str
    fresh: str


@dataclass
class Comparison:
    compared: int = 0
    identical: int = 0
    mismatches: list[Mismatch] | None = None
    missing: list[Key] | None = None
    unexpected: list[Key] | None = None
    new_columns: set[str] | None = None

    def __post_init__(self) -> None:
        self.mismatches = self.mismatches if self.mismatches is not None else []
        self.missing = self.missing if self.missing is not None else []
        self.unexpected = self.unexpected if self.unexpected is not None else []
        self.new_columns = self.new_columns if self.new_columns is not None else set()

    @property
    def ok(self) -> bool:
        return not (self.mismatches or self.missing)


def compare_rows(
    recorded: Mapping[Key, Mapping[str, str]], fresh: Mapping[Key, Mapping[str, str]],
) -> Comparison:
    """Compare recorded rows with fresh rows as exact text, column by column."""
    result = Comparison()
    for key, old in recorded.items():
        new = fresh.get(key)
        if new is None:
            result.missing.append(key)
            continue
        result.compared += 1
        differing = [Mismatch(key, column, old[column], new.get(column, "<column missing>"))
                     for column in old if new.get(column, object()) != old[column]]
        if differing:
            result.mismatches.extend(differing)
        else:
            result.identical += 1
        result.new_columns |= set(new) - set(old)
    result.unexpected = sorted(set(fresh) - set(recorded))
    return result


def report(result: Comparison, label: str) -> bool:
    print(f"{label}: {result.compared} rows compared, {result.identical} identical, "
          f"{len({m.key for m in result.mismatches})} rows with differences, "
          f"{len(result.missing)} recorded rows missing from the fresh run")
    if result.new_columns:
        print(f"  columns only in the fresh run (informational): {sorted(result.new_columns)}")
    for m in result.mismatches[:15]:
        print(f"  DIFFERS {m.key} {m.column}: recorded {m.recorded!r} fresh {m.fresh!r}")
    for key in result.missing[:15]:
        print(f"  MISSING {key}")
    print("RESULT:", "PASS" if result.ok else "FAIL")
    return result.ok


# --------------------------------------------------------------------------- manifest
def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else "unavailable"


def environment_manifest() -> dict:
    import sequence

    sequence_root = Path(sequence.__file__).resolve().parents[1]
    packages = {}
    for name in ("numpy", "scipy", "networkx", "qutip", "sequence"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not installed"
    return {
        "ace": {
            "commit": _git(REPO_ROOT, "rev-parse", "HEAD"),
            "branch": _git(REPO_ROOT, "rev-parse", "--abbrev-ref", "HEAD"),
            "tracked_files_modified": bool(_git(REPO_ROOT, "status", "--porcelain", "--untracked-files=no")),
            "source_sha256": {name: sha256_bytes(source_path(name).read_bytes()) for name in TRACKED_SOURCES},
        },
        "sequence": {
            "path": str(sequence_root),
            "commit": _git(sequence_root, "rev-parse", "HEAD"),
            "describe": _git(sequence_root, "describe", "--tags", "--always"),
            "tracked_files_modified": bool(_git(sequence_root, "status", "--porcelain", "--untracked-files=no")),
        },
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": packages,
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
    }


def environment_differences(recorded: Mapping, current: Mapping) -> list[str]:
    """Environment facts that can legitimately change results, if they differ."""
    pairs = {
        "python": (recorded.get("python"), current.get("python")),
        "numpy": (recorded.get("packages", {}).get("numpy"), current["packages"].get("numpy")),
        "scipy": (recorded.get("packages", {}).get("scipy"), current["packages"].get("scipy")),
        "sequence commit": (recorded.get("sequence", {}).get("commit"), current["sequence"]["commit"]),
    }
    return [f"{name}: recorded {old} vs now {new}" for name, (old, new) in pairs.items() if old != new]


# --------------------------------------------------------------------------- baseline files
def write_baseline(directory: Path, rows: Mapping[Key, Mapping[str, str]], manifest: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    order = {case.name: i for i, case in enumerate(build_cases())}
    strategy_order = {name: i for i, name in enumerate(ALL_STRATEGIES)}
    keys = sorted(rows, key=lambda k: (order.get(k[0], 10**6), strategy_order.get(k[1], 99), int(k[2])))
    columns = ["case", *rows[keys[0]].keys()]
    with (directory / "baseline.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for key in keys:
            writer.writerow({"case": key[0], **rows[key]})
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def read_baseline(directory: Path) -> tuple[dict[Key, dict[str, str]], dict]:
    with (directory / "baseline.csv").open(newline="", encoding="utf-8") as handle:
        rows = {(r["case"], r["strategy"], r["seed"]): {k: v for k, v in r.items() if k != "case"}
                for r in csv.DictReader(handle)}
    return rows, json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- subcommands
def select_cases(pattern: str | None) -> tuple[Case, ...]:
    cases = build_cases()
    if pattern is None:
        return cases
    chosen = tuple(c for c in cases if re.search(pattern, c.name))
    if not chosen:
        raise SystemExit(f"--only {pattern!r} matches no case; cases: {[c.name for c in cases]}")
    return chosen


def parse_externals(items: Iterable[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for item in items:
        name, separator, path = item.partition("=")
        if not separator or not name or not path:
            raise SystemExit(f"--external expects NAME=PATH, got {item!r}")
        result[name] = Path(path).expanduser()
    return result


def cmd_record(args: argparse.Namespace) -> int:
    rows, traces, skipped = run_cases(select_cases(args.only), parse_externals(args.external), args.hash_seed)
    if not rows:
        raise SystemExit("no case could run")
    manifest = environment_manifest()
    manifest["schema"] = 1
    manifest["recorded_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["traces"] = traces
    manifest["skipped"] = skipped
    write_baseline(args.output, rows, manifest)
    print(f"recorded {len(rows)} rows from {len(traces)} cases into {args.output}")
    for name, reason in skipped.items():
        print(f"SKIPPED {name}: {reason}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    recorded, manifest = read_baseline(args.golden)
    wanted = {c.name for c in select_cases(args.only)} & {key[0] for key in recorded}
    cases = tuple(c for c in build_cases() if c.name in wanted)
    rows, traces, skipped = run_cases(cases, parse_externals(args.external), args.hash_seed)
    for name, reason in skipped.items():
        print(f"SKIPPED {name}: {reason}")
    problems = [f"trace of {name} changed: recorded {manifest['traces'][name]['sha256']} now {info['sha256']}"
                for name, info in traces.items() if name in manifest["traces"]
                and manifest["traces"][name]["sha256"] != info["sha256"]]
    for line in environment_differences(manifest, environment_manifest()):
        print(f"WARNING environment differs: {line}")
    for line in problems:
        print(f"FAIL {line}")
    in_scope = {key: row for key, row in recorded.items() if key[0] in traces}
    ok = report(compare_rows(in_scope, rows), "legacy baseline") and not problems
    if skipped and args.strict:
        print("FAIL --strict: some cases were skipped")
        ok = False
    return 0 if ok else 1


def _mean(rows: Sequence[Mapping[str, str]], column: str) -> float:
    return statistics.fmean(float(r[column]) for r in rows)


def cmd_verify_locked(args: argparse.Namespace) -> int:
    recorded, _ = read_baseline(args.golden)
    names = {"Random-16": "random16", "QFT-96": "qft96"}
    failures = 0
    checked = 0
    with args.locked.open(newline="", encoding="utf-8") as handle:
        for locked in csv.DictReader(handle):
            case = names.get(locked["workload"])
            rows = [row for (c, s, _), row in recorded.items() if c == case and s == locked["strategy"]]
            if not rows:
                print(f"NOT RECORDED {locked['workload']} {locked['strategy']}")
                continue
            pairs = (("request_latency_ms_mean", "average_request_latency_ms"),
                     ("delivered_fidelity_mean", "average_delivered_epr_fidelity"),
                     ("pregenerated_success_rate_mean", "pregenerated_success_rate"))
            for locked_column, column in pairs:
                want, got = float(locked[locked_column]), _mean(rows, column)
                checked += 1
                if abs(want - got) > args.tolerance:
                    failures += 1
                    print(f"DIFFERS {locked['workload']} {locked['strategy']} {locked_column}: "
                          f"locked {want!r} recorded {got!r} (|d|={abs(want - got):.3e})")
    print(f"locked validation: {checked} means checked against {args.locked.name}, "
          f"{failures} outside tolerance {args.tolerance:g}")
    print("RESULT:", "PASS" if failures == 0 and checked else "FAIL")
    return 0 if failures == 0 and checked else 1


def cmd_verify_published(args: argparse.Namespace) -> int:
    recorded, _ = read_baseline(args.golden)
    pattern = re.compile(r"mqt-(?P<w>.+)-s42-c(?P<b>\d+)$")
    with args.published.open(newline="", encoding="utf-8") as handle:
        published = {(r["workload"], r["mapping_seed"], r["total_memories"], r["strategy"], r["seed"]): r
                     for r in csv.DictReader(handle)}
    compared = identical = absent = outside = 0
    for (case, strategy, seed), row in recorded.items():
        match = pattern.match(case)
        if not match:
            outside += 1            # a case the published study never ran, e.g. random16 or the fixed policy
            continue
        other = published.get((match["w"], "42", match["b"], strategy, seed))
        if other is None:
            absent += 1
            continue
        compared += 1
        shared = [c for c in row if c in other]
        differing = [c for c in shared if row[c] != other[c]]
        if differing:
            print(f"DIFFERS {case} {strategy} seed {seed}: {differing[:6]}")
        else:
            identical += 1
    print(f"published study: {compared} rows compared on shared columns, {identical} identical; "
          f"{absent} budget-study rows have no published counterpart; "
          f"{outside} recorded rows belong to cases the published study did not run")
    ok = compared > 0 and identical == compared
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--only", help="regex selecting case names")
        p.add_argument("--external", action="append", default=[], metavar="NAME=PATH",
                       help="trace outside the repository, e.g. qft96=/path/qft_requests.txt")
        p.add_argument("--hash-seed", help="PYTHONHASHSEED for the child runs (default: unset)")

    record = sub.add_parser("record", help="run the cases and write a baseline")
    record.add_argument("--output", type=Path, required=True)
    common(record)
    record.set_defaults(handler=cmd_record)

    check = sub.add_parser("check", help="rerun the cases and compare with a baseline")
    check.add_argument("--golden", type=Path, required=True)
    check.add_argument("--strict", action="store_true", help="fail if any case had to be skipped")
    common(check)
    check.set_defaults(handler=cmd_check)

    locked = sub.add_parser("verify-locked", help="compare a baseline with the locked validation table")
    locked.add_argument("--golden", type=Path, required=True)
    locked.add_argument("--locked", type=Path, default=LOCKED_CSV)
    locked.add_argument("--tolerance", type=float, default=1e-12)
    locked.set_defaults(handler=cmd_verify_locked)

    published = sub.add_parser("verify-published", help="compare a baseline with the published budget study")
    published.add_argument("--golden", type=Path, required=True)
    published.add_argument("--published", type=Path, default=PUBLISHED_CSV)
    published.set_defaults(handler=cmd_verify_published)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
