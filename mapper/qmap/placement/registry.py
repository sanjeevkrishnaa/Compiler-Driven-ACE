
from __future__ import annotations

from qmap.exceptions import ConfigurationError
from qmap.placement.base import Placer, PlacerConfig
from qmap.placement.GTR_QA import GTRQAPlacer
from qmap.placement.HQA import HQANoLookaheadPlacer, HQAPlacer
from qmap.placement.T_HQA import THQAPlacer
from qmap.placement.T_HQAR import THQARPlacer
from qmap.placement.TR_HQA import TRHQAPlacer

__all__ = [
    "DEFAULT_PLACERS",
    "PLACERS",
    "build_placer",
    "describe_placers",
    "list_placers",
    "resolve_placer",
]

PLACERS: dict[str, type[Placer]] = {
    placer.name: placer
    for placer in (
        HQAPlacer,
        HQANoLookaheadPlacer,
        THQAPlacer,
        THQARPlacer,
        TRHQAPlacer,
        GTRQAPlacer,
    )
}

DEFAULT_PLACERS: tuple[str, ...] = ("HQA", "T-HQA", "TR-HQA", "GTR-QA")

def _normalise(name: str) -> str:
    return name.strip().lower().replace("-", "").replace("_", "")

_LOOKUP = {_normalise(key): key for key in PLACERS}

def list_placers() -> list[str]:
    return list(PLACERS)

def describe_placers() -> dict[str, str]:
    return {name: placer.description for name, placer in PLACERS.items()}

def resolve_placer(name: str) -> type[Placer]:
    key = _LOOKUP.get(_normalise(name))
    if key is None:
        raise ConfigurationError(
            f"unknown placer {name!r}; available: {', '.join(list_placers())}"
        )
    return PLACERS[key]

def build_placer(name: str, config: PlacerConfig | None = None) -> Placer:
    return resolve_placer(name)(config)
