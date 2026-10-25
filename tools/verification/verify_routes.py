"""Pass-2 verification of the routing tools, with independent re-implementations (own parser, own mesh model, SciPy statistics).

R1  trace parser: every exported / intervention hop file parses to chains that are contiguous, adjacent on the 4x4 mesh, and keep the supplied
    file's (layer, qubit, first source, last destination) set and total hop count; layer headers == 766.
R2  XY / YX files: each route moves dimension 0 (row) fully first for XY, column first for YX (own geometry: core = row*4 + column).
R3  interventions obey their rule (mix: changed routes are XY; o1turn: XY or YX; rand_shortest/concentrate/balance: shortest paths only; avoid_hot:
    a migration is changed only if it relayed through a hot core).
R4  static load: demand and excess recomputed from scratch equal tools.mapper_ace.route_load for every arm.
R5  per-core wait (when the files exist): per-request mean equals the runner's average_admission_wait_ms for the same seed, and touches sum to 2 x requests.
R6  comparison statistics: Welch difference / interval / p-value equal scipy.stats.ttest_ind(equal_var=False) on the stored summaries.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[2]
BTP = ROOT.parent
failures = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def neighbours(core):                                   # 4x4 mesh, core = row * 4 + column
    r, c = divmod(core, 4)
    return {rr * 4 + cc for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)) if 0 <= rr < 4 and 0 <= cc < 4}


def parse(path: Path):
    """-> (initial placement, layer headers, {(layer, qubit): [hops in file order]})"""
    initial, headers, chains, layer = {}, 0, defaultdict(list), None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("// Layer"):
            layer, headers = int(line.split()[-1]), headers + 1
        elif line.startswith("("):
            values = tuple(int(v) for v in line.strip("()").split(","))
            if len(values) == 2 and layer is None:
                initial[values[0]] = values[1]
            elif len(values) == 3:
                chains[(layer, values[0])].append(values[1:])
    return initial, headers, chains


def path_of(hops):
    cores = [hops[0][0]]
    for source, destination in hops:
        assert source == cores[-1], "non-contiguous chain"
        assert destination in neighbours(source), "non-adjacent hop"
        cores.append(destination)
    return tuple(cores)


def manhattan(a, b):
    return abs(a // 4 - b // 4) + abs(a % 4 - b % 4)


def xy_path(s, t):                                      # row (dimension 0) first
    r, c = divmod(s, 4); tr, tc = divmod(t, 4); out = [s]
    while r != tr: r += 1 if tr > r else -1; out.append(r * 4 + c)
    while c != tc: c += 1 if tc > c else -1; out.append(r * 4 + c)
    return tuple(out)


def yx_path(s, t):                                      # column (dimension 1) first
    r, c = divmod(s, 4); tr, tc = divmod(t, 4); out = [s]
    while c != tc: c += 1 if tc > c else -1; out.append(r * 4 + c)
    while r != tr: r += 1 if tr > r else -1; out.append(r * 4 + c)
    return tuple(out)


def all_shortest(s, t):
    out = []
    def walk(p):
        if p[-1] == t: out.append(tuple(p)); return
        for n in sorted(neighbours(p[-1])):
            if manhattan(n, t) == manhattan(p[-1], t) - 1: walk(p + [n])
    walk([s]); return out


def demand(paths_by_layer):
    d = Counter()
    for layer, paths in paths_by_layer:
        for p in paths:
            for i, c in enumerate(p):
                d[(layer, c)] += 1 if i in (0, len(p) - 1) else 2
    return d


# ---------------------------------------------------------------------------------------------- load arms
SUPPLIED = BTP / "qft_requests.txt"
R = ROOT / "results/routing_study_2026-10-25/qft96"
I = ROOT / "results/why_xy_2026-10-25/interventions"
init0, headers0, chains0 = parse(SUPPLIED)
paths0 = {k: path_of(v) for k, v in chains0.items()}
check("R1 supplied file parses: 766 layer headers, 1770 chains, 4954 hops, all contiguous and adjacent",
      headers0 == 766 and len(paths0) == 1770 and sum(len(p) - 1 for p in paths0.values()) == 4954)

arms = {"xy": R / "xy/requests.txt", "yx": R / "yx/requests.txt", "shortest_reliable": R / "shortest_reliable/requests.txt",
        "max_reliability": R / "max_reliability/requests.txt"}
arms.update({d.name: d / "requests.txt" for d in sorted(I.iterdir()) if d.is_dir()})
parsed = {}
for name, path in arms.items():
    init, headers, chains = parse(path)
    paths = {k: path_of(v) for k, v in chains.items()}
    parsed[name] = paths
    same_moves = {k: (p[0], p[-1]) for k, p in paths.items()} == {k: (p[0], p[-1]) for k, p in paths0.items()}
    hops = sum(len(p) - 1 for p in paths.values())
    ok = headers == 766 and init == init0 and same_moves and (hops == 4954 or name == "max_reliability")
    check(f"R1 {name}: 766 layers, same placement and moves as supplied, hops {hops}", ok)
    if name not in ("max_reliability",):
        shortest = all(len(p) - 1 == manhattan(p[0], p[-1]) for p in paths.values())
        check(f"R1 {name}: every route is a shortest path", shortest)

for k, p in parsed["xy"].items():
    if p != xy_path(p[0], p[-1]): check("R2 xy route order", False, str(k)); break
else:
    check("R2 every XY route moves rows first (independent geometry)", True)
for k, p in parsed["yx"].items():
    if p != yx_path(p[0], p[-1]): check("R2 yx route order", False, str(k)); break
else:
    check("R2 every YX route moves columns first (independent geometry)", True)
check("R2 the pair counts of mesh shortest paths equal binomial(dx+dy, dx) for all 240 ordered pairs",
      all(len(all_shortest(s, t)) == math.comb(abs(s // 4 - t // 4) + abs(s % 4 - t % 4), abs(s // 4 - t // 4)) for s, t in product(range(16), repeat=2) if s != t))

# ---------------------------------------------------------------------------------------------- rules
for name, paths in parsed.items():
    if name.startswith("mix_p"):
        changed = [k for k in paths if paths[k] != paths0[k]]
        check(f"R3 {name}: all {len(changed)} changed routes are the XY route", all(paths[k] == xy_path(paths[k][0], paths[k][-1]) for k in changed))
        p = int(name.split("_p")[1].split("_")[0]) / 100
        eligible = [k for k in paths0 if paths0[k] != xy_path(paths0[k][0], paths0[k][-1])]
        check(f"R3 {name}: fraction of XY-differing routes switched {len(changed)}/{len(eligible)} is within 4 sd of p={p}",
              abs(len(changed) - p * len(eligible)) <= 4 * math.sqrt(len(eligible) * p * (1 - p)))
    elif name.startswith("o1turn"):
        check(f"R3 {name}: every route is XY or YX", all(paths[k] in (xy_path(paths[k][0], paths[k][-1]), yx_path(paths[k][0], paths[k][-1])) for k in paths))
    elif name.startswith(("rand_shortest", "concentrate", "balance")):
        check(f"R3 {name}: every route is one of the shortest paths", all(paths[k] in all_shortest(paths[k][0], paths[k][-1]) for k in paths))
    elif name.startswith("avoid_hot"):
        k_hot = int(name[len("avoid_hot"):])
        relay = Counter(c for p in paths0.values() for c in p[1:-1])
        hot = {c for c, _ in relay.most_common(k_hot)}
        touched = {k for k, p in paths0.items() if hot & set(p[1:-1])}
        changed = {k for k in paths if paths[k] != paths0[k]}
        check(f"R3 {name} (hot cores {sorted(hot)}): changes only migrations that relayed through a hot core ({len(changed)} changed of {len(touched)})", changed <= touched)
        before = sum(len(hot & set(paths0[k][1:-1])) for k in paths0); after = sum(len(hot & set(paths[k][1:-1])) for k in paths)
        check(f"R3 {name}: hot-core relay visits do not increase ({before} -> {after})", after <= before)
if "concentrate" in parsed and "balance" in parsed:
    exc = lambda paths: sum(max(0, v - 4) for v in demand([(k[0], [p]) for k, p in paths.items()]).values())     # noqa: E731
    e_c, e_b, e_o = exc(parsed["concentrate"]), exc(parsed["balance"]), exc(paths0)
    check(f"R3 balance carries less excess than supplied, concentrate more ({e_b} < {e_o} < {e_c})", e_b < e_o < e_c)

# ---------------------------------------------------------------------------------------------- static load
loads = json.loads((ROOT / "results/why_xy_2026-10-25/static_load_all.json").read_text())
for name, paths in {"original": paths0, **parsed}.items():
    if name not in loads: continue
    d = demand([(k[0], [p]) for k, p in paths.items()])
    mine = {c: sum(max(0, v - c) for v in d.values()) for c in (2, 3, 4, 6, 8)}
    theirs = {c: loads[name][f"excess_C{c}"] for c in (2, 3, 4, 6, 8)}
    check(f"R4 {name}: recomputed excess equals route_load for C=2,3,4,6,8", mine == theirs, f"C4 {mine[4]} vs {theirs[4]}")

# ---------------------------------------------------------------------------------------------- per-core wait
pc = ROOT / "results/why_xy_2026-10-25/per_core"
for arm in ("original", "xy", "yx"):
    f = pc / f"{arm}_on-demand.json"
    if not f.exists(): continue
    data = json.loads(f.read_text())
    stored = {r["seed"]: float(r["average_admission_wait_ms"]) for r in csv.DictReader((ROOT / f"results/routing_study_2026-10-25/runs/{arm}/summary.csv").open())
              if r["strategy"] == "on-demand"}
    ok = all(abs(s["mean_wait_ms"] - stored[str(s["seed"])]) < 1e-9 for s in data["per_seed"])
    check(f"R5 {arm} ODG: per-core tool's mean wait equals the runner's average_admission_wait_ms for seeds {[s['seed'] for s in data['per_seed']]}", ok)
    check(f"R5 {arm} ODG: 16 cores, touches sum to 2 x requests",
          all(len(s["endpoint_touches"]) == 16 and sum(s["endpoint_touches"]) + sum(s["relay_touches"]) == 2 * s["requests"] for s in data["per_seed"]))

# ---------------------------------------------------------------------------------------------- statistics
from scipy import stats                                     # noqa: E402
sys.path.insert(0, str(ROOT))
from tools.mapper_ace.compare_routing import welch          # noqa: E402
rows = {a: [r for r in csv.DictReader((ROOT / f"results/routing_study_2026-10-25/runs/{a}/summary.csv").open()) if r["strategy"] == "dynamic"] for a in ("original", "xy")}
a = [float(r["request_latency_mean_ms"]) for r in rows["xy"]]; b = [float(r["request_latency_mean_ms"]) for r in rows["original"]]
d, half, p = welch(a, b)
t = stats.ttest_ind(a, b, equal_var=False)
ci = t.confidence_interval(0.95)
check("R6 Welch difference, 95% interval and p-value equal scipy.stats.ttest_ind(equal_var=False)",
      abs(d - (fmean(a) - fmean(b))) < 1e-12 and abs((ci.high - ci.low) / 2 - half) < 1e-9 and abs(p - t.pvalue) < 1e-12 * max(1, p) + 1e-30,
      f"diff {d:.4f} ± {half:.4f}, p {p:.3g} vs {t.pvalue:.3g}")

print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
sys.exit(1 if failures else 0)
