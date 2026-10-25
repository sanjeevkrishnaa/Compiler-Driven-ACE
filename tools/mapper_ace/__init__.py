"""Project-owned mapper-to-ACE trace boundary.

The vendored :mod:`qmap` package produces placements.  This package turns
those placements into an auditable migration trace, selects a physical route,
and only then emits ACE's legacy adjacent-hop request format.
"""

from .adapter import (
    MigrationRecord,
    build_migration_records,
    validate_migration_records,
    write_adjacent_requests,
    write_migration_trace,
)
from .routing import route_path

__all__ = [
    "MigrationRecord",
    "build_migration_records",
    "validate_migration_records",
    "write_adjacent_requests",
    "write_migration_trace",
    "route_path",
]
