#!/usr/bin/env python3
"""Does the dynamic planner's lookahead change its schedule?

Plans the dynamic policy with lookaheads 1, 2, 4 and 8 for every benchmark, mapping seed (42-44) and memory count (2-32) with the
settings of Experiment 1 (cap and generation capacity budget - 1, coherence 10 layers) and compares the schedules.  It also counts how many
preparations the lookahead-8 plan places earlier than the layer just before the request.

    python tools/diagnostics/check_lookahead.py OUTPUT.txt
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "ace_budget_rerun"))
import run_budget_sweep as sweep                                        # noqa: E402
from ace.compiler.compiler_trace import parse_compiler_trace, plan_preparations      # noqa: E402

WORKLOADS = ["ghz", "bv", "graphstate", "vqe_real_amp", "cdkm_ripple_carry_adder", "bmw_quark_cardinality",
             "draper_qft_adder", "qft", "qaoa", "randomcircuit"]


def main(output: Path) -> int:
    tmp = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(sweep.ARCHIVE) as archive:
        for workload in WORKLOADS:
            for seed in (42, 43, 44):
                archive.extract(f"{sweep.PREFIX}/{workload}/seed_{seed}/requests.txt", tmp)
    configs = differ = placed_earlier = placed = 0
    lines = []
    for workload in WORKLOADS:
        for seed in (42, 43, 44):
            trace = parse_compiler_trace(tmp / sweep.PREFIX / workload / f"seed_{seed}" / "requests.txt")
            layer = {r.request_id: r.layer for r in trace.requests}
            for memories in (2, 3, 4, 6, 8, 16, 32):
                plans = {}
                for lookahead in (1, 2, 4, 8):
                    schedule, blocked, _ = plan_preparations(
                        trace, strategy="dynamic", compiler_memories_per_core=memories - 1, generation_capacity_per_core=memories - 1,
                        coherence_time_layers=10, delta_layers=6, dynamic_lookahead_layers=lookahead)
                    plans[lookahead] = (tuple(sorted((p.request_id, p.generation_layer) for p in schedule)), blocked)
                configs += 1
                if len(set(plans.values())) > 1:
                    differ += 1
                    lines.append(f"DIFFERS {workload} mapping {seed} memories {memories}: " + str({k: (len(v[0]), v[1]) for k, v in plans.items()}))
                placed += len(plans[8][0])
                placed_earlier += sum(1 for rid, g in plans[8][0] if g < layer[rid] - 1)
    lines += [f"configurations: {configs}", f"configurations where the schedule or the blocked count differs between lookahead 1, 2, 4 and 8: {differ}",
              f"preparations placed by the lookahead-8 plan: {placed}",
              f"of which placed earlier than the layer just before the request: {placed_earlier}"]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-4:]))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
