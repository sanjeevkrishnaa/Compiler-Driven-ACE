#!/usr/bin/env bash
# Resumable QAOA base-evaluation launcher.  It never touches a QFT study root.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 STUDY_ROOT ACE_PYTHON [WORKERS]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT_ARG="$1"
PYTHON_ARG="$2"
WORKERS="${3:-2}"
ROOT="${ROOT_ARG/#\~/$HOME}"
PYTHON="${PYTHON_ARG/#\~/$HOME}"
[[ "$ROOT" = /* ]] || ROOT="$REPO/$ROOT"
[[ "$PYTHON" = /* ]] || PYTHON="$REPO/$PYTHON"
ROOT="$(cd "$ROOT" && pwd)"

[[ -f "$ROOT/execution_spec.json" ]] || { echo "missing QAOA execution spec" >&2; exit 1; }
[[ -f "$ROOT/manifests/base-evaluation_jobs.jsonl.gz" ]] || { echo "missing QAOA manifest" >&2; exit 1; }
[[ -x "$PYTHON" ]] || { echo "ACE interpreter is not executable: $PYTHON" >&2; exit 1; }

LOCK="$ROOT/.qaoa-pipeline.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "another QAOA pipeline appears to be running: $LOCK" >&2
  exit 1
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

mkdir -p "$ROOT/logs" "$ROOT/summaries"
run_logged() {
  local name="$1"; shift
  "$@" 2>&1 | tee "$ROOT/logs/$name.log"
}

cd "$REPO"
MANIFEST="$ROOT/manifests/base-evaluation_jobs.jsonl.gz"
run_logged base-mesh "$PYTHON" -m tools.golden_study.run_execution \
  --root "$ROOT" --manifest "$MANIFEST" --python "$PYTHON" --workers "$WORKERS" --topology mesh
run_logged base-torus "$PYTHON" -m tools.golden_study.run_execution \
  --root "$ROOT" --manifest "$MANIFEST" --python "$PYTHON" --workers "$WORKERS" --topology torus
run_logged base-summary "$PYTHON" -m tools.golden_study.summarize_execution \
  --root "$ROOT" --manifest "$MANIFEST" \
  --output "$ROOT/summaries/base-evaluation-progress.csv" \
  --status "$ROOT/summaries/base-evaluation-status.json"

# Complete the same post-processing/report stages as the repository's
# run_qft96_all.sh pipeline, but keep the outputs scoped to this QAOA root.
run_logged congestion "$PYTHON" -m tools.golden_study.analyze_qft96_congestion \
  --root "$ROOT" --output "$ROOT/congestion" --capacities "2,3,4,6,8,16,32"
run_logged base-metric-plots "$PYTHON" tools/golden_study/plot_qft96_metrics.py \
  --input "$ROOT/summaries/base-evaluation-progress.csv" --output "$ROOT/figures/metrics"
run_logged dynamic-variant-summary "$PYTHON" tools/golden_study/summarize_qft96_variants.py \
  --root "$ROOT" --output "$ROOT/figures/dynamic-variants"
run_logged report-source "$PYTHON" -m tools.golden_study.make_qaoa_report --root "$ROOT"
if command -v tectonic >/dev/null 2>&1; then
  run_logged report-compile bash -c "cd '$ROOT/report' && tectonic -X compile qaoa_report.tex"
elif command -v pdflatex >/dev/null 2>&1; then
  run_logged report-compile bash -c "cd '$ROOT/report' && pdflatex -interaction=nonstopmode qaoa_report.tex && pdflatex -interaction=nonstopmode qaoa_report.tex"
else
  echo "No tectonic or pdflatex compiler installed; report source and coverage were still generated." | tee "$ROOT/logs/report-compile.log"
fi

echo "QAOA base evaluation complete: $ROOT"
