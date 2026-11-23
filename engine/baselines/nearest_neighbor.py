"""
Nearest Neighbor construction heuristic for delivery routing.

Greedy algorithm: repeatedly visit the nearest unvisited stop.
"""

import numpy as np
from typing import List
from pydantic import BaseModel, Field


class RouteResult(BaseModel):
    """
    Result of a routing algorithm.
    
    Attributes:
        route: Sequence of stop indices [0, ..., 0] (depot start/end)
        total_distance: Total route distance
        algorithm: Name of algorithm used
    """
    route: List[int] = Field(..., description="Stop indices in visit order")
    total_distance: float = Field(..., ge=0, description="Total route distance")
    algorithm: str = Field(..., description="Algorithm name")
    
    def __repr__(self) -> str:
        return (
            f"RouteResult(algorithm='{self.algorithm}', "
            f"distance={self.total_distance:.2f}, "
            f"stops={len(self.route)})"
        )


def nearest_neighbor(distance_matrix: np.ndarray, *, checkpoint=None) -> RouteResult:
    """
    Construct a route using the Nearest Neighbor heuristic.
    
    Algorithm:
    1. Start at depot (index 0)
    2. Repeatedly visit the nearest unvisited stop
    3. Return to depot after all stops visited
    
    Tie-Breaking:
    If multiple stops have the same distance, select the one with
    the lowest index (deterministic).
    
    Args:
        distance_matrix: NxN symmetric distance matrix
                        Index 0 = depot, 1..N-1 = stops
        checkpoint: Optional host callback before each distance comparison.
                    It may raise to abandon an incomplete construction.
        
    Returns:
        RouteResult containing route and total distance
        
    Raises:
        ValueError: If distance_matrix is invalid
        
    Example:
        >>> # 3 locations: depot, stop1, stop2
        >>> distances = np.array([
        ...     [0, 10, 20],
        ...     [10, 0, 5],
        ...     [20, 5, 0]
        ... ])
        >>> result = nearest_neighbor(distances)
        >>> result.route
        [0, 1, 2, 0]
    """
    if distance_matrix.size == 0:
        raise ValueError("Distance matrix must contain at least the depot")
    
    if distance_matrix.shape[0] != distance_matrix.shape[1]:
        raise ValueError("Distance matrix must be square")
    
    n = distance_matrix.shape[0]
    
    # Check for negative distances
    if np.any(distance_matrix < 0):
        raise ValueError("Distance matrix cannot contain negative distances")
    
    # Special case: only depot (no delivery stops)
    if n == 1:
        from engine.instances import calculate_route_cost
        route = [0, 0]
        cost = calculate_route_cost(route, distance_matrix, return_to_depot=False)
        return RouteResult(
            route=route,
            total_distance=cost,
            algorithm="Nearest Neighbor"
        )
    
    # Initialize
    current = 0  # Start at depot
    unvisited = set(range(1, n))  # All delivery stops
    route = [0]  # Route starts at depot
    
    # Greedy construction: visit nearest unvisited stop
    while unvisited:
        # Find nearest unvisited stop
        nearest_stop = None
        nearest_distance = float('inf')
        
        for stop in unvisited:
            if checkpoint is not None:
                checkpoint()
            dist = distance_matrix[current, stop]
            # Deterministic tie-breaking: prefer lower index
            if dist < nearest_distance or (dist == nearest_distance and stop < nearest_stop):
                nearest_stop = stop
                nearest_distance = dist
        
        # Visit nearest stop
        route.append(nearest_stop)
        unvisited.remove(nearest_stop)
        current = nearest_stop
    
    # Return to depot
    route.append(0)
    
    # Calculate total distance using shared function
    from engine.instances import calculate_route_cost
    total_distance = calculate_route_cost(
        route,
        distance_matrix,
        return_to_depot=False  # Already added depot to route
    )
    
    return RouteResult(
        route=route,
        total_distance=total_distance,
        algorithm="Nearest Neighbor"
    )
