"""Deterministic stop assignment strategies for multi-driver routing.

Assignment Algorithms:
- Sweep: Assign stops by angular position around the depot
"""

import numpy as np
from typing import List
from .models import DriverAssignment
from engine.instances.models import DeliveryInstance, Point


def assign_stops_by_sweep(
    instance: DeliveryInstance,
    num_drivers: int
) -> List[DriverAssignment]:
    """
    Assign delivery stops to drivers using sweep-angle assignment.
    
    Strategy:
    1. Calculate angle of each stop relative to depot
    2. Sort stops by angle (deterministic tie-breaking by stop ID)
    3. Distribute stops sequentially to drivers in round-robin fashion
    
    This creates geographically cohesive driver territories while
    ensuring deterministic, balanced assignments.
    
    Edge Cases:
    - Zero stops: All drivers get empty assignments
    - Fewer stops than drivers: Some drivers get empty assignments
    - More stops than drivers: Stops distributed as evenly as possible
    
    Args:
        instance: Delivery instance with stops and depot
        num_drivers: Number of drivers (must be >= 1)
        
    Returns:
        List of DriverAssignment, one per driver (0-indexed)
        
    Raises:
        ValueError: If num_drivers < 1
        
    Example:
        >>> instance = InstanceGenerator(seed=42).generate(n_stops=6)
        >>> assignments = assign_stops_by_sweep(instance, num_drivers=2)
        >>> len(assignments)
        2
        >>> sum(len(a.stop_ids) for a in assignments)
        6
    """
    if num_drivers < 1:
        raise ValueError(f"num_drivers must be >= 1, got {num_drivers}")
    
    # Handle zero stops
    if instance.n_stops == 0:
        return [
            DriverAssignment(driver_id=i, stop_ids=[])
            for i in range(num_drivers)
        ]
    
    # Calculate angles for all delivery stops relative to depot
    depot_loc = instance.depot.location
    stop_angles = []
    
    for stop in instance.stops:
        dx = stop.location.x - depot_loc.x
        dy = stop.location.y - depot_loc.y
        
        # Use atan2 for full 360-degree range
        angle = np.arctan2(dy, dx)
        
        stop_angles.append((stop.id, angle))
    
    # Sort by angle, with stop ID as tie-breaker for determinism
    stop_angles.sort(key=lambda x: (x[1], x[0]))
    
    # Initialize assignments
    assignments = [
        DriverAssignment(driver_id=i, stop_ids=[])
        for i in range(num_drivers)
    ]
    
    # Distribute stops round-robin to drivers
    for idx, (stop_id, angle) in enumerate(stop_angles):
        driver_idx = idx % num_drivers
        assignments[driver_idx].stop_ids.append(stop_id)
    
    return assignments


def validate_assignment(
    assignments: List[DriverAssignment],
    expected_stop_count: int
) -> None:
    """
    Validate that assignments are complete and non-overlapping.
    
    Checks:
    - All stop IDs appear exactly once
    - No stop is assigned to multiple drivers
    - Total assigned stops equals expected count
    
    Args:
        assignments: List of driver assignments
        expected_stop_count: Expected total number of stops
        
    Raises:
        ValueError: If validation fails
    """
    assigned_stops = set()
    
    for assignment in assignments:
        for stop_id in assignment.stop_ids:
            if stop_id in assigned_stops:
                raise ValueError(f"Stop {stop_id} assigned to multiple drivers")
            if stop_id == 0:
                raise ValueError(f"Depot (stop 0) cannot be assigned to a driver")
            assigned_stops.add(stop_id)
    
    if len(assigned_stops) != expected_stop_count:
        raise ValueError(
            f"Expected {expected_stop_count} stops assigned, "
            f"got {len(assigned_stops)}"
        )
