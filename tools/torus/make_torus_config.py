#!/usr/bin/env python3
"""Build ACE's torus topology file from its mesh file by adding the wrap-around links.

A rows x columns torus joins (r, columns-1) to (r, 0) and (rows-1, c) to (0, c) in addition to the mesh links.  Every link is
built exactly as the mesh file builds one: a BSM node between the two routers, router-to-BSM quantum channels both ways,
BSM-router classical channels both ways, and direct router-router classical channels both ways.  ``--wrap-distance-factor``
scales the fibre length of the wrap links (default 1: the same length as every other link, which models a folded torus layout;
an unfolded layout would use a larger factor).  Everything else, including every physical parameter, is copied unchanged.

    python tools/torus/make_torus_config.py --output config/final_config/grid_4x4_torus_ace_3.json
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MESH_CONFIG = REPO / "config" / "final_config" / "grid_4x4_ace_3.json"


def wrap_pairs(rows: int, columns: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    pairs = []
    if columns > 2:
        pairs += [((r, columns - 1), (r, 0)) for r in range(rows)]
    if rows > 2:
        pairs += [((rows - 1, c), (0, c)) for c in range(columns)]
    return pairs


def build(mesh: dict, rows: int = 4, columns: int = 4, wrap_distance_factor: float = 1.0) -> dict:
    config = copy.deepcopy(mesh)
    existing = {n["name"] for n in config["nodes"]}
    next_seed = 1 + max(n["seed"] for n in config["nodes"])
    # copy the quantum and classical channel parameters of an existing link
    q_example = next(q for q in mesh["qchannels"] if q["destination"].startswith("BSM"))
    c_bsm = next(c for c in mesh["cchannels"] if c["source"].startswith("BSM"))
    c_rr = next(c for c in mesh["cchannels"] if c["source"].startswith("router") and c["destination"].startswith("router"))
    bsm_template = next(n for n in mesh["nodes"] if n["type"] == "BSMNode")["template"]
    for (r1, c1), (r2, c2) in wrap_pairs(rows, columns):
        name = f"BSM_{r1}_{c1}_{r2}_{c2}"
        if name in existing:
            raise ValueError(f"duplicate BSM node {name}")
        routers = [f"router_{r1}_{c1}", f"router_{r2}_{c2}"]
        config["nodes"].append({"name": name, "type": "BSMNode", "seed": next_seed, "template": bsm_template})
        next_seed += 1
        d = q_example["distance"] * wrap_distance_factor
        for router in routers:
            config["qchannels"].append({"source": router, "destination": name, "distance": d,
                                        "attenuation": q_example["attenuation"]})
            config["cchannels"].append({"source": name, "destination": router, "distance": d, "delay": c_bsm["delay"]})
            config["cchannels"].append({"source": router, "destination": name, "distance": d, "delay": c_bsm["delay"]})
        for a, b in ((routers[0], routers[1]), (routers[1], routers[0])):
            config["cchannels"].append({"source": a, "destination": b, "distance": 2 * d, "delay": c_rr["delay"]})
    return config


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mesh-config", type=Path, default=MESH_CONFIG)
    parser.add_argument("--rows", type=int, default=4)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--wrap-distance-factor", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    mesh = json.loads(args.mesh_config.read_text(encoding="utf-8"))
    config = build(mesh, args.rows, args.columns, args.wrap_distance_factor)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=1), encoding="utf-8")
    print(f"wrote {args.output}: {len(config['nodes'])} nodes, {len(config['qchannels'])} quantum and "
          f"{len(config['cchannels'])} classical channels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
