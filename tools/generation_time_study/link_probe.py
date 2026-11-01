"""One on-demand request on one link, repeated over many seeds, on the real ACE stack.

Counts the physical attempts of every delivered pair, so the attempt distribution and the time per
attempt are measured separately instead of being inferred from their product.  Each process runs
one knob setting, because the knobs are process-wide constants.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import math
from pathlib import Path
import statistics
import tempfile

import knobs as kn


def mini_trace(path: Path, source: int, destination: int) -> None:
    path.write_text("\n".join((
        "// Number of cores", "16", "// Number of qubit slots per core", "12",
        "// Number of qubits", "1", "// Initial placement: (qubit, core)", f"(0, {source})",
        "// Inter-core communication requests: (qubit, src, dst)", "// Layer 0",
        f"(0, {source}, {destination})", "")))


def mean_ci(values: list[float]) -> tuple[float, float]:
    mean = statistics.fmean(values)
    half = 1.96 * statistics.stdev(values) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return mean, half


def probe(settings: kn.Knobs, source: int, destination: int, samples: int, first_seed: int) -> dict:
    kn.patch_runtime(settings)
    from ace.compiler.compiler_trace import parse_compiler_trace, to_ace_layers
    from ace.protocols import generation
    from ace.simulation.parallel_core import run_parallel_experiment

    source_name = f"router_{source // 4}_{source % 4}"
    protocol = generation.ShEntanglementGenerationAadaptive
    failures = collections.Counter()
    original_fail = protocol._entanglement_fail

    def counting_fail(self):
        if self.from_app_request and self.owner.name == source_name:
            failures["attempts"] += 1
        return original_fail(self)

    protocol._entanglement_fail = counting_fail
    rows, errors = [], []
    with tempfile.TemporaryDirectory() as folder:
        trace_path, config_path = Path(folder) / "trace.txt", Path(folder) / "config.json"
        mini_trace(trace_path, source, destination)
        kn.write_config(config_path, settings)
        trace = parse_compiler_trace(trace_path)
        layers = to_ace_layers(trace, columns=4)
        spec = dict(requests=trace.requests, schedule=(), strategy="on-demand", columns=4, planner_blocked=0,
                    planner_peak_memory=0, compiler_memories_per_core=0, fidelity=0.01,
                    reservation_duration_ms=50.0)
        for seed in range(first_seed, first_seed + samples):
            failures.clear()
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = run_parallel_experiment(str(config_path), False, False, layers, 0.0, 50.0, f"probe{seed}",
                                                     seed=seed, compiler_spec=spec, scheduler="per-qubit",
                                                     request_plan=trace.requests, stop_after_workload=True)
                parts = result["request_manager"].get_statistics()["timing_breakdown"][0]
                fidelities = [f for values in result["fidelity_dict"].values() for f in values]
                rows.append(dict(attempts=failures["attempts"] + 1,
                                 generation_ms=parts["entanglement_generation_time_ms"],
                                 guard_ms=parts["reservation_start_delay_time_ms"],
                                 total_ms=parts["total_time_ms"],
                                 retries=parts["retry_count"],
                                 fidelity=statistics.fmean(fidelities) if fidelities else None))
            except Exception as exc:        # recorded, never hidden: a failing setting is itself a result
                errors.append(f"{seed}: {type(exc).__name__}: {str(exc)[:160]}")
    if not rows:
        return dict(samples=0, errors=errors[:5], error_count=len(errors))
    attempts = [r["attempts"] for r in rows]
    generation_ms = [r["generation_ms"] for r in rows]
    per_attempt = [g / a for g, a in zip(generation_ms, attempts) if a]
    fidelity = [r["fidelity"] for r in rows if r["fidelity"] is not None]
    return dict(samples=len(rows), error_count=len(errors), errors=errors[:5],
                attempts_mean=mean_ci(attempts)[0], attempts_ci=mean_ci(attempts)[1],
                generation_mean_ms=mean_ci(generation_ms)[0], generation_ci_ms=mean_ci(generation_ms)[1],
                generation_p50_ms=statistics.median(generation_ms),
                generation_p95_ms=sorted(generation_ms)[int(0.95 * (len(generation_ms) - 1))],
                generation_max_ms=max(generation_ms),
                ms_per_attempt_mean=statistics.fmean(per_attempt), ms_per_attempt_min=min(per_attempt),
                ms_per_attempt_max=max(per_attempt),
                guard_mean_ms=statistics.fmean(r["guard_ms"] for r in rows),
                retries_mean=statistics.fmean(r["retries"] for r in rows),
                fidelity_mean=statistics.fmean(fidelity) if fidelity else None,
                attempt_histogram={str(k): v for k, v in sorted(collections.Counter(attempts).items())})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knobs", default="{}", help="JSON object of Knobs fields")
    parser.add_argument("--source", type=int, default=0)
    parser.add_argument("--destination", type=int, default=1)
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--first-seed", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = kn.Knobs(**json.loads(args.knobs))
    result = probe(settings, args.source, args.destination, args.samples, args.first_seed)
    result.update(knobs=settings.overrides(), key=settings.key(), source=args.source, destination=args.destination,
                  predicted_p=kn.success_probability(settings),
                  predicted_messages=kn.attempt_messages(args.source, args.destination))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
