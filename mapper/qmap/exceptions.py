
from __future__ import annotations

__all__ = [
    "ArchitectureError",
    "CircuitError",
    "ConfigurationError",
    "DependencyError",
    "InvalidPartitionError",
    "PlacementError",
    "QMapError",
    "UnplaceableOperationError",
]

class QMapError(Exception):
    pass

class ConfigurationError(QMapError):
    pass

class DependencyError(QMapError):
    pass

class ArchitectureError(QMapError):
    pass

class CircuitError(QMapError):
    pass

class PlacementError(QMapError):
    pass

class InvalidPartitionError(PlacementError):
    pass

class UnplaceableOperationError(PlacementError):
    pass
