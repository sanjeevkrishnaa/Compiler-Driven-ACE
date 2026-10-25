#!/bin/bash
# T3: per-core wait for the supplied and the XY routes, ODG and dynamic, physics seeds 0-4.
set -u
O=results/why_xy_2026-10-25/per_core; mkdir -p $O
for arm in original xy yx; do
  if [ $arm = original ]; then T="$(pwd)/../qft_requests.txt"; else T=results/routing_study_2026-10-25/qft96/$arm/requests.txt; fi
  for s in on-demand dynamic; do
    [ -f $O/${arm}_$s.json ] || ../Compiler-Driven-ACE/.venv/bin/python tools/mapper_ace/per_core_wait.py run --trace "$T" --strategy $s --seeds 0,1,2,3,4 --out $O/${arm}_$s.json > $O/${arm}_$s.log 2>&1
  done
done
