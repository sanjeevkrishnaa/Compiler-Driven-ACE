# Benchmark study: how to run it

Final setting (decided 2026-11-05): 4x4 mesh, 224 logical qubits (16 x 14), 8 memories per core with 6 for pre-generation,
Dynamic planner lead 1 / lookahead 2 / age limit 10 / launch budget 8, history routing over ALL past layers (cumulative,
routing capacity 8), XY and history routes, strategies ODG, CGP, ACGP, Dynamic, seeds 60 and 61.
Memories per core K = 1, 2, 3, 4, 6, 8, infinity (64), plus "4all" (4 memories, all 4 for pre-generation).
CGP and ACGP cache floor(0.75 K) pairs. At 4all they starve, so they are stopped after 30 minutes and marked
`did_not_finish.txt` (shown as n/a).

## One-time setup
    BTP="/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP"
    # simulator env:  $BTP/Compiler-Driven-ACE/.venv   (SeQUeNCe at $BTP/SeQUeNCe-0.8.1)
    # analysis env (pandas, openpyxl, matplotlib):
    python3 -m venv "$BTP/venv_bench" && "$BTP/venv_bench/bin/pip" install pandas openpyxl matplotlib
    # tectonic (LaTeX) must be installed:  brew install tectonic

## The ten commands (run ONE AT A TIME, from the repository root, wait for ALLDONE before the next)
    tools/benchmark_study/run_everything.sh qft
    tools/benchmark_study/run_everything.sh bv
    tools/benchmark_study/run_everything.sh ghz
    tools/benchmark_study/run_everything.sh dj
    tools/benchmark_study/run_everything.sh qpeexact
    tools/benchmark_study/run_everything.sh qaoa
    tools/benchmark_study/run_everything.sh draper_qft_adder
    tools/benchmark_study/run_everything.sh graphstate
    tools/benchmark_study/run_everything.sh bmw_quark_cardinality
    tools/benchmark_study/run_everything.sh bmw_quark_copula
(`run_everything.sh` with no argument runs all ten in this order.) Do not start two at once: they share the workbook.
Use `JOBS=6 tools/benchmark_study/run_everything.sh qft` to use fewer parallel simulations (default 8).
Stopping and restarting is safe: finished runs are skipped.

Each command, for its benchmark: routes the frozen mapping (XY, history) -> runs 2 routes x 8 K values x 4 strategies
(8 x 4 x 2 = 64 simulations, 2 seeds each) -> refreshes the workbook -> refreshes the LaTeX report and PDF.

## Results
* Master workbook: `results/benchmark_study_2026-11-04/benchmark_study.xlsx` (README, Summary, PerSeed, one tab per metric,
  per-hop lead tabs, Checks, one tab per benchmark and route). The Checks tab must show: runs missing = 0 (4 per
  benchmark are expected for CGP/ACGP at 4all), completion < 1: 0, audit violations: 0.
* Report with tables and graphs: `docs/latex/benchmark_study/main.pdf` (tables and figures in `generated/`, `figures/`).
* Per-hop data: `results/benchmark_study_2026-11-04/per_hop/`, raw runs: `output/benchmark_study/runs/`, log:
  `output/benchmark_study/run_everything.log`.
