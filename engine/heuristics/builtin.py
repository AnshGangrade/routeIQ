"""
Built-in scoring heuristics.

These provide working examples and baselines for comparison.
"""

from .models import HeuristicContext, HeuristicResult


def nearest_distance_heuristic(context: HeuristicContext) -> HeuristicResult:
    """
    Score candidates by distance from current location.
    
    This is the canonical example heuristic. It scores each candidate
    using its Euclidean distance from the current location.
    
    With the harness's deterministic tie-breaking, this reproduces
    the Nearest Neighbor baseline algorithm exactly.
    
    Scoring:
        score(candidate) = distance_matrix[current_location, candidate]
        Lower distance = lower score = more preferred
    
    Args:
        context: Current location, candidate stops, and distance matrix
        
    Returns:
        HeuristicResult with distance-based scores
        
    Example:
        >>> ctx = HeuristicContext(
        ...     current_location=0,
        ...     candidate_stops=[1, 2, 3],
        ...     distance_matrix=np.array([[0, 10, 20, 30],
        ...                               [10, 0, 5, 15],
        ...                               [20, 5, 0, 10],
        ...                               [30, 15, 10, 0]]),
        ...     partial_route=[0]
        ... )
        >>> result = nearest_distance_heuristic(ctx)
        >>> result.scores
        {1: 10.0, 2: 20.0, 3: 30.0}
        >>> # Stop 1 has lowest score, so harness will select it
    """
    scores = {
        stop: float(context.distance_matrix[context.current_location, stop])
        for stop in context.candidate_stops
    }
    
    return HeuristicResult(scores=scores)
