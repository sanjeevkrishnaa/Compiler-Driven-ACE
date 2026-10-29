#!/bin/bash
# Memory occupancy for each routing arm on physics seeds 0-2 (same ACE settings as run_routing_arms.sh).
set -u
R=results/routing_study_2026-10-25
O=$R/occupancy; mkdir -p $O
for arm in original xy yx shortest_reliable max_reliability; do
  if [ $arm = original ]; then T="$(pwd)/../qft_requests.txt"; else T=$R/qft96/$arm/requests.txt; fi
  ../Compiler-Driven-ACE/.venv/bin/python tools/diagnostics/occupancy.py --out $O/$arm.json -- --trace "$T" \
    --strategies on-demand,dynamic --seeds 0,1,2 --total-memories 4 --compiler-memories 3 --generation-capacity 3 \
    --scheduler per-qubit --admission event --pregeneration-buffer-ms 0 --stop-after-workload --stop-time-s 200 \
    --output $O/run_$arm > $O/$arm.log 2>&1
done
