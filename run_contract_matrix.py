"""Run every selected ACE profile from a validated experiment contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import subprocess
import sys

from experiment_contract import load_contract, select_profile


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument(
        "--contract", type=Path,
        default=Path("experiments/qft_4x4_comparison_v1.json"),
    )
    parser.add_argument("--config", type=Path,
                        default=Path("config/final_config/grid_4x4_ace_3.json"))
    parser.add_argument("--profiles", help="comma-separated profile ids; default is all")
    parser.add_argument("--output", type=Path, default=Path("output/contract_qft_v1"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--contract-seed-limit", type=int)
    args = parser.parse_args()

    try:
        contract = load_contract(args.contract)
        identifiers = ([item.strip() for item in args.profiles.split(",") if item.strip()]
                       if args.profiles else [item["id"] for item in contract["profiles"]])
        for identifier in identifiers:
            select_profile(contract, identifier)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    commands = []
    for identifier in identifiers:
        destination = args.output / identifier
        if not args.dry_run and destination.exists() and any(destination.iterdir()):
            parser.error(f"output profile directory is not empty: {destination}")
        commands.append([
            sys.executable, "run_compiler_pregeneration.py",
            "--trace", str(args.trace), "--config", str(args.config),
            "--contract", str(args.contract), "--profile", identifier,
            "--output", str(destination),
        ] + (["--contract-seed-limit", str(args.contract_seed_limit)]
             if args.contract_seed_limit is not None else []))

    for command in commands:
        print(shlex.join(command), flush=True)
        if not args.dry_run:
            subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
