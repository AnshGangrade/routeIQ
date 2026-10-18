"""
Heuristic scoring system for route construction.

This module provides:
- HeuristicContext: Input data for scoring candidate stops
- ScoringHeuristic: Protocol defining the heuristic interface
- RouteHarness: Trusted route builder that uses heuristics to construct routes
- Built-in heuristics: nearest_distance_heuristic

The harness constructs routes by iteratively asking the heuristic to score
candidate stops, then selecting the stop with the lowest score.
"""

from .models import HeuristicContext, HeuristicResult
from .protocol import ScoringHeuristic
from .harness import RouteHarness
from .builtin import nearest_distance_heuristic

__all__ = [
    "HeuristicContext",
    "HeuristicResult",
    "ScoringHeuristic",
    "RouteHarness",
    "nearest_distance_heuristic",
]
