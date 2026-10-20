"""
Real road routing using OSRM or similar providers.

This module provides road-network distance calculations as an alternative
to synthetic Euclidean distances. It preserves the existing distance matrix
abstraction so algorithms work unchanged.
"""

from .models import RoadRoutingConfig, RoadDistanceResult, RoadProvider
from .osrm import OSRMClient, get_osrm_table
from .adapter import create_road_distance_matrix

__all__ = [
    "RoadRoutingConfig",
    "RoadDistanceResult",
    "RoadProvider",
    "OSRMClient",
    "get_osrm_table",
    "create_road_distance_matrix",
]
