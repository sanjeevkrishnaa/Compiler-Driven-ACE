#!/usr/bin/env python3
"""Which timer discards a cached pair, and what does ACE do next?  Runs with the invariant monitor and counts events.

ACE has three timers that can end the life of a cached (pre-generated) pair, plus the planner's assumption:
  * the memory *cut-off*:  SeQUeNCe ``Memory.cutoff_ratio`` x ``coherence_time`` after the pair is made, the memory is reset
    and the resource manager returns it to RAW (ACE then drops the pair from its cache and reports it expired);
  * the reservation window: a compiler pair's one-shot reservation ends ``compiler_reservation_ms`` after it starts and the
    booking is released with reason ``reservation_expired``;
  * continuous decoherence: the stored state decays at rate 1/coherence_time, but nothing is discarded by it;
  * the planner's ``--coherence-time-layers``: how many layers ahead it will prepare a pair (a planning assumption only).

    python tools/cutoff_study/mechanism.py --output out.csv
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "ace_correctness"))
sys.path.insert(0, str(REPO))
from audit_trace import DEFAULT_CONFIG, audit_trace                               # noqa: E402
from execution_events import Booked, PairCredited, PairDelivered, Unbooked       # noqa: E402

ARCHIVE = REPO / "results" / "congestion" / "mqt_ten_workload_congestion_results.zip"
PREFIX = "mqt_ten_workload_study"
# name, config overrides on the memory array, compiler reservation window (ms)
CASES = [
    ("ACE default: cut-off = coherence time (1 s), window 1000 ms", {}, 1000),
    ("short reservation window only (20 ms)", {}, 20),
    ("cut-off ratio 0.02 (20 ms), window 1000 ms", {"cutoff_ratio": 0.02}, 1000),
    ("cut-off ratio 0.005 (5 ms), window 1000 ms", {"cutoff_ratio": 0.005}, 1000),
    ("cut-off ratio 0.02 and window 20 ms", {"cutoff_ratio": 0.02}, 20),
]
FIELDS = ["workload", "case", "completed", "requested", "violations", "violation_kinds", "makespan_ms",
          "adaptive_bookings", "released_consumed", "released_reservation_expired", "released_removed",
          "pairs_delivered", "pairs_credited", "memory_expiry_resets"]


def variant_config(directory: Path, overrides: dict) -> Path:
    config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
    config["templates"]["adaptive_protocol"]["MemoryArray"].update(overrides)
    path = directory / f"config_{'_'.join(f'{k}{v}' for k, v in sorted(overrides.items())) or 'default'}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def run_case(trace: Path, workload: str, name: str, overrides: dict, window_ms: float, memories: int, scheduler: str) -> dict:
    from sequence.components.memory import Memory
    resets = {"n": 0}
    original = Memory.expire

    def counting(self):
        # SeQUeNCe removes a memory's scheduled expiry when the pair is consumed or the memory is reset, so a call that
        # reaches here with the memory not in an application is a cut-off discard
        if not self.is_in_application:
            resets["n"] += 1
        return original(self)

    Memory.expire = counting
    try:
        with tempfile.TemporaryDirectory() as tmp:
            config = variant_config(Path(tmp), overrides)
            audit = audit_trace(trace, "dynamic", seed=0, total_memories=memories, scheduler=scheduler, config=config,
                                compiler_reservation_ms=window_ms)
    finally:
        Memory.expire = original
    adaptive = collections.Counter(e.reason for e in audit.events if isinstance(e, Unbooked) and e.kind == "adaptive")
    bookings = sum(isinstance(e, Booked) and e.kind == "adaptive" for e in audit.events)
    delivered = sum(isinstance(e, PairDelivered) for e in audit.events)
    credited = sum(isinstance(e, PairCredited) for e in audit.events)
    return {"workload": workload, "case": name, "completed": audit.completed, "requested": audit.requested,
            "violations": len(audit.violations), "violation_kinds": "|".join(sorted({v.invariant for v in audit.violations})),
            "makespan_ms": f"{audit.makespan_ms:.3f}", "adaptive_bookings": bookings,
            "released_consumed": adaptive["consumed"], "released_reservation_expired": adaptive["reservation_expired"],
            "released_removed": adaptive["removed"], "pairs_delivered": delivered, "pairs_credited": credited,
            "memory_expiry_resets": resets["n"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workloads", nargs="+", default=["ghz", "graphstate"])
    parser.add_argument("--memories", type=int, default=4)
    parser.add_argument("--scheduler", default="per-qubit")
    args = parser.parse_args(argv)
    rows = []
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(ARCHIVE) as z:
        for workload in args.workloads:
            trace = Path(z.extract(f"{PREFIX}/{workload}/seed_42/requests.txt", tmp))
            for name, overrides, window in CASES:
                rows.append(run_case(trace, workload, name, overrides, window, args.memories, args.scheduler))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    for r in rows:
        print(f"{r['workload']:10} {r['case'][:58]:58} done {r['completed']}/{r['requested']} viol {r['violations']} "
              f"consumed {r['released_consumed']} window-expired {r['released_reservation_expired']} cutoff-reset {r['memory_expiry_resets']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
