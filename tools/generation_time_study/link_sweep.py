"""Single-link screening: change one physical knob at a time and measure generation time.

Every hop direction matters, so each setting runs on both 0->1 and 1->0.  The same seeds are used
everywhere, which makes the comparison between settings paired.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

import knobs as kn

HERE = Path(__file__).resolve().parent
OUTPUT = kn.ROOT / "output" / "generation_time_study" / "link"
SCREEN = {
    "memory_efficiency": (1.0, 0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3),
    "detector_efficiency": (1.0, 0.9, 0.8, 0.6, 0.4),
    "bsm_success_rate": (0.5, 0.4, 0.3, 0.2, 0.1),
    "classical_scale": (0.01, 0.1, 0.5, 2.0, 5.0, 10.0),
    "distance_scale": (1e3, 1e4, 1e5, 2e5, 4e5),
    "attenuation_db_per_m": (0.0, 2.0, 20.0, 100.0, 200.0),
    "memory_frequency_hz": (1e6, 1e5, 1e4, 5e3, 2e3, 1e3),
    "coherence_time_s": (0.1, 0.01, 1e-3, 5e-4, 2e-4, 1e-4),
    "raw_fidelity": (0.99, 0.85),
    "dark_count_per_s": (1e3, 1e6, 1e8),
    "gate_fidelity": (0.9,),
    "measurement_fidelity": (0.9,),
    "empty_gap_ms": (0.0, 20.0),
}


def job(item: tuple) -> None:
    samples, name, value, source, destination = item
    settings = kn.Knobs(**({name: value} if name else {}))
    target = OUTPUT / f"{settings.key().replace('/', '_')}__{source}_{destination}.json"
    if target.exists():
        return
    done = subprocess.run([sys.executable, "-B", str(HERE / "link_probe.py"), "--knobs", json.dumps(settings.overrides()),
                           "--source", str(source), "--destination", str(destination), "--samples", str(samples),
                           "--output", str(target)], capture_output=True, text=True, env=os.environ, cwd=HERE)
    if done.returncode:
        print("FAILED", target.name, done.stderr[-300:], flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3000)
    parser.add_argument("--workers", type=int, default=7)
    args = parser.parse_args()
    items = [(args.samples * 3, None, None, s, d) for s, d in ((0, 1), (1, 0), (0, 4), (4, 0), (5, 6), (6, 5))]
    items += [(args.samples, name, value, s, d) for name, values in SCREEN.items() for value in values
              for s, d in ((0, 1), (1, 0)) if not (kn.Knobs(**{name: value}).key() == "base")]
    print(len(items), "probes", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(job, items))
    print("DONE link", flush=True)


if __name__ == "__main__":
    main()
