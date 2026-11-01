"""Flatten the single-link probes and compare each with the prediction of H1."""
from __future__ import annotations

import json
import math

import pandas as pd

import knobs as kn
from collect import DATA

LINK = kn.ROOT / "output" / "generation_time_study" / "link"


def main() -> None:
    rows, histograms = [], {}
    for path in sorted(LINK.glob("*.json")):
        record = json.loads(path.read_text())
        settings = kn.Knobs(**record["knobs"])
        delay_ms = 0.1 * settings.classical_scale + kn.LINK_METRES * settings.distance_scale * 2 / 2e-4 / 1e9
        name = next(iter(record["knobs"]), "base")
        row = dict(knob=name, value=record["knobs"].get(name, math.nan), source=record["source"], destination=record["destination"],
                   samples=record.get("samples", 0), errors=record.get("error_count", 0), predicted_p=record["predicted_p"],
                   predicted_attempts=1 / record["predicted_p"], messages=record["predicted_messages"],
                   predicted_generation_ms=record["predicted_messages"] * delay_ms / record["predicted_p"],
                   note=(record.get("errors") or [""])[0][:100])
        for field in ("attempts_mean", "attempts_ci", "generation_mean_ms", "generation_ci_ms", "generation_p50_ms", "generation_p95_ms",
                      "generation_max_ms", "ms_per_attempt_mean", "ms_per_attempt_min", "ms_per_attempt_max", "guard_mean_ms",
                      "retries_mean", "fidelity_mean"):
            row[field] = record.get(field, math.nan)
        rows.append(row)
        if name == "base":
            histograms[f"{record['source']}->{record['destination']}"] = record.get("attempt_histogram", {})
    table = pd.DataFrame(rows)
    table["error_percent"] = 100 * (table["generation_mean_ms"] / table["predicted_generation_ms"] - 1)
    table.to_csv(DATA / "link_screen.csv", index=False, float_format="%.6g")
    (DATA / "link_attempt_histograms.json").write_text(json.dumps(histograms, indent=1))
    print(len(table), "probes,", int((table["samples"] == 0).sum()), "with no sample")


if __name__ == "__main__":
    main()
