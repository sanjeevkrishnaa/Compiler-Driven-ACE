#!/bin/bash
# Run one routing arm through identical ACE settings (the settings of results/qft96_physical_per_qubit_30seed_2026-10-25).
# usage: run_routing_arms.sh <arm name> <requests file> <output dir>
set -u
ARM="$1"; TRACE="$2"; OUT="$3"
mkdir -p "$OUT"
exec ../Compiler-Driven-ACE/.venv/bin/python run_trace_comparison.py --trace "$TRACE" \
  --strategies on-demand,dynamic --seeds 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29 \
  --total-memories 4 --compiler-memories 3 --generation-capacity 3 --scheduler per-qubit --admission event \
  --pregeneration-buffer-ms 0 --stop-after-workload --stop-time-s 200 --output "$OUT" > "$OUT/run.log" 2>&1
