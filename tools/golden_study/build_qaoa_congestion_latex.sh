#!/usr/bin/env bash
# Rebuild the step-one QAOA LaTeX report and its audited figure/table inputs.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
.venv/bin/python -m tools.golden_study.make_qaoa_congestion_pdf
.venv/bin/python -m tools.golden_study.append_qaoa_metric_results
cd output/pdf/qaoa_methods_congestion
if [[ -n "${TECTONIC_BIN:-}" ]]; then
  "$TECTONIC_BIN" --keep-logs main.tex
elif [[ -x "$REPO/.tools/tectonic/tectonic" ]]; then
  "$REPO/.tools/tectonic/tectonic" --keep-logs main.tex
else
  tectonic --keep-logs main.tex
fi
