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

echo "QAOA base evaluation complete: $ROOT"
