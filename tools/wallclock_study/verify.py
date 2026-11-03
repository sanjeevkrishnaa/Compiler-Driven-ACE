"""Check every finished run of the wall-clock study against the intended specification.

A run passes only if, for every seed: the summary exists with the expected seeds, all requests completed, the physical
audit found no violation, and the recorded parameters equal the spec (4 memories, efficiency-0.8 config, the frozen
trace, the expected planner).  Prints one line per failing run; exit status 1 if anything fails.

    python tools/wallclock_study/verify.py
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "output" / "wallclock_study" / "runs"
TRACES = ROOT / "results" / "wallclock_2026-11-03" / "traces"
CONFIG = ROOT / "config" / "final_config" / "grid_4x4_ace_3.json"
SEEDS = {60, 61, 62, 63}
FOLDERS = {"v0_layer": ("layer", ("on-demand", "dynamic")), "v2_time": ("time", ("dynamic",)),
           "v3_cgp": (None, ("continuous", "adaptive-continuous"))}


def main() -> int:
    efficiency = json.loads(CONFIG.read_text())["templates"]["adaptive_protocol"]["MemoryArray"]["efficiency"]
    limit = json.loads((RUNS / "cgp_tune_choice.json").read_text())["chosen"]
    problems, checked = [], 0
    if efficiency != 0.8:
        problems.append(f"config memory efficiency is {efficiency}, not 0.8")
    for folder, (planner, strategies) in FOLDERS.items():
        for run in sorted((RUNS / folder).glob("*_*_*")):
            strategy = stem = None
            for s in strategies:
                if run.name.endswith("_" + s):
                    strategy = s
                    stem = run.name[: -len(s) - 1]
            if strategy is None:
                problems.append(f"{folder}/{run.name}: stray run that does not belong in this folder")
                continue
            route = stem.rsplit("_", 1)[1]
            workload = stem.rsplit("_", 1)[0]
            checked += 1
            tag = f"{folder}/{run.name}"
            try:
                rows = list(csv.DictReader((run / "summary.csv").open()))
                meta = json.loads((run / "metadata.json").read_text())
            except FileNotFoundError:
                problems.append(f"{tag}: summary or metadata missing")
                continue
            if {int(r["seed"]) for r in rows} != SEEDS:
                problems.append(f"{tag}: seeds {sorted(int(r['seed']) for r in rows)}")
            for r in rows:
                audit = json.loads((run / f"audit_{strategy}_{r['seed']}.json").read_text())
                if float(r["completion_rate"]) != 1 or audit["violations"] or audit["completed_requests"] != audit["total_requests"]:
                    problems.append(f"{tag} seed {r['seed']}: completion {r['completion_rate']} violations {len(audit['violations'])}")
            p = meta["parameters"]
            if p["total_memories"] != 4:
                problems.append(f"{tag}: total_memories {p['total_memories']}")
            if Path(p["config"]) != CONFIG:
                problems.append(f"{tag}: config {p['config']}")
            if Path(p["trace"]) != TRACES / workload / route / "requests.txt":
                problems.append(f"{tag}: trace {p['trace']}")
            if strategy == "dynamic" and (p["compiler_memories"] != 4 or p["dynamic_planner"] != planner):
                problems.append(f"{tag}: compiler_memories {p['compiler_memories']} planner {p['dynamic_planner']}")
            if folder == "v3_cgp" and p.get("compiler_memories") != limit:
                problems.append(f"{tag}: cache limit {p.get('compiler_memories')} but the rule chose {limit}")
            if p.get("allow_incomplete_audit") or not p.get("audit_events"):
                problems.append(f"{tag}: audit not enforced")
            if folder == "v3_cgp" and not p.get("autonomous_cache_follows_compiler_memories"):
                problems.append(f"{tag}: autonomous cache limit is not tied to the chosen limit")
    print(f"checked {checked} runs, {len(problems)} problems")
    for line in problems:
        print("  ", line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
