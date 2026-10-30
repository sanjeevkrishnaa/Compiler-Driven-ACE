"""Recheck full-chain Dynamic against ODG with four physical memories per core.

This is an explicit QFT-96 configuration, not a replacement for frozen study
defaults or a universally tuned policy. Both strategies use the same trace,
physical memories, seeds, and eligibility-to-completion latency definition.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ace.compiler.settings import DEFAULT_COMPILER_RESERVATION_MS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--topology", choices=("mesh", "torus"), default="mesh")
    parser.add_argument("--mesh", default="4x4")
    parser.add_argument("--seeds", required=True,
                        help="explicit physics seeds; use independent seeds for confirmation")
    parser.add_argument("--compiler-memories", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument("--compiler-pair-consumption", choices=("handoff", "swap"), default="handoff")
    parser.add_argument("--planner-lead-layers", type=int, default=2,
                        help="minimum preparation lead (2: verified full-chain preset; 1: earlier C=2 baseline)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--compiler-reservation-ms", type=float, default=DEFAULT_COMPILER_RESERVATION_MS)
    args = parser.parse_args()
    command = [
        sys.executable, "-u", str(ROOT / "run_trace_comparison.py"),
        "--trace", str(args.trace.resolve()),
        "--config", str(args.config.resolve()),
        "--topology", args.topology, "--mesh", args.mesh,
        "--strategies", "on-demand,dynamic", "--seeds", args.seeds,
        "--total-memories", "4", "--compiler-memories", str(args.compiler_memories),
        "--generation-capacity", str(args.compiler_memories), "--all-chain-hops",
        "--compiler-pair-consumption", args.compiler_pair_consumption,
        "--no-congestion-threshold", "--preparation-trigger", "layer-start",
        "--preparation-delay-ms", "0", "--planner-lead-layers", str(args.planner_lead_layers),
        "--dynamic-lookahead-layers", "8", "--coherence-time-layers", "10",
        "--fidelity-threshold", "0.01", "--pregeneration-buffer-ms", "0",
        "--compiler-reservation-ms", str(args.compiler_reservation_ms), "--request-duration-ms", "50",
        "--stop-time-s", "200", "--scheduler", "per-qubit",
        "--admission", "event", "--admission-priority", "ready-first", "--starvation-guard", "--stop-after-workload", "--audit-events",
        "--output", str(args.output.resolve()),
    ]
    if args.dry_run:
        print(subprocess.list2cmdline(command))
        return
    if not args.trace.is_file() or not args.config.is_file():
        parser.error("trace and config must be existing files")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("choose an empty output directory to preserve earlier evidence")
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
