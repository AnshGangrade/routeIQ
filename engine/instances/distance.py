"""
Distance calculations for routing instances.

All distances use Euclidean (straight-line) metric.
No road network or travel time considerations.
"""

import numpy as np
from typing import List, Sequence
from .models import Point


def euclidean_distance(p1: Point, p2: Point) -> float:
    """
    Calculate Euclidean distance between two points.
    
    Formula: sqrt((x2-x1)^2 + (y2-y1)^2)
    
    Args:
        p1: First point
        p2: Second point
        
    Returns:
        Euclidean distance as a non-negative float
        
    Example:
        >>> p1 = Point(x=0, y=0)
        >>> p2 = Point(x=3, y=4)
        >>> euclidean_distance(p1, p2)
        5.0
    """
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    return np.sqrt(dx * dx + dy * dy)


def compute_distance_matrix(locations: List[Point]) -> np.ndarray:
    """
    Compute symmetric distance matrix for all locations.
    
    The matrix is indexed consistently with the instance:
    - Row/Column 0: Depot
    - Row/Column i (i>0): Stop i
    
    Args:
        locations: List of Point objects [depot, stop1, stop2, ...]
        
    Returns:
        NxN symmetric distance matrix where N = len(locations)
        - matrix[i][j] = Euclidean distance from location i to j
        - Diagonal is all zeros
        - matrix[i][j] == matrix[j][i] (symmetric)
        
    Raises:
        ValueError: If locations list is empty
        
    Example:
        >>> depot = Point(x=0, y=0)
        >>> stop1 = Point(x=3, y=4)
        >>> matrix = compute_distance_matrix([depot, stop1])
        >>> matrix[0, 1]  # Distance from depot to stop1
        5.0
        >>> matrix[0, 0]  # Distance from depot to itself
        0.0
    """
    if not locations:
        raise ValueError("Cannot compute distance matrix for empty locations list")
    
    n = len(locations)
    matrix = np.zeros((n, n), dtype=float)
    
    # Compute upper triangle (symmetric, so we only compute once)
    for i in range(n):
        for j in range(i + 1, n):
            dist = euclidean_distance(locations[i], locations[j])
            matrix[i, j] = dist
            matrix[j, i] = dist  # Symmetric
    
    return matrix


def calculate_route_cost(
    route: Sequence[int],
    distance_matrix: np.ndarray,
    return_to_depot: bool = True
) -> float:
    """
    Calculate total distance of a route through stops.
    
    Route Convention:
    - Route is a sequence of stop indices
    - Index 0 = depot, 1..N = delivery stops
    - Route typically starts and ends at depot: [0, 3, 1, 2, 0]
    
    Args:
        route: Sequence of stop indices defining the path
        distance_matrix: Precomputed distance matrix
        return_to_depot: If True and route doesn't end at depot (0),
                        automatically add return leg to depot
        
    Returns:
        Total distance traveled along the route
        
    Raises:
        ValueError: If route is too short, contains invalid indices,
                   or indices are out of bounds for distance_matrix
        
    Example:
        >>> # Route: depot -> stop1 -> stop2 -> depot
        >>> route = [0, 1, 2, 0]
        >>> cost = calculate_route_cost(route, distance_matrix)
    """
    if len(route) < 1:
        raise ValueError("Route must contain at least one stop")
    
    n = distance_matrix.shape[0]
    
    # Validate all indices
    for idx in route:
        if not isinstance(idx, (int, np.integer)):
            raise ValueError(f"Route indices must be integers, got {type(idx)}")
        if idx < 0 or idx >= n:
            raise ValueError(
                f"Route index {idx} out of bounds. "
                f"Distance matrix size: {n}"
            )
    
    # Calculate cumulative distance
    total_distance = 0.0
    
    for i in range(len(route) - 1):
        from_idx = route[i]
        to_idx = route[i + 1]
        total_distance += distance_matrix[from_idx, to_idx]
    
    # Add return to depot if needed
    if return_to_depot and len(route) > 0 and route[-1] != 0:
        total_distance += distance_matrix[route[-1], 0]
    
    return float(total_distance)


def validate_route(
    route: Sequence[int],
    n_stops: int,
    require_depot_start: bool = True,
    require_depot_end: bool = True,
    require_all_stops: bool = True
) -> None:
    """
    Validate that a route meets structural requirements.
    
    This does NOT calculate distance, only checks route validity.
    
    Args:
        route: Sequence of stop indices
        n_stops: Number of delivery stops (excluding depot)
        require_depot_start: Route must start at depot (index 0)
        require_depot_end: Route must end at depot (index 0)
        require_all_stops: Route must visit all stops exactly once
        
    Raises:
        ValueError: If route violates any required condition
        
    Example:
        >>> validate_route([0, 1, 2, 0], n_stops=2)  # Valid
        >>> validate_route([1, 2, 0], n_stops=2, require_depot_start=True)  
        ValueError: Route must start at depot
    """
    if not route:
        raise ValueError("Route cannot be empty")
    
    if require_depot_start and route[0] != 0:
        raise ValueError(f"Route must start at depot (0), got {route[0]}")
    
    if require_depot_end and route[-1] != 0:
        raise ValueError(f"Route must end at depot (0), got {route[-1]}")
    
    if require_all_stops:
        # Extract non-depot stops (exclude depot occurrences)
        visited_stops = [idx for idx in route if idx != 0]
        expected_stops = set(range(1, n_stops + 1))
        actual_stops = set(visited_stops)
        
        # Check all stops visited
        missing = expected_stops - actual_stops
        if missing:
            raise ValueError(f"Route missing stops: {sorted(missing)}")
        
        # Check no duplicates
        if len(visited_stops) != len(actual_stops):
            raise ValueError("Route contains duplicate stop visits")
