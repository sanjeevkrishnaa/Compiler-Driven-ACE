"""Run the immutable ACE static fixed-lead matrix from a source snapshot."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys


def run(contract: Path, trace: Path, config: Path, output: Path) -> tuple[str, int]:
    payload = json.loads(contract.read_text(encoding="utf-8"))
    profile = payload["profiles"][0]["id"]
    destination = output / profile
    command = [sys.executable, "run_compiler_pregeneration.py", "--trace", str(trace),
               "--config", str(config), "--contract", str(contract), "--profile", profile,
               "--output", str(destination)]
    with (output / f"{profile}.log").open("w", encoding="utf-8") as log:
        return profile, subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", required=True, type=Path)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    contracts = sorted(args.contracts.glob("qft_4x4_static-*plus*_fixed_delta*_v1.json"))
    if len(contracts) != 18:
        parser.error(f"expected 18 static fixed-lead contracts, found {len(contracts)}")
    args.output.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda item: run(item, args.trace, args.config, args.output), contracts))
    failed = [profile for profile, code in results if code]
    if failed:
        raise SystemExit(f"failed profiles: {', '.join(failed)}")


if __name__ == "__main__":
    main()
