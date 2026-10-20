"""Multi-driver routing layer.

This module handles:
- Deterministic stop assignment to drivers
- Per-driver route optimization
- Fleet-level metrics and aggregation
"""

from .models import DriverAssignment, DriverRoute, FleetResult
from .assignment import assign_stops_by_sweep
from .fleet import FleetRouter

__all__ = [
    "DriverAssignment",
    "DriverRoute",
    "FleetResult",
    "assign_stops_by_sweep",
    "FleetRouter",
]
