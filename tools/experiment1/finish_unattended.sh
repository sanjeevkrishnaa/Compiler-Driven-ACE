#!/bin/sh
# Run Experiment 1 end to end without a person present.
#   1. wait for a running driver if a pid is given (use 999999 for none), then run the main arm (4 jobs in parallel);
#   2. copy results, run_parameters.json and timings.csv into the repository and run analyze.py;
#   3. run the sensitivity arm with ACGP Table I memory parameters (coherence 1 ms, efficiency 0.85), labelled as such;
#   4. run a quiet timing pass: one invocation at a time, so each time is not inflated by parallel jobs;
#   5. write DONE files.  Nothing is committed or pushed.
# usage: finish_unattended.sh DRIVER_PID WORKDIR
pid=$1; work=$2
repo="$(cd "$(dirname "$0")/../.." && pwd)"
py="$repo/../Compiler-Driven-ACE/.venv/bin/python"
cd "$repo" || exit 1
while kill -0 "$pid" 2>/dev/null; do sleep 20; done
copy() { for f in results.csv run_parameters.json timings.csv; do [ -f "$1/$f" ] && cp "$1/$f" "$2/$f"; done; }

dest="$repo/results/experiment1_ten_benchmarks_2026-10-24"; mkdir -p "$dest"
"$py" -B tools/experiment1/run_experiment1.py --resume --jobs 4 --output "$work/exp1" > "$work/exp1.log" 2>&1
copy "$work/exp1" "$dest"; cp "$work/exp1.log" "$dest/driver.log"
"$py" -B tools/experiment1/analyze.py --results "$dest/results.csv" --output "$dest" > "$dest/analysis.log" 2>&1
echo "experiment 1 finished $(date)" > "$dest/DONE"

sens="$repo/results/experiment1_sensitivity_acgp_table1_2026-10-24"; mkdir -p "$sens"
"$py" -B tools/experiment1/run_experiment1.py --resume --jobs 4 --output "$work/sens" \
  --config config/final_config/grid_4x4_ace_3_acgp_table1.json --parameter-set acgp-table1 \
  --only-workloads ghz graphstate draper_qft_adder qaoa qft --budgets 2 4 8 32 --mapping-seeds 42 > "$work/sens.log" 2>&1
copy "$work/sens" "$sens"; cp "$work/sens.log" "$sens/driver.log"
"$py" -B tools/experiment1/analyze.py --results "$sens/results.csv" --output "$sens" > "$sens/analysis.log" 2>&1
echo "sensitivity finished $(date)" > "$sens/DONE"

timing="$repo/results/experiment1_timing_serial_2026-10-24"; mkdir -p "$timing"
"$py" -B tools/experiment1/run_experiment1.py --jobs 1 --budgets 1 2 4 8 32 --mapping-seeds 42 --output "$work/timing" > "$work/timing.log" 2>&1
copy "$work/timing" "$timing"; cp "$work/timing.log" "$timing/driver.log"
echo "timing pass finished $(date)" > "$timing/DONE"
