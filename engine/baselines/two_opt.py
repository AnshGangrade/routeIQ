"""
2-Opt local search improvement for delivery routing.

Iteratively improves a route by reversing segments that reduce total distance.
"""

import numpy as np
from typing import List
from .nearest_neighbor import RouteResult


def two_opt(
    initial_route: List[int],
    distance_matrix: np.ndarray,
    max_iterations: int = 1000,
    *, should_continue=None
) -> RouteResult:
    """
    Improve a route using 2-Opt local search.
    
    Algorithm:
    1. Start with an initial valid route
    2. Try all pairs of edges (i, i+1) and (j, j+1) where i < j
    3. If reversing the segment [i+1...j] reduces distance, apply it
    4. Repeat until no improvement found or max_iterations reached
    
    The 2-Opt move reverses a segment of the route:
        Before: [..., A, B, ..., C, D, ...]
        After:  [..., A, C, ..., B, D, ...]
    (segment B...C is reversed)
    
    Preserves:
    - Depot start/end (indices 0 and -1 are always depot)
    - All stops visited exactly once
    - Route validity
    
    Args:
        initial_route: Valid route [0, ..., 0] (depot start/end)
        distance_matrix: NxN distance matrix (symmetric or directed)
        max_iterations: Maximum improvement iterations (default 1000)
        should_continue: Optional host callback before each reversal evaluation.
                         False returns the best route already found.
        
    Returns:
        RouteResult with improved route and distance
        
    Raises:
        ValueError: If initial_route is invalid
        
    Example:
        >>> # Start with NN route
        >>> nn_result = nearest_neighbor(distances)
        >>> # Improve with 2-Opt
        >>> improved = two_opt(nn_result.route, distances)
        >>> assert improved.total_distance <= nn_result.total_distance
    """
    if not initial_route:
        raise ValueError("Initial route cannot be empty")
    
    if initial_route[0] != 0 or initial_route[-1] != 0:
        raise ValueError("Route must start and end at depot (0)")
    
    if len(initial_route) < 3:
        # Route is [0, 0] (depot only) - cannot improve
        from engine.instances import calculate_route_cost
        total_distance = calculate_route_cost(
            initial_route,
            distance_matrix,
            return_to_depot=False
        )
        return RouteResult(
            route=initial_route.copy(),
            total_distance=total_distance,
            algorithm="2-Opt"
        )
    
    # Work with a mutable copy
    route = initial_route.copy()
    n = len(route)
    
    # Calculate initial distance
    from engine.instances import calculate_route_cost
    best_distance = calculate_route_cost(
        route,
        distance_matrix,
        return_to_depot=False
    )
    
    improved = True
    iterations = 0
    
    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        
        # Try all pairs of edges
        # We don't touch the depot at start (index 0) or end (index n-1)
        # We consider edges (i, i+1) and (j, j+1) where 0 <= i < j-1 < n-1
        for i in range(n - 2):
            for j in range(i + 2, n):
                # Skip if this would affect depot endpoints inappropriately
                # We need i < j and at least one stop between them
                if j - i < 2:
                    continue
                
                # Calculate change in distance from 2-opt swap
                # Current edges: (route[i], route[i+1]) and (route[j], route[j+1])
                # New edges: (route[i], route[j]) and (route[i+1], route[j+1])
                
                # Handle boundary: j might be n-1 (last position)
                if j == n - 1:
                    # Can't reverse past the end depot
                    continue

                # Optional cooperative hook; default historical behavior is unchanged.
                if should_continue is not None and not should_continue():
                    return RouteResult(route=route.copy(), total_distance=best_distance,
                                       algorithm="2-Opt")
                
                # Reversal changes internal edge directions as well as the
                # boundary edges. Measure the complete proposed route so a
                # symmetric-only delta cannot accept a worse road route.
                proposed_route = route.copy()
                proposed_route[i + 1:j + 1] = reversed(route[i + 1:j + 1])
                proposed_distance = calculate_route_cost(
                    proposed_route, distance_matrix, return_to_depot=False
                )

                if proposed_distance < best_distance:
                    route = proposed_route
                    best_distance = proposed_distance
                    improved = True
                    break  # Restart from beginning after improvement
            
            if improved:
                break  # Restart outer loop
    
    # Verify final distance (sanity check)
    actual_distance = calculate_route_cost(
        route,
        distance_matrix,
        return_to_depot=False
    )
    
    return RouteResult(
        route=route,
        total_distance=actual_distance,
        algorithm="2-Opt"
    )


def nearest_neighbor_with_2opt(
    distance_matrix: np.ndarray,
    max_2opt_iterations: int = 1000
) -> RouteResult:
    """
    Construct route with Nearest Neighbor, then improve with 2-Opt.
    
    This is a complete baseline: construction + local search.
    
    Args:
        distance_matrix: NxN distance matrix (symmetric or directed)
        max_2opt_iterations: Maximum 2-Opt improvement iterations
        
    Returns:
        RouteResult with final improved route
        
    Example:
        >>> result = nearest_neighbor_with_2opt(distances)
        >>> # Result is always at least as good as pure NN
    """
    from .nearest_neighbor import nearest_neighbor
    
    # Step 1: Construct with Nearest Neighbor
    nn_result = nearest_neighbor(distance_matrix)
    
    # Step 2: Improve with 2-Opt
    improved_result = two_opt(
        nn_result.route,
        distance_matrix,
        max_iterations=max_2opt_iterations
    )
    
    # Update algorithm name to reflect full pipeline
    improved_result.algorithm = "Nearest Neighbor + 2-Opt"
    
    return improved_result
