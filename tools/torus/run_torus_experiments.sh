#!/bin/sh
# Torus experiments, unattended: structural heatmap and own-vs-relay split, then Experiment 1 (latency, fidelity, waiting).
# usage: run_torus_experiments.sh WORKDIR     (nothing is committed or pushed)
work=$1
repo="$(cd "$(dirname "$0")/../.." && pwd)"
py="$repo/../Compiler-Driven-ACE/.venv/bin/python"
traces="$repo/results/torus_traces_2026-10-24"
cd "$repo" || exit 1
heat="$repo/results/heatmap_torus_2026-10-24"; mkdir -p "$heat"
"$py" -B tools/heatmap/regenerate_heatmap.py --topology torus --traces-dir "$traces" --output "$heat" > "$heat/log.txt" 2>&1
for cap in 1 2 3 4; do
  "$py" -B tools/experiment2/split_congestion.py --topology torus --traces-dir "$traces" --capacity $cap \
    --output "$repo/results/experiment2_torus_2026-10-24/capacity_$cap" > "$work/exp2_$cap.log" 2>&1
done
dest="$repo/results/experiment1_torus_2026-10-24"; mkdir -p "$dest"
"$py" -B tools/experiment1/run_experiment1.py --topology torus --traces-dir "$traces" --parameter-set torus-ace-default \
  --jobs 4 --output "$work/exp1" > "$work/exp1.log" 2>&1
for f in results.csv run_parameters.json timings.csv; do [ -f "$work/exp1/$f" ] && cp "$work/exp1/$f" "$dest/$f"; done
cp "$work/exp1.log" "$dest/driver.log"
"$py" -B tools/experiment1/analyze.py --topology torus --traces-dir "$traces" --results "$dest/results.csv" --output "$dest" > "$dest/analysis.log" 2>&1
echo "torus experiments finished $(date)" > "$dest/DONE"
