"""Run the reproducible QFT research matrix and aggregate paired seed results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from aggregate_compiler_results import aggregate, paired_latency, _write
from calibrate_physical_lead import derive_profile


QFT_SHA256 = "61d97492195aea40fad48d5bc4e1b48b2dd019eea20fe24aada8c954e3073da1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], environment: dict[str, str]) -> None:
    print("Running:", " ".join(command), flush=True)
    subprocess.run(command, check=True, env=environment)


def read_summary(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def runner_command(args, output: Path, name: str, strategy: str,
                   compiler_memories: int, generation_capacity: int,
                   dynamic_min_lead: int = 1) -> list[str]:
    return [
        sys.executable, "run_compiler_pregeneration.py",
        "--trace", str(args.trace), "--config", str(args.config),
        "--mesh", "4x4", "--strategies", strategy,
        "--seeds", args.seeds, "--total-memories", "4",
        "--compiler-memories", str(compiler_memories),
        "--generation-capacity", str(generation_capacity),
        "--delta-layers", "6", "--dynamic-lookahead-layers", "8",
        "--dynamic-min-lead-layers", str(dynamic_min_lead),
        "--coherence-time-layers", "10",
        "--compiler-reservation-ms", "1000", "--stop-time-s", "300",
        "--configuration-name", name, "--output", str(output),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--sequence-root", required=True, type=Path)
    parser.add_argument("--config", type=Path,
                        default=Path("config/final_config/grid_4x4_ace_3.json"))
    parser.add_argument("--seeds", default="0,1,2,3,4,5,6,7,8,9")
    parser.add_argument("--service-quantile", required=True, type=float)
    parser.add_argument("--layer-quantile", required=True, type=float)
    parser.add_argument("--safety-factor", required=True, type=float)
    parser.add_argument("--output", type=Path, default=Path("output/research_matrix"))
    args = parser.parse_args()

    if sha256(args.trace) != QFT_SHA256:
        parser.error("trace SHA-256 does not match the handed-off 4x4 QFT workload")
    if not (args.sequence_root / "sequence").is_dir():
        parser.error("--sequence-root must contain the compatible sequence package")
    if args.safety_factor <= 0:
        parser.error("--safety-factor must be positive")

    args.output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(args.sequence_root.resolve())

    profiles = (
        ("on-demand", "on-demand", 1, 3, 1),
        ("fixed-delta6-cap3", "fixed", 3, 3, 1),
        ("dynamic-latest-cap3", "dynamic", 3, 3, 1),
        ("dynamic-latest-cap2", "dynamic", 2, 2, 1),
    )
    summary_rows = []
    for name, strategy, memories, capacity, lead in profiles:
        output = args.output / name
        run(runner_command(args, output, name, strategy, memories, capacity, lead),
            environment)
        summary_rows.extend(read_summary(output / "summary.csv"))

    baseline_payload = json.loads(
        (args.output / "on-demand" / "runs.json").read_text(encoding="utf-8")
    )
    calibration = derive_profile(
        baseline_payload, args.service_quantile, args.layer_quantile,
        args.safety_factor,
    )
    calibration_path = args.output / "physical_lead_calibration.json"
    calibration_path.write_text(json.dumps(calibration, indent=2) + "\n",
                                encoding="utf-8")
    lead = calibration["dynamic_min_lead_layers"]
    if lead > 8:
        raise ValueError(
            f"calibrated lead {lead} exceeds lookahead 8; increase the declared "
            "lookahead before running the calibrated profile"
        )
    for cap in (2, 3):
        name = f"dynamic-calibrated-lead{lead}-cap{cap}"
        output = args.output / name
        run(runner_command(args, output, name, "dynamic", cap, cap, lead), environment)
        summary_rows.extend(read_summary(output / "summary.csv"))

    aggregate_path = args.output / "aggregate_95ci.csv"
    paired_path = args.output / "paired_vs_odg_95ci.csv"
    _write(aggregate_path, aggregate(summary_rows))
    _write(paired_path, paired_latency(summary_rows, "on-demand"))
    manifest = {
        "trace": str(args.trace.resolve()), "trace_sha256": sha256(args.trace),
        "sequence_root": str(args.sequence_root.resolve()), "seeds": args.seeds,
        "service_quantile": args.service_quantile,
        "layer_quantile": args.layer_quantile,
        "safety_factor": args.safety_factor,
        "calibrated_dynamic_min_lead_layers": lead,
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {aggregate_path}")
    print(f"Wrote {paired_path}")


if __name__ == "__main__":
    main()
