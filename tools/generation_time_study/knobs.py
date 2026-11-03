"""The knobs of the EPR generation-time study, and how each one reaches the simulator.

Nothing under ace/ is edited.  A knob is either a value in a *copy* of the JSON configuration, or
one of two module constants replaced in the current process before the simulation is built:

* ``classical_scale`` multiplies the 100 us + 20 us/hop classical-delay model.  That formula is a
  nested function in ace/topology/router_net_topo_adaptive.py and reads the module global
  MICROSECOND, which is used nowhere else in that module (see tests).  distance/c is not scaled.
* ``empty_gap_ms`` replaces EMPTY_LAYER_GAP_MS in ace/simulation/request_scheduler.py, the time
  charged for a layer with no inter-core request.
* ``request_retry_ms`` replaces RETRY_PERIOD in the same file, the wait before a request that the
  protocol refused is submitted again; ``compiler_retry_ms`` is the wait before a refused
  preparation is launched again, which the controller hard-codes as one millisecond (see
  patch_runtime for the exact replacement).

Default knobs change nothing: apply_config(config, Knobs()) returns an equal configuration.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, fields, replace
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
# Frozen copy: this study was run at memory efficiency 0.95, before the project default moved to 0.8.
CONFIG = ROOT / "results" / "generation_time_2026-11-01" / "config_grid_4x4_efficiency095.json"
TEMPLATE = "adaptive_protocol"
LINK_METRES = 0.025     # router to BSM, the qchannel distance of the default configuration


def engine_path() -> Path:
    """The pinned SeQUeNCe checkout: $SEQUENCE_ENGINE, else the third_party submodule."""
    configured = os.environ.get("SEQUENCE_ENGINE")
    path = Path(configured) if configured else ROOT / "third_party" / "SeQUeNCe"
    if not (path / "sequence" / "__init__.py").is_file():
        raise SystemExit(f"SeQUeNCe not found at {path}; set SEQUENCE_ENGINE or initialise the submodule")
    return path


def add_paths() -> None:
    for path in (str(ROOT), str(engine_path())):
        if path not in sys.path:
            sys.path.insert(0, path)


@dataclass(frozen=True)
class Knobs:
    classical_scale: float = 1.0
    empty_gap_ms: float = 5.0
    memory_efficiency: float = 0.95
    detector_efficiency: float = 0.95
    bsm_success_rate: float = 0.5
    distance_scale: float = 1.0
    attenuation_db_per_m: float = 0.0002
    memory_frequency_hz: float = 80e6
    coherence_time_s: float = 1.0
    raw_fidelity: float = 0.95
    dark_count_per_s: float = 0.0
    gate_fidelity: float = 0.99
    measurement_fidelity: float = 0.99
    request_retry_ms: float = 1.0
    compiler_retry_ms: float = 1.0

    def overrides(self) -> dict:
        """Only the knobs that differ from the default, for labels and file names."""
        base = Knobs()
        return {f.name: getattr(self, f.name) for f in fields(self)
                if getattr(self, f.name) != getattr(base, f.name)}

    def key(self) -> str:
        items = self.overrides()
        return "base" if not items else ",".join(f"{k}={v:g}" for k, v in sorted(items.items()))

    def as_dict(self) -> dict:
        return asdict(self)

    def with_(self, **changes) -> "Knobs":
        return replace(self, **changes)


def apply_config(config: dict, knobs: Knobs) -> dict:
    """A copy of the configuration with the JSON-level knobs set.  Defaults leave it unchanged."""
    out = copy.deepcopy(config)
    template = out["templates"][TEMPLATE]
    memory = template["MemoryArray"]
    bsm = template["SingleHeraldedBSM"]
    default = Knobs()
    if knobs.memory_efficiency != default.memory_efficiency:
        memory["efficiency"] = knobs.memory_efficiency
    if knobs.coherence_time_s != default.coherence_time_s:
        memory["coherence_time"] = knobs.coherence_time_s
    if knobs.raw_fidelity != default.raw_fidelity:
        memory["fidelity"] = knobs.raw_fidelity
    if knobs.memory_frequency_hz != default.memory_frequency_hz:
        memory["frequency"] = knobs.memory_frequency_hz
    if knobs.bsm_success_rate != default.bsm_success_rate:
        bsm["success_rate"] = knobs.bsm_success_rate
    for detector in bsm["detectors"]:
        if knobs.detector_efficiency != default.detector_efficiency:
            detector["efficiency"] = knobs.detector_efficiency
        if knobs.dark_count_per_s != default.dark_count_per_s:
            detector["dark_count"] = knobs.dark_count_per_s
    if knobs.distance_scale != default.distance_scale:
        for name in ("qchannels", "cchannels"):
            for channel in out[name]:
                channel["distance"] *= knobs.distance_scale
    if knobs.attenuation_db_per_m != default.attenuation_db_per_m:
        for channel in out["qchannels"]:
            channel["attenuation"] = knobs.attenuation_db_per_m
    for node in out["nodes"]:
        if node["type"] != "QuantumRouter":
            continue
        if knobs.gate_fidelity != default.gate_fidelity:
            node["gate_fidelity"] = knobs.gate_fidelity
        if knobs.measurement_fidelity != default.measurement_fidelity:
            node["measurement_fidelity"] = knobs.measurement_fidelity
    return out


def write_config(path: Path, knobs: Knobs) -> Path:
    config = json.loads(CONFIG.read_text())
    path.write_text(json.dumps(apply_config(config, knobs)))
    return path


def patch_runtime(knobs: Knobs) -> None:
    """Set the two in-process constants.  Call once, before the simulation is built."""
    add_paths()
    from sequence.constants import MICROSECOND
    import ace.simulation.request_scheduler as scheduler
    import ace.topology.router_net_topo_adaptive as topology
    topology.MICROSECOND = MICROSECOND * knobs.classical_scale
    scheduler.EMPTY_LAYER_GAP_MS = knobs.empty_gap_ms
    from sequence.constants import MILLISECOND
    scheduler.RETRY_PERIOD = int(knobs.request_retry_ms * MILLISECOND)
    if knobs.compiler_retry_ms != Knobs().compiler_retry_ms:
        from sequence.kernel.event import Event
        from sequence.kernel.process import Process
        from ace.compiler.compiler_scheduler import CompilerPreGenerationController as Controller
        period = int(knobs.compiler_retry_ms * MILLISECOND)

        def on_preparation_rejected(self, request_id: int, reason: str) -> None:
            """Same as the controller's method, with the retry wait taken from the knob."""
            self.rejections[request_id].append(reason)
            if (request_id not in self.deadlines and request_id not in self.accepted
                    and request_id not in self.preparation_retry_events):
                event = Event(self.timeline.now() + period, Process(self, "retry_preparation", [request_id]))
                self.preparation_retry_events[request_id] = event
                self.timeline.schedule(event)
        Controller.on_preparation_rejected = on_preparation_rejected


def success_probability(knobs: Knobs) -> float:
    """Per-attempt success read from the engine: BSM rate x (memory x detector x fibre)^2.

    SingleHeraldedBSM.get needs both photons to survive (memory emission and fibre, one draw each),
    the linear-optics rate once, and then both detectors to fire.
    """
    fibre = 10 ** (-(LINK_METRES * knobs.distance_scale * knobs.attenuation_db_per_m) / 10)
    return knobs.bsm_success_rate * (knobs.memory_efficiency * knobs.detector_efficiency * fibre) ** 2


def attempt_messages(source_core: int, destination_core: int) -> int:
    """Classical messages per attempt on a hop, in units of the delay.

    The protocol is paired by the request's source, so the destination starts after one delay and
    the source after two.  NEGOTIATE is sent by the primary, the node with the greater name, which
    for these names is the greater core number.  If the primary is the destination it starts first
    and an attempt takes 4 delays; if it is the source it starts second and an attempt takes 5.
    """
    return 5 if source_core > destination_core else 4


def hit_messages(source_core: int, destination_core: int) -> int:
    """Delays from window start to delivery on a cache hit: the primary's start plus INFORM_EP."""
    return 3 if source_core > destination_core else 2
