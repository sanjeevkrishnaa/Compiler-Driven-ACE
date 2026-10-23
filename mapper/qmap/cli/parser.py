
from __future__ import annotations

import argparse

from qmap import __version__
from qmap.architecture.topology import canonical_topology, list_topologies
from qmap.placement.initial import list_initial_placements
from qmap.placement.lambda_scaling import list_lambda_scalings
from qmap.placement.registry import DEFAULT_PLACERS, list_placers

__all__ = ["build_parser"]

_EPILOG = """\
examples:
  qmap run --grid 4x4 --benchmark qft
  qmap run --grid 8x8 --qasm circuits/qft/128.qasm --placers TR-HQA,HQA
  qmap scaling --grids 2x2,4x4,8x4,8x8 --benchmarks qft,cuccaro --repeats 3 --plot
  qmap reliability --repeats 10 --plot --output results/reliability
  qmap ablation --grid 4x4 --qubits-per-core 16 --plot
  qmap run --grid 4x4 --benchmark qft --trace results/trace.jsonl
  qmap run --grid 4x4 --benchmark qft --measure-time
  qmap list placers
"""

def _add_architecture_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("architecture")
    group.add_argument(
        "--qubits-per-core",
        type=int,
        default=8,
        metavar="N",
        help="physical qubits per core, held fixed under strong scaling (default: 8)",
    )
    group.add_argument(
        "--reserved-ancilla",
        type=int,
        default=2,
        metavar="N",
        help=(
            "ancillae reserved per core as teleportation headroom; the workload "
            "share is qubits-per-core minus this (default: 2)"
        ),
    )
    group.add_argument(
        "--topology",
        default="mesh",
        type=canonical_topology,
        choices=list_topologies(),
        help=(
            "inter-core interconnect topology. mesh and torus read --grid as RxC; "
            "line, tree, and ata (all-to-all) have no intrinsic shape and read "
            "it as a core total, so "
            "'8x8' and '64' name the same 64-core line (default: mesh)"
        ),
    )
    group.add_argument(
        "--reliability-min",
        type=float,
        default=0.4,
        metavar="P",
        help=(
            "lower bound of the per-link reliability draw p(e) ~ U[min, 1]; "
            "1.0 gives a perfectly reliable interconnect (default: 0.4)"
        ),
    )

def _add_placement_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("placement")
    group.add_argument(
        "--placers",
        default=",".join(DEFAULT_PLACERS),
        metavar="LIST",
        help=(
            "comma-separated algorithms to compare, all seeing the identical "
            f"architecture, circuit and initial placement (default: "
            f"{','.join(DEFAULT_PLACERS)}; available: {','.join(list_placers())})"
        ),
    )
    group.add_argument(
        "--initial-placement",
        default="sequential",
        choices=list_initial_placements(),
        help=(
            "strategy for pi_0, identical across the compared algorithms "
            "(default: sequential)"
        ),
    )
    group.add_argument(
        "--lookahead",
        type=int,
        default=8,
        metavar="N",
        help="look-ahead window in timeslices; 0 disables it (default: 8)",
    )
    group.add_argument(
        "--lookahead-weight",
        type=float,
        default=1.0,
        metavar="W",
        help=(
            "weight lambda on the look-ahead attraction term. The default is "
            "lambda=1; because the transfer cost d/rho is unbounded while "
            "attraction is bounded by 1, larger architectures need a larger "
            "lambda for look-ahead to remain influential (default: 1.0)"
        ),
    )
    group.add_argument(
        "--lambda-scaling",
        default="fixed",
        choices=list_lambda_scalings(),
        help=(
            "how lambda is scaled to the architecture. 'fixed' uses "
            "--lookahead-weight verbatim. The other strategies "
            "multiply it by the mean, median or maximum transfer cost, keeping "
            "look-ahead influential as the interconnect grows, since d/rho is "
            "unbounded while the attraction term is bounded by 1 (default: fixed)"
        ),
    )
    group.add_argument(
        "--cost-normalization",
        default="none",
        choices=["none", "minmax"],
        help=(
            "subtract each row's feasible minimum from C_base before subtracting "
            "the look-ahead term. 'none' uses the published unshifted cost; "
            "'minmax' is retained as the legacy option name (default: none)"
        ),
    )
    group.add_argument(
        "--no-eviction",
        action="store_true",
        help=(
            "disable the eviction pass that frees capacity for otherwise "
            "unplaceable gates; leaves such gates unplaced and counted as residuals"
        ),
    )

