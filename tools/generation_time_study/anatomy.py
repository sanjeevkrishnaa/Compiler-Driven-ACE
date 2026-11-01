"""Message-level timeline of one EPR delivery, for a miss and for a hit, in both hop directions.

Every classical message and protocol step of a single request is logged with its simulation time
by wrapping methods in this process.  The timeline in the report is this output, not a reconstruction.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
from pathlib import Path
import sys
import tempfile

import knobs as kn


def mini_trace(path: Path, source: int, destination: int, layer: int) -> None:
    lines = ["// Number of cores", "16", "// Number of qubit slots per core", "12", "// Number of qubits", "1",
             "// Initial placement: (qubit, core)", f"(0, {source})",
             "// Inter-core communication requests: (qubit, src, dst)"]
    for index in range(layer + 1):
        lines.append(f"// Layer {index}")
    lines += [f"(0, {source}, {destination})", ""]
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    kn.add_paths()
    from ace.cli import run_trace_comparison as cli
    from ace.protocols import generation
    from ace.protocols.adaptive_continuous import AdaptiveContinuousProtocol
    from ace.resources.reservation import ResourceReservationProtocolAdaptive
    from ace.resources.resource_manager import ResourceManagerAdaptive
    from ace.simulation import request_scheduler

    log: list[tuple] = []
    times: dict = {}
    protocol = generation.ShEntanglementGenerationAadaptive

    def wrap(cls, name, describe):
        original = getattr(cls, name)

        def wrapped(self, *call, **named):
            owner = getattr(self, "owner", None)
            before = owner.timeline.now()
            text = describe(self, call)
            if text:
                log.append((before, owner.name, text))
            return original(self, *call, **named)
        setattr(cls, name, wrapped)

    wrap(protocol, "received_message", lambda self, a: f"received {a[1].msg_type.name} from {a[0]}")
    wrap(protocol, "start", lambda self, a: "generation protocol starts")
    wrap(protocol, "emit_event", lambda self, a: "memory emits photon")
    wrap(protocol, "_entanglement_succeed", lambda self, a: "herald: attempt succeeded")
    wrap(protocol, "_entanglement_fail", lambda self, a: "herald: attempt failed")
    wrap(protocol, "swap_two_memory", lambda self, a: "pair moved to request")
    wrap(ResourceManagerAdaptive, "received_message", lambda self, a: f"received pairing {a[1].msg_type.name} from {a[0]}"
         if a[1].msg_type.name in ("REQUEST", "RESPONSE") else "")
    wrap(ResourceReservationProtocolAdaptive, "pop", lambda self, a: f"received reservation {a[1].msg_type.name} from {a[0]}")
    wrap(AdaptiveContinuousProtocol, "request_compiler_pair", lambda self, a: "compiler launches preparation")

    original_statistics = request_scheduler.QubitOrderedRequestManager.get_statistics

    def capture(self, *call, **named):
        times.update(submitted=self.request_submission_times[0], window=self.request_generation_start_times[0],
                     completed=self.request_end_times[0])
        return original_statistics(self, *call, **named)
    request_scheduler.QubitOrderedRequestManager.get_statistics = capture

    rows = []
    with tempfile.TemporaryDirectory() as folder:
        trace = Path(folder) / "trace.txt"
        for source, destination in ((0, 1), (1, 0)):
            mini_trace(trace, source, destination, layer=3)
            for strategy, wanted in (("on-demand", 2), ("dynamic", None)):
                for seed in range(200):
                    log.clear()
                    sys.argv = ["x", "--trace", str(trace), "--config", str(kn.CONFIG), "--strategies", strategy, "--seeds", str(seed),
                                "--total-memories", "4", "--compiler-memories", "3", "--generation-capacity", "3",
                                "--planner-lead-layers", "2", "--scheduler", "per-qubit", "--admission", "event",
                                "--admission-priority", "ready-first", "--all-chain-hops", "--no-congestion-threshold",
                                "--pregeneration-buffer-ms", "0", "--stop-after-workload", "--compiler-reservation-ms", "50",
                                "--compiler-pair-consumption", "handoff", "--output", str(Path(folder) / "out")]
                    with contextlib.redirect_stdout(io.StringIO()):
                        cli.main()
                    failed = sum("attempt failed" in entry[2] for entry in log) // 2
                    if wanted is None or failed + 1 == wanted:
                        break
                zero = times["submitted"]
                for moment, node, text in sorted(log, key=lambda entry: entry[0]):
                    rows.append(dict(case=f"{strategy} {source}->{destination}", seed=seed, t_us=round((moment - zero) / 1e6, 3),
                                     node=node, event=text))
                rows.append(dict(case=f"{strategy} {source}->{destination}", seed=seed, t_us=round((times["window"] - zero) / 1e6, 3),
                                 node="manager", event="reservation window opens"))
                rows.append(dict(case=f"{strategy} {source}->{destination}", seed=seed, t_us=round((times["completed"] - zero) / 1e6, 3),
                                 node="manager", event="request completed"))
    rows.sort(key=lambda r: (r["case"], r["t_us"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
