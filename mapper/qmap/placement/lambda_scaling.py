
from __future__ import annotations

from collections.abc import Callable

import numpy as np

from qmap.exceptions import ConfigurationError

__all__ = [
    "DEFAULT_LAMBDA_SCALING",
    "LAMBDA_SCALINGS",
    "LambdaScaling",
    "list_lambda_scalings",
    "register_lambda_scaling",
    "resolve_lambda",
]

LambdaScaling = Callable[[np.ndarray], float]
"""Maps a transfer-cost matrix to a scale factor for ``lambda``."""

DEFAULT_LAMBDA_SCALING = "fixed"

LAMBDA_SCALINGS: dict[str, LambdaScaling] = {}
"""Registry of scaling strategies. Extend via :func:`register_lambda_scaling`."""

def register_lambda_scaling(name: str) -> Callable[[LambdaScaling], LambdaScaling]:

    def decorator(strategy: LambdaScaling) -> LambdaScaling:
        key = name.lower()
        if key in LAMBDA_SCALINGS:
            raise ConfigurationError(f"lambda scaling {name!r} is already registered")
        LAMBDA_SCALINGS[key] = strategy
        return strategy

    return decorator

def _off_diagonal(transfer: np.ndarray) -> np.ndarray:
    n = transfer.shape[0]
    if n < 2:
        return np.empty(0, dtype=np.float64)
    return transfer[~np.eye(n, dtype=bool)]

@register_lambda_scaling("fixed")
def _fixed(transfer: np.ndarray) -> float:
    del transfer
    return 1.0

@register_lambda_scaling("mean")
def _mean(transfer: np.ndarray) -> float:
    values = _off_diagonal(transfer)
    return float(values.mean()) if values.size else 1.0

@register_lambda_scaling("median")
def _median(transfer: np.ndarray) -> float:
    values = _off_diagonal(transfer)
    return float(np.median(values)) if values.size else 1.0

@register_lambda_scaling("diameter")
def _diameter(transfer: np.ndarray) -> float:
    values = _off_diagonal(transfer)
    return float(values.max()) if values.size else 1.0

def list_lambda_scalings() -> list[str]:
    return sorted(LAMBDA_SCALINGS)

def resolve_lambda(
    strategy: str, base_weight: float, transfer: np.ndarray
) -> float:
    key = strategy.lower()
    if key not in LAMBDA_SCALINGS:
        raise ConfigurationError(
            f"unknown lambda scaling {strategy!r}; "
            f"available: {', '.join(list_lambda_scalings())}"
        )
    scale = LAMBDA_SCALINGS[key](transfer)
    if not np.isfinite(scale) or scale <= 0.0:
        raise ConfigurationError(
            f"lambda scaling {strategy!r} produced a non-positive or non-finite "
            f"scale ({scale}); look-ahead would become a repulsion"
        )
    return float(base_weight) * scale
