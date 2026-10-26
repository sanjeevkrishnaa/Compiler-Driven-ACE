#!/usr/bin/env bash
# Resumable end-to-end QFT-96 experiment pipeline.
#
# Usage:
#   bash tools/golden_study/run_qft96_all.sh \
#     results/qft96_2seed_2026-10-26 \
#     /absolute/path/to/Compiler-Driven-ACE/.venv/bin/python \
#     2
#
# The simulation runners validate job hashes and atomically promote completed
# outputs, so this script may be re-run after interruption.  Do not run two
# copies against the same study root concurrently.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 STUDY_ROOT ACE_PYTHON [WORKERS]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT_ARG="$1"
ACE_PYTHON_ARG="$2"
WORKERS="${3:-2}"

if [[ "$ROOT_ARG" = /* ]]; then ROOT="$ROOT_ARG"; else ROOT="$REPO/$ROOT_ARG"; fi
if [[ "$ACE_PYTHON_ARG" = /* ]]; then ACE_PYTHON="$ACE_PYTHON_ARG"; else ACE_PYTHON="$REPO/$ACE_PYTHON_ARG"; fi
ROOT="$(cd "$ROOT" && pwd)"

SCOPE_FILE="$ROOT/execution_scope.json"
if [[ -f "$SCOPE_FILE" ]]; then
  BASE_MANIFEST_REL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["base_manifest"])' "$SCOPE_FILE")"
  CONGESTION_CAPACITIES="$(python3 -c 'import json,sys; print(",".join(map(str,json.load(open(sys.argv[1]))["included_total_memories_per_core"])))' "$SCOPE_FILE")"
else
  BASE_MANIFEST_REL="manifests/base-evaluation_jobs.jsonl.gz"
  CONGESTION_CAPACITIES="2,3,4,6,8,16,32,64"
fi
BASE_MANIFEST="$ROOT/$BASE_MANIFEST_REL"

[[ -x "$ACE_PYTHON" ]] || { echo "ACE interpreter is not executable: $ACE_PYTHON" >&2; exit 1; }
[[ -f "$ROOT/execution_spec.json" ]] || { echo "missing execution_spec.json under $ROOT" >&2; exit 1; }
[[ -f "$BASE_MANIFEST" ]] || { echo "missing scoped base manifest: $BASE_MANIFEST" >&2; exit 1; }

LOCK="$ROOT/.qft96-pipeline.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "another QFT-96 pipeline appears to be running (lock: $LOCK)" >&2
  exit 1
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

run_logged() {
  local name="$1"; shift
  echo
  echo "===== [$name] $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
  "$@" 2>&1 | tee "$LOG_DIR/$name.log"
}

cd "$REPO"
BASE_SUMMARY="$ROOT/summaries/base-evaluation-progress.csv"
BASE_STATUS="$ROOT/summaries/base-evaluation-status.json"

echo "Official base manifest: $BASE_MANIFEST"
echo "Official memory capacities: $CONGESTION_CAPACITIES"

run_logged base-mesh python3 -m tools.golden_study.run_execution \
  --root "$ROOT" --manifest "$BASE_MANIFEST" --python "$ACE_PYTHON" \
  --workers "$WORKERS" --topology mesh

run_logged base-torus python3 -m tools.golden_study.run_execution \
  --root "$ROOT" --manifest "$BASE_MANIFEST" --python "$ACE_PYTHON" \
  --workers "$WORKERS" --topology torus

run_logged dynamic-variants python3 -m tools.golden_study.run_qft96_dynamic_variants \
  --root "$ROOT" --python "$ACE_PYTHON" --workers "$WORKERS" --run

run_logged base-summary python3 -m tools.golden_study.summarize_execution \
  --root "$ROOT" --manifest "$BASE_MANIFEST" --output "$BASE_SUMMARY" --status "$BASE_STATUS"

run_logged congestion "$ACE_PYTHON" -m tools.golden_study.analyze_qft96_congestion \
  --root "$ROOT" --output "$ROOT/congestion" --capacities "$CONGESTION_CAPACITIES"

run_logged base-metric-plots "$ACE_PYTHON" tools/golden_study/plot_qft96_metrics.py \
  --input "$BASE_SUMMARY" --output "$ROOT/figures/metrics"

run_logged dynamic-variant-summary "$ACE_PYTHON" \
  tools/golden_study/summarize_qft96_variants.py \
  --root "$ROOT" --output "$ROOT/figures/dynamic-variants"

run_logged report-compile bash -c \
  "cd \"$REPO/docs/latex/ace_report\" && tectonic -X compile main.tex"

echo
echo "QFT-96 pipeline complete or fully resumed."
echo "Study root: $ROOT"
echo "Logs:       $LOG_DIR"
echo "Tables:     $ROOT/summaries and $ROOT/figures"
echo "Heatmaps:   $ROOT/congestion"
echo "Report PDF: $REPO/docs/latex/ace_report/main.pdf"
