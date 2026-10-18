"""
Protocol definition for scoring heuristics.

A heuristic is any callable that accepts a HeuristicContext
and returns a HeuristicResult with scores for each candidate.
"""

from typing import Protocol, runtime_checkable
from .models import HeuristicContext, HeuristicResult


@runtime_checkable
class ScoringHeuristic(Protocol):
    """
    Protocol for a route construction heuristic.
    
    A heuristic scores candidate stops to guide route construction.
    The harness calls the heuristic at each step and selects the
    candidate with the lowest score.
    
    Contract:
    ---------
    Input (HeuristicContext):
        - current_location: Where we are now (0=depot, 1..N=stops)
        - candidate_stops: Unvisited stops that need scoring
        - distance_matrix: Full NxN distance matrix (read-only)
        - partial_route: Route constructed so far (read-only context)
    
    Output (HeuristicResult):
        - scores: Dict mapping each candidate stop to a finite numeric score
        - Lower scores indicate more preferred candidates
        - Must provide exactly one score per candidate
        - All scores must be finite (no NaN, no infinity)
    
    The heuristic must NOT:
        - Modify the context
        - Construct routes directly
        - Access external state
        - Perform I/O
        - Raise exceptions (except for programmer errors)
    
    Example:
    --------
    def simple_distance_heuristic(ctx: HeuristicContext) -> HeuristicResult:
        '''Score candidates by distance from current location.'''
        scores = {
            stop: ctx.distance_matrix[ctx.current_location, stop]
            for stop in ctx.candidate_stops
        }
        return HeuristicResult(scores=scores)
    """
    
    def __call__(self, context: HeuristicContext) -> HeuristicResult:
        """
        Score candidate stops based on the current context.
        
        Args:
            context: Current location, candidates, distances, partial route
            
        Returns:
            HeuristicResult with one finite score per candidate
            (lower scores = more preferred)
            
        Raises:
            ValueError: If unable to score candidates (programmer error)
        """
        ...
