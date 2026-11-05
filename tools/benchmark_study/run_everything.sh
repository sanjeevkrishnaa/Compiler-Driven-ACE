#!/bin/zsh
# One command for the whole benchmark study on branch history-algo-update.
#   tools/benchmark_study/run_everything.sh                 # all 10 benchmarks, XY + history, K=1,2,3,4,6,8,inf and 4-of-4
#   tools/benchmark_study/run_everything.sh qft bv          # only the named benchmarks
# Safe to stop and restart: finished runs (summary.csv exists) are skipped.  Logs: output/benchmark_study/run_everything.log
# Output: results/benchmark_study_2026-11-04/benchmark_study.xlsx (master workbook), docs/latex/benchmark_study/main.pdf
BTP="/Users/dhruvrpansuriya/Documents/IITG Acad/Sem 7/BTP"
cd "$(dirname "$0")/../.." || exit 1
export SEQUENCE_ENGINE="$BTP/SeQUeNCe-0.8.1"
SIM="$BTP/Compiler-Driven-ACE/.venv/bin/python"      # simulator environment
ANA="$BTP/venv_bench/bin/python"                     # pandas + openpyxl + matplotlib
JOBS=${JOBS:-8}
if (( $# )); then LIST=("$@"); else
  LIST=(qft bv ghz dj qpeexact qaoa draper_qft_adder graphstate bmw_quark_cardinality bmw_quark_copula); fi
mkdir -p output/benchmark_study
{
echo "=== branch: $(git branch --show-current) commit: $(git rev-parse --short HEAD) start $(date)"
echo "=== 1. routes (XY and history) from the frozen mappings"
"$SIM" tools/benchmark_study/build_traces.py --jobs 6 || exit 1
for b in $LIST; do
  echo "=== $b started $(date '+%H:%M:%S')"
  "$SIM" tools/benchmark_study/run_matrix.py --benchmarks $b --k 1 2 3 4 6 8 inf --jobs $JOBS | tail -2
  # 4 memories, all 4 for pre-generation. CGP/ACGP may starve here; run_matrix stops them after 30 min (did_not_finish.txt)
  "$SIM" tools/benchmark_study/run_matrix.py --benchmarks $b --k 4all --jobs $JOBS | tail -1
  "$ANA" tools/benchmark_study/analyze.py | grep -E "runs found|runs missing|completion|violations"
  "$ANA" tools/benchmark_study/report.py | tail -1
  (cd docs/latex/benchmark_study && tectonic main.tex >/dev/null 2>&1 && echo "report rebuilt")
  echo "=== $b finished $(date '+%H:%M:%S')"
done
echo ALLDONE
} 2>&1 | tee -a output/benchmark_study/run_everything.log
