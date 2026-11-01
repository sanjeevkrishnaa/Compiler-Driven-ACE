"""Run an experiment of experiments.py in parallel; finished cases are skipped, failures are kept."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import experiments
import knobs as kn

HERE = Path(__file__).resolve().parent
RUNS = kn.ROOT / "output" / "generation_time_study" / "runs"


def case_key(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16]


def run(spec: dict, timeout: float) -> tuple[str, str]:
    folder = RUNS / case_key(spec)
    if (folder / "reduced.json").exists():
        return "skipped", folder.name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "spec.json"
    path.write_text(json.dumps(spec, indent=1, sort_keys=True))
    (folder / "failed.txt").unlink(missing_ok=True)
    start = time.time()
    try:
        done = subprocess.run([sys.executable, "-B", str(HERE / "run_case.py"), "--spec", str(path), "--output", str(folder)],
                              capture_output=True, text=True, timeout=timeout, cwd=kn.ROOT, env=os.environ)
    except subprocess.TimeoutExpired:
        (folder / "failed.txt").write_text(f"timeout after {timeout} s\n")
        return "failed", folder.name
    if done.returncode:
        (folder / "failed.txt").write_text(done.stderr[-4000:])
        return "failed", folder.name
    (folder / "seconds.txt").write_text(f"{time.time() - start:.1f}\n")
    return "ok", folder.name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiment", choices=sorted(experiments.EXPERIMENTS))
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=3 * 3600)
    args = parser.parse_args()
    specs = experiments.EXPERIMENTS[args.experiment]()
    unique = {case_key(s): s for s in specs}
    counts = {"ok": 0, "skipped": 0, "failed": 0}
    print(f"{args.experiment}: {len(specs)} cases, {len(unique)} unique", flush=True)
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run, s, args.timeout): s for s in unique.values()}
        for index, future in enumerate(as_completed(futures), 1):
            state, name = future.result()
            counts[state] += 1
            if state == "failed" or index % 10 == 0 or index == len(futures):
                print(f"[{index}/{len(futures)}] {state} {name} {counts} {time.time() - started:.0f}s", flush=True)
    print("DONE", args.experiment, counts, flush=True)


if __name__ == "__main__":
    main()
