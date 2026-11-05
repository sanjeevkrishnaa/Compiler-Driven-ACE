"""Run the benchmark study (2026-11-04): 224-qubit benchmarks x route x memories per core K x four strategies.

Agreed with the user on 2026-11-04:
* the default policy of branch history-algo-update (ace/compiler/settings.py) for everything except K and the memory split:
  active-layer basis, lead 1, lookahead 2, age limit 10, generation budget 8, demand guard on, refill on release on,
  trace-order preparation priority, 10 ns empty-layer gap, per-qubit event admission, 50 ms reservations;
* 4x4 mesh, 14 occupied data slots per core (224 logical qubits), traces from tools/benchmark_study/build_traces.py;
* K = 1, 2, 3, 4, 6, 8 and "infinite" (64) communication memories per core.  Dynamic may use all K memories, except
  6 of 8 at K = 8.  CGP and ACGP cache floor(0.75 K) pairs (K = 1: 0, which is ODG; 2: 1; 3: 2; 4: 3; 6: 4; 8: 6;
  infinite: 48), decided after a smoke test showed that caching in all K memories starves requests;
* strategies ODG, CGP, ACGP, Dynamic; physics seeds 60 and 61.
Only run-control flags are added: --audit-events (checks physics and ordering), --stop-after-workload (ends the
simulation when the workload completes) and --record-chain-coverage (records chains at layer opening).

    python tools/benchmark_study/run_matrix.py --benchmarks qft --routes xy [--k ...] [--strategies ...] [--jobs 6]

Each job writes output/benchmark_study/runs/<benchmark>_<route>_K<k>_<strategy>/ and is skipped if its summary.csv exists.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
TRACES = ROOT / "results" / "benchmark_study_2026-11-04" / "traces"
RUNS = ROOT / "output" / "benchmark_study" / "runs"
CONFIG = ROOT / "config" / "final_config" / "grid_4x4_ace_3.json"

BENCHMARKS = ("qft", "bv", "ghz", "dj", "qpeexact", "qaoa", "draper_qft_adder", "graphstate",
              "bmw_quark_cardinality", "bmw_quark_copula")
ROUTES = ("xy", "history")
STRATEGIES = ("on-demand", "continuous", "adaptive-continuous", "dynamic")
K_VALUES = ("1", "2", "3", "4", "6", "8", "inf")
EXTRA_K = ("4all",)      # 4 memories, all 4 for pre-generation in every strategy (asked for on 2026-11-04); run with --k 4all
INFINITE = 64           # memories per core standing in for "infinite"; check_infinite.py confirms it never binds
SEEDS = "60,61"
CAP_MIN = 30            # wall-clock cap for CGP/ACGP at 4all


def memories(k: str, strategy: str = "dynamic") -> tuple[int, int]:
    """(physical memories per core, of which pre-generation may use) for one K and strategy."""
    if k.endswith("all"):                 # every memory available to pre-generation, in every strategy
        total = int(k[:-3])
        return total, total
    total = INFINITE if k == "inf" else int(k)
    if strategy in ("continuous", "adaptive-continuous"):
        return total, (3 * total) // 4
    if k == "inf":
        return total, total
    return total, (6 if total == 8 else total)


GAP_MS = None          # empty-layer gap override in ms; None keeps main's default (10 ns).  Set by --empty-gap-ns.


def command(benchmark: str, route: str, k: str, strategy: str, output: Path) -> list[str]:
    total, compiler = memories(k, strategy)
    # everything not listed here is main's default policy (ace/compiler/settings.py)
    cmd = [sys.executable, "-B", str(ROOT / "run_trace_comparison.py"),
           "--trace", str(TRACES / benchmark / route / "requests.txt"), "--config", str(CONFIG),
           "--strategies", strategy, "--seeds", SEEDS,
           "--total-memories", str(total), "--compiler-memories", str(compiler),
           "--audit-events", "--stop-after-workload", "--record-chain-coverage", "--output", str(output)]
    if strategy in ("continuous", "adaptive-continuous"):
        cmd.append("--autonomous-cache-follows-compiler-memories")
    if GAP_MS is not None:
        cmd += ["--empty-layer-gap-ms", f"{GAP_MS:.12g}"]
    return cmd


def run(job) -> tuple[str, int, float]:
    benchmark, route, k, strategy = job
    name = f"{benchmark}_{route}_K{k}_{strategy}"
    output = RUNS / name
    if (output / "summary.csv").exists() or (output / "did_not_finish.txt").exists():
        return name, 0, 0.0
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [env.get("SEQUENCE_ENGINE", ""), str(ROOT), env.get("PYTHONPATH", "")]))
    start = time.time()
    with (output / "run.log").open("w") as log:
        # CGP/ACGP with every memory cached (4all) starve requests and may never finish: cap them and record it
        cap = CAP_MIN * 60 if (k.endswith("all") and strategy in ("continuous", "adaptive-continuous")) else None
        try:
            code = subprocess.run(command(benchmark, route, k, strategy, output), cwd=ROOT, env=env,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=cap).returncode
        except subprocess.TimeoutExpired:
            (output / "did_not_finish.txt").write_text(f"stopped after {CAP_MIN} min (cache fills every memory; requests starve)\n")
            code = 0
    if code:
        (output / "failed.txt").write_text(f"exit {code}\n")
    return name, code, time.time() - start


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--benchmarks", nargs="+", default=list(BENCHMARKS))
    parser.add_argument("--routes", nargs="+", default=list(ROUTES))
    parser.add_argument("--k", nargs="+", default=list(K_VALUES))
    parser.add_argument("--strategies", nargs="+", default=list(STRATEGIES))
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--empty-gap-ns", type=float, help="override the empty-layer gap (ns); runs go to runs_gap<ns>ns/")
    args = parser.parse_args()
    global GAP_MS, RUNS
    if args.empty_gap_ns is not None:
        GAP_MS = args.empty_gap_ns * 1e-6
        RUNS = RUNS.parent / f"runs_gap{args.empty_gap_ns:g}ns"
    # largest workloads first, so the long jobs do not end up last
    order = {name: i for i, name in enumerate(("qaoa", "qpeexact", "qft", "bmw_quark_copula", "draper_qft_adder"))}
    jobs = sorted(((b, r, k, s) for b in args.benchmarks for r in args.routes for k in args.k for s in args.strategies),
                  key=lambda job: (order.get(job[0], 99), job))
    print(f"{len(jobs)} jobs, seeds {SEEDS}", flush=True)
    if args.dry_run:
        print(" ".join(command(*jobs[0], RUNS / "dry-run")))
        return
    done = failed = 0
    with ThreadPoolExecutor(args.jobs) as pool:
        for name, code, seconds in pool.map(run, jobs):
            done += 1
            failed += bool(code)
            print(f"[{done}/{len(jobs)}] {'FAIL' if code else 'ok  '} {name} {seconds / 60:.1f} min", flush=True)
    print(f"finished: {done - failed} ok, {failed} failed")


if __name__ == "__main__":
    main()
