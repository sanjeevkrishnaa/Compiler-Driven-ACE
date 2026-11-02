"""Route the five study workloads with XY and history, from one frozen mapping each.

Architecture: 4x4 mesh, 16 data slots per core (14 occupied at the start, 2 kept free for migrations), 4 communication
memories per core, so 224 logical qubits.  Workloads: qft, qpeexact and draper_qft_adder and qaoa from MQT Bench 2.3.0, and
quantum_volume from Qiskit (random SU(4) layers, depth equal to width).  Inputs come from tools/congestion_study/run_study.py.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "routing_research"))
import heavy_routing as routing     # noqa: E402

WORKLOADS = ("qft", "qpeexact", "qaoa", "draper_qft_adder", "quantum_volume")
ROUTES = ("xy", "history")
WORK = ROOT / "output" / "wallclock_study"
OUTPUT = ROOT / "results" / "wallclock_2026-11-03" / "traces"


def main() -> None:
    inputs = WORK / "inputs"
    for workload in WORKLOADS:
        target = inputs / workload / "seed_42"
        target.mkdir(parents=True, exist_ok=True)
        for name in ("requests.txt", "mapping.npz", "manifest.json"):
            shutil.copy(WORK / f"inputs_{workload}" / workload / "seed_42" / name, target / name)
    routing.ROOT = WORK.resolve()
    routing.build(WORK / "routed", inputs.resolve(), ROUTES, WORKLOADS)
    manifest = []
    for workload in WORKLOADS:
        for route in ROUTES:
            data = (WORK / "routed" / "traces" / workload / "seed_42" / route / "requests.txt").read_bytes().replace(b"\r\n", b"\n")
            target = OUTPUT / workload / route / "requests.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest.append(dict(workload=workload, route=route, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
    (OUTPUT.parent / "traces_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(len(manifest), "traces")


if __name__ == "__main__":
    main()
