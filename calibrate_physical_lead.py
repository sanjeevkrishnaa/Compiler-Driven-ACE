"""Derive an explicit dynamic-scheduler lead from physical ACE observations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from math import ceil
import json
from pathlib import Path
from statistics import fmean


def quantile(values: list[float], probability: float) -> float:
    """Linearly interpolated empirical quantile (inclusive endpoints)."""
    if not values:
        raise ValueError("cannot calculate a quantile of an empty sample")
    if not 0 <= probability <= 1:
        raise ValueError("quantile probability must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def derive_profile(payload: dict, service_quantile: float,
                   layer_quantile: float, safety_factor: float) -> dict:
    service_ms = []
    layer_ms = []
    for run in payload["runs"]:
        for timing in run.get("simulator_timing_breakdown", {}).values():
            service_ms.append(float(timing["total_time_ms"]))
        layer_ms.extend(float(value) for value in
                        run.get("simulator_layer_latencies_ms", {}).values())
    if not service_ms or not layer_ms:
        raise ValueError(
            "runs.json does not contain physical timing samples; regenerate it "
            "with the current runner"
        )
    service_bound = quantile(service_ms, service_quantile) * safety_factor
    reference_layer = quantile(layer_ms, layer_quantile)
    if reference_layer <= 0:
        raise ValueError("calibration layer duration must be positive")
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "method": "empirical_service_quantile_over_layer_quantile",
        "service_quantile": service_quantile,
        "layer_duration_quantile": layer_quantile,
        "safety_factor": safety_factor,
        "service_samples": len(service_ms),
        "layer_samples": len(layer_ms),
        "mean_service_time_ms": fmean(service_ms),
        "service_bound_ms": service_bound,
        "reference_layer_duration_ms": reference_layer,
        "dynamic_min_lead_layers": max(1, ceil(service_bound / reference_layer)),
        "source_trace_sha256": payload.get("trace_sha256"),
        "source_config_sha256": payload.get("config_sha256"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", type=Path)
    parser.add_argument("--service-quantile", required=True, type=float)
    parser.add_argument("--layer-quantile", required=True, type=float)
    parser.add_argument("--safety-factor", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.safety_factor <= 0:
        parser.error("--safety-factor must be positive")
    profile = derive_profile(
        json.loads(args.runs.read_text(encoding="utf-8")),
        args.service_quantile, args.layer_quantile, args.safety_factor,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    main()
