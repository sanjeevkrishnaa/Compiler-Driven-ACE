#!/bin/sh
# Finish Experiment 1 without a person present, then run the physical-parameter sensitivity arm.
#   1. wait for the running driver (pid given), then resume: any invocation missing on disk is run, results.csv rebuilt;
#   2. copy results into the repository, run analyze.py (controls, tables, figures);
#   3. run the sensitivity arm with ACGP Table I memory parameters (coherence 1 ms, efficiency 0.85), labelled as such;
#   4. write DONE files.  Nothing is committed or pushed.
# usage: finish_unattended.sh DRIVER_PID WORKDIR
pid=$1; work=$2
repo="$(cd "$(dirname "$0")/../.." && pwd)"
py="$repo/../Compiler-Driven-ACE/.venv/bin/python"
cd "$repo" || exit 1
while kill -0 "$pid" 2>/dev/null; do sleep 20; done
dest="$repo/results/experiment1_ten_benchmarks_2026-10-24"; mkdir -p "$dest"
"$py" -B tools/experiment1/run_experiment1.py --resume --jobs 4 --output "$work/exp1" > "$work/exp1_resume.log" 2>&1
cp "$work/exp1/results.csv" "$dest/results.csv" && cp "$work/exp1_resume.log" "$dest/driver_resume.log"
"$py" -B tools/experiment1/analyze.py --results "$dest/results.csv" --output "$dest" > "$dest/analysis.log" 2>&1
echo "experiment 1 finished $(date)" > "$dest/DONE"
sens="$repo/results/experiment1_sensitivity_acgp_table1_2026-10-24"; mkdir -p "$sens"
"$py" -B tools/experiment1/run_experiment1.py --resume --jobs 4 --output "$work/sens" \
  --config config/final_config/grid_4x4_ace_3_acgp_table1.json --parameter-set acgp-table1 \
  --only-workloads ghz graphstate draper_qft_adder qaoa qft --budgets 2 4 8 32 --mapping-seeds 42 > "$work/sens.log" 2>&1
cp "$work/sens/results.csv" "$sens/results.csv" && cp "$work/sens.log" "$sens/driver.log"
"$py" -B tools/experiment1/analyze.py --results "$sens/results.csv" --output "$sens" > "$sens/analysis.log" 2>&1
echo "sensitivity finished $(date)" > "$sens/DONE"
