"""Audit every finished case against its own spec before any analysis uses it.

A case is accepted only if: its folder name is the hash of its spec; it holds exactly the requested
strategies and seeds, once each; every request completed; the physical audit found no violation; the
per-class latency breakdown reproduces the simulator's own mean; and no failure marker is left.
"""
from __future__ import annotations

import json

import experiments
from collect import DATA
from run_matrix import RUNS, case_key


def main() -> None:
    wanted = {}
    for name, build in experiments.EXPERIMENTS.items():
        for spec in build():
            wanted.setdefault(case_key(spec), (name, spec))
    problems, accepted = [], 0
    for key, (name, spec) in sorted(wanted.items()):
        folder = RUNS / key
        path = folder / "reduced.json"
        if not path.exists():
            problems.append((key, name, "not finished"))
            continue
        reduced = json.loads(path.read_text())
        if case_key(reduced["spec"]) != key or reduced["spec"] != json.loads(json.dumps(spec)):
            problems.append((key, name, "spec does not match folder"))
        pairs = [(t["strategy"], t["seed"]) for t in reduced["trials"]]
        expected = [(s, int(seed)) for s in spec["strategies"].split(",") for seed in spec["seeds"].split(",")]
        if sorted(pairs) != sorted(expected):
            problems.append((key, name, f"trials differ from spec: {len(pairs)} vs {len(expected)}"))
        if any(t["completion_rate"] != 1.0 for t in reduced["trials"]):
            problems.append((key, name, "incomplete workload"))
        if any(t["audit_violations"] for t in reduced["trials"]):
            problems.append((key, name, "audit violation"))
        if any(t["consistency_latency_error_ms"] > 1e-6 for t in reduced["trials"]):
            problems.append((key, name, "latency breakdown inconsistent"))
        if (folder / "failed.txt").exists():
            problems.append((key, name, "failure marker present"))
        accepted += not [p for p in problems if p[0] == key]
    strays = [d.name for d in RUNS.iterdir() if d.name not in wanted]
    report = dict(cases_expected=len(wanted), cases_accepted=accepted, problems=problems, folders_not_in_any_experiment=strays)
    (DATA / "audit_runs.json").write_text(json.dumps(report, indent=1))
    print(f"expected {len(wanted)} accepted {accepted} problems {len(problems)} strays {len(strays)}")
    for problem in problems[:12]:
        print(" ", problem)


if __name__ == "__main__":
    main()
