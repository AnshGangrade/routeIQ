"""
Route construction harness using scoring heuristics.

The harness is the trusted component that builds valid routes by
iteratively consulting a heuristic for scoring guidance.
"""

import numpy as np
from typing import List, Callable
from .models import HeuristicContext, HeuristicResult
from .protocol import ScoringHeuristic
from engine.baselines import RouteResult


class RouteHarness:
    """
    Trusted route builder using heuristic scoring.
    
    The harness:
    1. Starts at the depot
    2. Presents current context to the heuristic
    3. Gets scores for all unvisited candidates
    4. Selects the candidate with lowest score (deterministic tie-breaking)
    5. Moves to that stop
    6. Repeats until all stops visited
    7. Returns to depot
    8. Calculates total distance
    
    The harness validates all heuristic outputs and rejects invalid results.
    
    Example:
        >>> harness = RouteHarness()
        >>> result = harness.build_route(
        ...     heuristic=my_heuristic,
        ...     distance_matrix=distances,
        ...     n_stops=10
        ... )
        >>> print(result.route)  # [0, 3, 1, 5, ..., 0]
    """
    
    def __init__(self):
        """Initialize the harness."""
        pass
    
    def build_route(
        self,
        heuristic: ScoringHeuristic,
        distance_matrix: np.ndarray,
        n_stops: int,
        algorithm_name: str = "Heuristic"
    ) -> RouteResult:
        """
        Build a complete route using the provided heuristic.
        
        Args:
            heuristic: Scoring function that implements ScoringHeuristic protocol
            distance_matrix: NxN symmetric distance matrix (0=depot, 1..N=stops)
            n_stops: Number of delivery stops (not including depot)
            algorithm_name: Name for the algorithm (default: "Heuristic")
            
        Returns:
            RouteResult with complete route [0, ..., 0] and total distance
            
        Raises:
            ValueError: If heuristic returns invalid scores or if inputs are invalid
            TypeError: If heuristic doesn't implement the protocol correctly
            
        Example:
            >>> def nearest(ctx):
            ...     scores = {s: ctx.distance_matrix[ctx.current_location, s]
            ...               for s in ctx.candidate_stops}
            ...     return HeuristicResult(scores=scores)
            >>> harness = RouteHarness()
            >>> result = harness.build_route(nearest, dist_matrix, n_stops=5)
        """
        # Validate inputs
        self._validate_inputs(distance_matrix, n_stops)
        
        # Special case: no delivery stops (depot only)
        if n_stops == 0:
            from engine.instances import calculate_route_cost
            route = [0, 0]
            distance = calculate_route_cost(route, distance_matrix, return_to_depot=False)
            return RouteResult(
                route=route,
                total_distance=distance,
                algorithm=algorithm_name
            )
        
        # Initialize route construction
        current_location = 0  # Start at depot
        partial_route = [0]
        unvisited = set(range(1, n_stops + 1))  # All delivery stops
        
        # Iteratively select next stop
        while unvisited:
            # Never expose the reference used to measure route cost. A fresh
            # copy also prevents mutations from leaking into later decisions,
            # even if candidate code makes its own array writable again.
            candidate_matrix = distance_matrix.copy()
            candidate_matrix.setflags(write=False)
            # Build context for heuristic
            context = HeuristicContext(
                current_location=current_location,
                candidate_stops=sorted(unvisited),  # Sorted for consistency
                distance_matrix=candidate_matrix,
                partial_route=partial_route.copy()  # Defensive copy
            )
            
            # Get scores from heuristic
            try:
                result = heuristic(context)
            except Exception as e:
                raise ValueError(
                    f"Heuristic raised exception: {type(e).__name__}: {e}"
                ) from e
            
            # Validate result type
            if not isinstance(result, HeuristicResult):
                raise TypeError(
                    f"Heuristic must return HeuristicResult, got {type(result)}"
                )
            
            # Select best candidate (lowest score with deterministic tie-breaking)
            try:
                next_stop = result.get_best_stop(context.candidate_stops)
            except ValueError as e:
                raise ValueError(
                    f"Invalid heuristic output: {e}"
                ) from e
            
            # Move to selected stop
            partial_route.append(next_stop)
            unvisited.remove(next_stop)
            current_location = next_stop
        
        # Return to depot
        partial_route.append(0)
        
        # Calculate total distance
        from engine.instances import calculate_route_cost
        total_distance = calculate_route_cost(
            partial_route,
            distance_matrix,
            return_to_depot=False  # Already added depot to route
        )
        
        return RouteResult(
            route=partial_route,
            total_distance=total_distance,
            algorithm=algorithm_name
        )
    
    def _validate_inputs(self, distance_matrix: np.ndarray, n_stops: int) -> None:
        """
        Validate harness inputs.
        
        Args:
            distance_matrix: Distance matrix to validate
            n_stops: Number of stops to validate
            
        Raises:
            ValueError: If inputs are invalid
        """
        # Validate distance matrix
        if not isinstance(distance_matrix, np.ndarray):
            raise TypeError("distance_matrix must be a numpy array")
        
        if distance_matrix.size == 0:
            raise ValueError("distance_matrix cannot be empty")
        
        if distance_matrix.ndim != 2:
            raise ValueError("distance_matrix must be 2-dimensional")
        
        if distance_matrix.shape[0] != distance_matrix.shape[1]:
            raise ValueError("distance_matrix must be square")
        
        # Validate n_stops
        if not isinstance(n_stops, (int, np.integer)):
            raise TypeError("n_stops must be an integer")
        
        if n_stops < 0:
            raise ValueError("n_stops cannot be negative")
        
        # Check matrix size matches n_stops
        expected_size = n_stops + 1  # +1 for depot
        if distance_matrix.shape[0] != expected_size:
            raise ValueError(
                f"distance_matrix size {distance_matrix.shape[0]} doesn't match "
                f"n_stops={n_stops} (expected {expected_size})"
            )
