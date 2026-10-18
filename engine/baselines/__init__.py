"""
Baseline routing algorithms for RouteIQ.

Provides classical heuristics for comparison against LLM-evolved methods.
"""

from .nearest_neighbor import nearest_neighbor, RouteResult
from .two_opt import two_opt, nearest_neighbor_with_2opt

__all__ = [
    "nearest_neighbor",
    "two_opt",
    "nearest_neighbor_with_2opt",
    "RouteResult",
]
