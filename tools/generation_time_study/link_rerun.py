"""Rerun the three single-link settings that did not finish in the main screen, each with a time limit.

Dark counts of 1e6 and 1e8 per second add a detector event every microsecond or faster, and a
coherence time of 0.1 ms schedules memory expiry events constantly, so these settings are slow to simulate.
A probe that does not finish inside the limit is recorded as a timeout, never dropped.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import knobs as kn

HERE = Path(__file__).resolve().parent
OUTPUT = kn.ROOT / "output" / "generation_time_study" / "link"
SETTINGS = ({"dark_count_per_s": 1e6}, {"dark_count_per_s": 1e8}, {"coherence_time_s": 1e-4})


def main(samples: int = 100, limit: float = 1500.0) -> None:
    for overrides in SETTINGS:
        settings = kn.Knobs(**overrides)
        for source, destination in ((0, 1), (1, 0)):
            target = OUTPUT / f"{settings.key()}__{source}_{destination}.json"
            if target.exists():
                continue
            try:
                done = subprocess.run([sys.executable, "-B", str(HERE / "link_probe.py"), "--knobs", json.dumps(overrides),
                                       "--source", str(source), "--destination", str(destination), "--samples", str(samples),
                                       "--output", str(target)], capture_output=True, text=True, timeout=limit, env=os.environ, cwd=HERE)
                failed = done.returncode != 0
                note = done.stderr[-200:]
            except subprocess.TimeoutExpired:
                failed, note = True, f"timeout after {limit:.0f} s for {samples} samples"
            if failed:
                target.write_text(json.dumps(dict(samples=0, error_count=samples, errors=[note], knobs=settings.overrides(), key=settings.key(),
                                                  source=source, destination=destination, predicted_p=kn.success_probability(settings),
                                                  predicted_messages=kn.attempt_messages(source, destination))))
            print(settings.key(), source, destination, "timeout/failed" if failed else "ok", flush=True)


if __name__ == "__main__":
    main()
