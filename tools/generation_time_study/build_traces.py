"""Route the frozen mappings with the repository's own selectors and store the study's traces.

QFT and QAOA come from the 2026-10-30 evidence, Draper from the 2026-10-28 evidence, and the two
48-qubit controls from the golden-study traces.  Placements are not regenerated, so a route is the
only difference between two traces of a workload.  The XY and greedy QFT/QAOA traces must equal the
2026-10-30 traces, which checks that this path reproduces the earlier study.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

import knobs as kn

sys.path.insert(0, str(kn.ROOT / "tools" / "routing_research"))
import heavy_routing as routing     # noqa: E402

OUTPUT = kn.ROOT / "results" / "generation_time_2026-11-01" / "traces"
FRESH = kn.ROOT / "results" / "greedy_xy_2026-10-30" / "evidence.zip"
HEAVY = kn.ROOT / "results" / "heavy_routing_2026-10-28" / "evidence.zip"
ROUTES_96 = ("xy", "greedy", "history", "minhop")


def extract(archive: Path, prefix: str, workload: str, inputs: Path) -> None:
    target = inputs / workload / "seed_42"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for name in ("requests.txt", "mapping.npz"):
            (target / name).write_bytes(bundle.read(f"{prefix}/{workload}/seed_42/{name}"))


def normalised(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def store(source: Path, workload: str, route: str, provenance: str) -> dict:
    target = OUTPUT / workload / route / "requests.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    data = normalised(source.read_bytes())
    target.write_bytes(data)
    return dict(workload=workload, route=route, sha256=hashlib.sha256(data).hexdigest(), provenance=provenance)


def main() -> None:
    manifest = []
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder).resolve()
        inputs, routed = work / "inputs", work / "routed"
        extract(FRESH, "study/inputs", "qft", inputs)
        extract(FRESH, "study/inputs", "qaoa", inputs)
        extract(HEAVY, "inputs96", "draper_qft_adder", inputs)
        routing.ROOT = work
        routing.build(routed, inputs, ROUTES_96, ("qft", "qaoa"))
        routing.build(routed, inputs, ("xy", "history"), ("draper_qft_adder",))
        with zipfile.ZipFile(FRESH) as bundle:
            for workload in ("qft", "qaoa"):
                for route in ("xy", "greedy"):
                    earlier = normalised(bundle.read(f"study/traces/{workload}/seed_42/{route}/requests.txt"))
                    built = normalised((routed / "traces" / workload / "seed_42" / route / "requests.txt").read_bytes())
                    if earlier != built:
                        raise SystemExit(f"{workload}/{route} does not reproduce the 2026-10-30 trace")
        for workload, routes, origin in (("qft", ROUTES_96, FRESH.name), ("qaoa", ROUTES_96, FRESH.name),
                                         ("draper_qft_adder", ("xy", "history"), HEAVY.name)):
            for route in routes:
                manifest.append(store(routed / "traces" / workload / "seed_42" / route / "requests.txt", workload, route,
                                      f"mapping from {origin}, route from tools/routing_research/heavy_routing.py"))
        routing.ROOT = kn.ROOT
        golden = work / "golden"
        routing.build(golden, None, ("xy", "history"), ("cdkm_ripple_carry_adder", "randomcircuit"))
        for workload in ("cdkm_ripple_carry_adder", "randomcircuit"):
            for route in ("xy", "history"):
                manifest.append(store(golden / "traces" / workload / "seed_42" / route / "requests.txt", workload, route,
                                      "48-qubit T-HQA golden-study mapping, route from heavy_routing.py"))
    (OUTPUT.parent / "traces_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{len(manifest)} traces stored; XY and greedy reproduce the 2026-10-30 traces")


if __name__ == "__main__":
    main()
