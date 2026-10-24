#!/usr/bin/env python3
"""Mesh against torus, from the committed result files: hops, structural overload, own-versus-relay share, latency, fidelity."""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "experiment1"))
sys.path.insert(0, str(REPO / "tools" / "experiment2"))
import analyze as A                                                           # noqa: E402
import split_congestion as S                                                  # noqa: E402

MESH = REPO / "results" / "experiment1_ten_benchmarks_2026-10-24"
TORUS = REPO / "results" / "experiment1_torus_2026-10-24"
ORDER = ["ghz", "bv", "bmw_quark_cardinality", "vqe_real_amp", "cdkm_ripple_carry_adder", "graphstate", "draper_qft_adder", "qaoa", "qft", "randomcircuit"]


def count_hops(path: Path) -> int:
    n = 0
    section = False
    for line in path.read_text().splitlines():
        if line.startswith("// Inter-core communication requests"):
            section = True
        elif section and line.startswith("(") and line.count(",") == 2:
            n += 1
    return n


def main() -> int:
    import zipfile, tempfile
    mesh_rows, torus_rows = A.load(MESH / "results.csv"), A.load(TORUS / "results.csv")
    gm, gt = A.cells(mesh_rows), A.cells(torus_rows)
    sm = json.loads((MESH / "structural_overload.json").read_text())
    stt = json.loads((TORUS / "structural_overload.json").read_text())
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(S.ARCHIVE) as z:
        mesh_hops = {w: st.fmean(count_hops(Path(z.extract(f"{S.PREFIX}/{w}/seed_{s}/requests.txt", tmp))) for s in (42, 43, 44)) for w in ORDER}
    torus_hops = {w: st.fmean(count_hops(REPO / "results" / "torus_traces_2026-10-24" / w / f"seed_{s}" / "requests.txt") for s in (42, 43, 44)) for w in ORDER}
    mean = lambda g, k, m: (st.fmean(g[k][m]) if g.get(k, {}).get(m) else None)
    out = []
    for w in ORDER:
        out.append({
            "workload": w, "hops_mesh": round(mesh_hops[w], 1), "hops_torus": round(torus_hops[w], 1),
            "overload_c4_mesh": sm[w]["4"], "overload_c4_torus": stt[w]["4"], "overload_c2_mesh": sm[w]["2"], "overload_c2_torus": stt[w]["2"],
            **{f"ondemand_latency_b{b}_{n}": mean(g, (w, "on-demand", b), "latency_ms") for b in (1, 2, 4, 32) for n, g in (("mesh", gm), ("torus", gt))},
            **{f"dynamic_latency_b{b}_{n}": mean(g, (w, "dynamic", b), "latency_ms") for b in (4, 8, 32) for n, g in (("mesh", gm), ("torus", gt))},
        })
    keys = list(out[0])
    path = TORUS.parent / "mesh_vs_torus_2026-10-24" / "comparison.csv"
    path.parent.mkdir(exist_ok=True)
    with path.open("w", newline="") as h:
        w_ = csv.DictWriter(h, fieldnames=keys)
        w_.writeheader()
        w_.writerows(out)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
