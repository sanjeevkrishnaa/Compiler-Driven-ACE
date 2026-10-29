"""Where does the waiting happen?  Per-core admission wait and saturation, from inside the simulator.

``run``: simulate ONE strategy on a hop file and write, per physics seed,
  * for every core: requests that touched it as an endpoint of their migration / as a relay, the admission wait of those requests
    (a request that needs two cores is counted at both), and the share of admission checks at which the core had no free memory;
  * the same totals for the whole run.
``compare``: put two or more such files side by side and test whether the waiting follows the cores' static relay load.

Roles come from the hop trace itself: in a qubit's chain of hops within a layer, the first hop's source and the last hop's destination
are the migration's endpoints; every other core a hop touches is a relay.

    python tools/mapper_ace/per_core_wait.py run --trace T --strategy on-demand --seeds 0,1,2 --out F.json
    python tools/mapper_ace/per_core_wait.py compare A=F1.json B=F2.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "diagnostics"))

PS_PER_MS = 10**9


def run(args) -> int:
    import occupancy                                                   # noqa: E402  (AdmissionLog)
    import run_trace_comparison as runner                              # noqa: E402
    from request_scheduler import QubitOrderedRequestManager           # noqa: E402

    captured = []
    real = runner.run_parallel_experiment

    def wrapper(*a, **kw):
        log = occupancy.AdmissionLog()
        original = log.install(QubitOrderedRequestManager)
        try:
            result = real(*a, **kw)
        finally:
            QubitOrderedRequestManager._free_memories = original
        captured.append((result, kw["request_plan"], log))
        return result

    runner.run_parallel_experiment = wrapper
    out_dir = args.out.with_suffix("") .parent / (args.out.stem + "_run")
    sys.argv = ["run_trace_comparison.py", "--trace", str(args.trace), "--strategies", args.strategy, "--seeds", args.seeds,
                "--total-memories", str(args.total_memories), "--compiler-memories", str(args.compiler_memories),
                "--generation-capacity", "3", "--scheduler", "per-qubit", "--admission", "event", "--pregeneration-buffer-ms", "0",
                "--stop-after-workload", "--stop-time-s", "200", "--output", str(out_dir)]
    runner.main()
    seeds = [int(s) for s in args.seeds.split(",")]
    records = []
    for seed, (result, plan, log) in zip(seeds, captured):
        manager = result["request_manager"]
        chains = defaultdict(list)
        for request in plan:
            chains[(request.layer, request.qubit)].append(request)
        n_cores = runner.parse_compiler_trace(args.trace).core_count        # from the trace header, not from the cores that happen to appear
        endpoint_touch, relay_touch = [0] * n_cores, [0] * n_cores
        endpoint_wait, relay_wait = [0.0] * n_cores, [0.0] * n_cores
        waited = [0] * n_cores
        total_wait, count = 0.0, 0
        for hops in chains.values():
            hops.sort(key=lambda r: r.order)
            for index, request in enumerate(hops):
                if request.request_id not in manager.request_admission_times or request.request_id not in manager.request_eligible_times:
                    continue
                wait = (manager.request_admission_times[request.request_id] - manager.request_eligible_times[request.request_id]) / PS_PER_MS
                total_wait += wait
                count += 1
                roles = ((request.source_core, "endpoint" if index == 0 else "relay"),
                         (request.destination_core, "endpoint" if index == len(hops) - 1 else "relay"))
                for core, role in roles:
                    if role == "endpoint":
                        endpoint_touch[core] += 1
                        endpoint_wait[core] += wait
                    else:
                        relay_touch[core] += 1
                        relay_wait[core] += wait
                    waited[core] += wait > 1e-3
        columns = int(result["config_columns"]) if "config_columns" in result else 4
        checks, full = [0] * n_cores, [0] * n_cores
        for _, name, _, free, _ in log.checks:
            core = int(name.split("_")[1]) * columns + int(name.split("_")[2])
            checks[core] += 1
            full[core] += free <= 0
        records.append({"seed": seed, "requests": count, "mean_wait_ms": total_wait / count,
                        "endpoint_touches": endpoint_touch, "relay_touches": relay_touch,
                        "endpoint_wait_ms": endpoint_wait, "relay_wait_ms": relay_wait, "requests_that_waited": waited,
                        "admission_checks": checks, "checks_with_no_free_memory": full})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"trace": str(args.trace), "strategy": args.strategy, "total_memories": args.total_memories,
                                    "per_seed": records}, indent=1), encoding="utf-8")
    return 0


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    ma, mb = fmean(ra), fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return num / den if den else float("nan")


def compare(args) -> int:
    loads = json.loads(Path(args.static).read_text(encoding="utf-8"))
    for item in args.files:
        label, path = item.split("=", 1)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        n = len(data["per_seed"][0]["endpoint_touches"])
        mean = lambda key: [fmean(s[key][c] for s in data["per_seed"]) for c in range(n)]       # noqa: E731
        wait = [a + b for a, b in zip(mean("endpoint_wait_ms"), mean("relay_wait_ms"))]
        full = [a / b if b else 0.0 for a, b in zip(mean("checks_with_no_free_memory"), mean("admission_checks"))]
        total = sum(wait) or 1.0
        top = sorted(range(n), key=lambda c: -wait[c])[:3]
        relay_static = loads[args.static_key or label]["relay_touches_by_core"] if (args.static_key or label) in loads else None
        excess = loads[args.static_key or label]["excess_by_core_C4"] if (args.static_key or label) in loads else None
        print(f"== {label}  ({data['strategy']}, {len(data['per_seed'])} seeds, mean wait per request {fmean(s['mean_wait_ms'] for s in data['per_seed']):.4f} ms)")
        print(f"   touch-weighted wait by core (ms, mean over seeds): " + " ".join(f"{c}:{wait[c]:.0f}" for c in range(n)))
        print(f"   top-3 cores {top} hold {sum(wait[c] for c in top) / total:.1%} of touch-weighted wait")
        print(f"   share of admission checks with no free memory, busiest: " + ", ".join(f"core {c} {full[c]:.1%}" for c in sorted(range(n), key=lambda c: -full[c])[:3]))
        if relay_static:
            print(f"   Spearman(core wait, static relay touches) = {spearman(wait, relay_static):+.3f};  (core wait, static excess C=4) = {spearman(wait, excess):+.3f};  "
                  f"(core full-share, static excess C=4) = {spearman(full, excess):+.3f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--trace", type=Path, required=True)
    r.add_argument("--strategy", required=True, choices=("on-demand", "dynamic"))
    r.add_argument("--seeds", default="0,1,2")
    r.add_argument("--total-memories", type=int, default=4)
    r.add_argument("--compiler-memories", type=int, default=3)
    r.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("files", nargs="+")
    c.add_argument("--static", default=str(ROOT / "results/why_xy_2026-10-25/static_load_all.json"))
    c.add_argument("--static-key", default=None)
    args = parser.parse_args()
    return run(args) if args.command == "run" else compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
