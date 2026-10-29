#!/bin/bash
# Run every intervention arm (ODG + dynamic, 30 seeds, routing-study settings), N at a time.
# usage: run_intervention_pool.sh <interventions dir> <runs dir> <parallel jobs>
set -u
IN="$1"; OUT="$2"; JOBS="${3:-6}"
mkdir -p "$OUT"
ls "$IN" | grep -v json | xargs -P "$JOBS" -I{} bash -c "[ -f $OUT/{}/summary.csv ] || tools/mapper_ace/run_routing_arms.sh {} $IN/{}/requests.txt $OUT/{}"
