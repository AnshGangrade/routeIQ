"""
Instance generation and distance calculations for RouteIQ.

This module provides:
- Synthetic delivery instance generation with configurable seeds
- Euclidean distance calculations
- Distance matrix computation
- Route cost calculation
"""

from .generator import InstanceGenerator
from .models import DeliveryInstance, Stop, Point
from .distance import (
    euclidean_distance,
    compute_distance_matrix,
    calculate_route_cost,
)

__all__ = [
    "InstanceGenerator",
    "DeliveryInstance",
    "Stop",
    "Point",
    "euclidean_distance",
    "compute_distance_matrix",
    "calculate_route_cost",
]