def _add_output_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("output")
    group.add_argument(
        "--output",
        metavar="DIR",
        help="directory for results; defaults to results/<command>",
    )
    group.add_argument(
        "--stem",
        metavar="NAME",
        help="filename stem for the result files (default: the command name)",
    )
    group.add_argument(
        "--plot",
        action="store_true",
        help="render the corresponding study figures (requires matplotlib)",
    )
    group.add_argument(
        "--seed",
        type=int,
        default=20260101,
        metavar="N",
        help=(
            "root seed. Every random quantity derives from it by a labelled path, "
            "so a run is bit-for-bit reproducible (default: 20260101)"
        ),
    )
    group.add_argument(
        "--no-write",
        action="store_true",
        help="print results to stdout without writing files",
    )
    group.add_argument(
        "--hop-count",
        action="store_true",
        help=(
            "include the total gate-routing hop count for each mapper in the console "
            "report and saved result files"
        ),
    )

def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    _add_architecture_arguments(parser)
    _add_placement_arguments(parser)
    _add_output_arguments(parser)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qmap",
        description=(
            "Topology and reliability aware qubit mapping for multi-core quantum "
            "architectures. Includes scaling, reliability, and ablation studies."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"qmap {__version__}")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase logging verbosity; repeat for debug output",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="suppress progress logging",
    )

    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = subparsers.add_parser(
        "run",
        help="map one circuit on one architecture",
        description=(
            "Map a single circuit and report its cost. The circuit is either "
            "synthesised (--benchmark) or loaded from QASM (--qasm)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    circuit_group = run.add_argument_group("circuit")
    source = circuit_group.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--benchmark",
        help="synthesise a benchmark: qft, cuccaro, draper or random",
    )
    source.add_argument(
        "--qasm",
        metavar="PATH",
        help="load an OpenQASM 2.0 circuit from a file",
    )
    circuit_group.add_argument(
        "--grid",
        default="4x4",
        metavar="RxC",
        help="architecture size; a core total for line and tree",
    )
    circuit_group.add_argument(
        "--width",
        type=int,
        metavar="N",
        help=(
            "circuit width for synthesised benchmarks; defaults to the "
            "architecture's workload width"
        ),
    )
    circuit_group.add_argument(
        "--depth",
        type=int,
        metavar="N",
        help="pre-transpilation gate count for --benchmark random (default: 2 x width)",
    )
    circuit_group.add_argument(
        "--two-qubit-prob",
        type=float,
        default=0.5,
        metavar="P",
        help="probability a random-circuit gate is two-qubit",
    )
    circuit_group.add_argument(
        "--trace",
        metavar="PATH",
        help=(
            "write the induced inter-core communication trace as JSON Lines "
            "(Section 6.4), the synthetic workload a routing study consumes"
        ),
    )
    _add_common_arguments(run)
    timing = run.add_argument_group("mapper timing")
    timing.add_argument(
        "--measure-time",
        action="store_true",
        help=(
            "measure mapper execution time in isolated pyperf worker processes. "
            "Always compares HQA, TR-HQA and GTR-QA; excludes circuit/architecture "
            "setup, validation, evaluation and output I/O"
        ),
    )
    timing.add_argument(
        "--timing-processes",
        type=int,
        default=10,
        metavar="N",
        help="isolated worker processes per mapper when --measure-time is enabled",
    )
    timing.add_argument(
        "--timing-values",
        type=int,
        default=3,
        metavar="N",
        help="timed values collected from each timing worker process",
    )
    timing.add_argument(
        "--timing-warmups",
        type=int,
        default=1,
        metavar="N",
        help="unreported warm-up values per timing worker process",
    )
    timing.add_argument(
        "--timing-min-time",
        type=float,
        default=0.1,
        metavar="SECONDS",
        help="minimum duration of one calibrated timing value",
    )

    scaling = subparsers.add_parser(
        "scaling",
        help="strong-scaling study (Sections 6.1, 6.2)",
        description=(
            "Hold qubits-per-core fixed and grow the core count, measuring "
            "communication cost (Table 1) and mapping runtime (Figures 4, 5). "
            "Circuit width tracks the architecture."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    scaling.add_argument(
        "--grids",
        default="2x2,4x4,8x4,8x8",
        metavar="LIST",
        help=(
            "comma-separated architecture sizes; defaults are 2x2,4x4,8x4,8x8, "
            "which give 4, 16, 32 and 64 cores on every topology"
        ),
    )
    scaling.add_argument(
        "--benchmarks",
        default="qft,cuccaro,draper,random",
        metavar="LIST",
        help="comma-separated benchmark families",
    )
    scaling.add_argument(
        "--repeats",
        type=int,
        default=3,
        metavar="N",
        help="independent architecture realisations per configuration",
    )
    _add_common_arguments(scaling)

    reliability = subparsers.add_parser(
        "reliability",
        help="link-reliability study (Section 6.3)",
        description=(
            "Fix the architecture and sweep entanglement link reliability over "
            "bands spanning [0.1, 1.0], averaging over repeats (Figure 6)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    reliability.add_argument(
        "--grid", default="4x4", metavar="RxC", help="fixed architecture size"
    )
    reliability.add_argument(
        "--benchmark", default="qft", help="circuit family"
    )
    reliability.add_argument(
        "--width", type=int, metavar="N", help="circuit width (default: workload width)"
    )
    reliability.add_argument(
        "--bands",
        default="0.1-0.325,0.325-0.55,0.55-0.775,0.775-1.0",
        metavar="LIST",
        help=(
            "comma-separated reliability bands as MIN-MAX; the default divides "
            "the 0.1-1.0 range into four equal-width bands"
        ),
    )
    reliability.add_argument(
        "--repeats",
        type=int,
        default=10,
        metavar="N",
        help="independent draws per band",
    )
    _add_common_arguments(reliability)

    ablation = subparsers.add_parser(
        "ablation",
        help="ablation against an idealised control (Section 6.4)",
        description=(
            "Compare TR-HQA against T-HQA, which prices distance but assumes "
            "perfectly reliable links, plus HQA and the no-look-ahead variant so "
            "topology awareness and look-ahead are ablated independently (Figure 7)."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ablation.add_argument(
        "--grid", default="4x4", metavar="RxC", help="fixed architecture size"
    )
    ablation.add_argument("--benchmark", default="qft", help="circuit family")
    ablation.add_argument(
        "--width", type=int, metavar="N", help="circuit width (default: workload width)"
    )
    ablation.add_argument(
        "--bands",
        default="0.1-0.325,0.325-0.55,0.55-0.775,0.775-1.0",
        metavar="LIST",
        help="comma-separated reliability bands as MIN-MAX",
    )
    ablation.add_argument(
        "--repeats", type=int, default=10, metavar="N", help="draws per band"
    )
    _add_common_arguments(ablation)

    listing = subparsers.add_parser(
        "list",
        help="list registered algorithms, benchmarks, topologies or placements",
    )
    listing.add_argument(
        "registry",
        choices=("placers", "benchmarks", "topologies", "initial-placements", "all"),
        default="all",
        nargs="?",
        help="which registry to print",
    )

    describe = subparsers.add_parser(
        "describe",
        help="print an architecture's resolved properties without running anything",
    )
    describe.add_argument(
        "--grid",
        default="4x4",
        metavar="RxC",
        help="architecture size; a core total for line and tree",
    )
    _add_architecture_arguments(describe)
    describe.add_argument(
        "--seed", type=int, default=20260101, metavar="N", help="root seed"
    )

    return parser
