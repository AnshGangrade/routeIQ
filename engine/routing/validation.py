"""Independent fleet feasibility and objective calculation; no solver claims trusted."""
import math
from dataclasses import dataclass

from .problem import FleetProblem


@dataclass(frozen=True)
class FleetValidation:
    route_distances: tuple[float, ...]
    total_distance: float
    longest_route_distance: float


def validate_fleet_solution(problem: FleetProblem, routes) -> FleetValidation:
    """Routes are indexed by driver slot and use problem IDs, not matrix indices.

    An idle route is [depot, depot] and costs zero (no travel), even when an
    externally supplied matrix has a nonzero diagonal. Interior depot visits
    are unsupported. Raises ValueError for any incomplete or infeasible fleet.
    """
    if len(routes) != problem.num_drivers:
        raise ValueError("Exactly one route per driver slot is required")
    indices = {node: i for i, node in enumerate(problem.node_ids)}
    visited, distances = [], []
    for driver, route in enumerate(routes):
        if (len(route) < 2 or route[0] != problem.depot_id or route[-1] != problem.depot_id):
            raise ValueError("Every route must start and end at the depot")
        if any(type(node) is not int or node not in indices for node in route):
            raise ValueError("Route contains an unknown or invalid stop ID")
        stops = route[1:-1]
        if problem.depot_id in stops:
            raise ValueError("Interior depot visits are unsupported")
        if not problem.workload.minimum_stops[driver] <= len(stops) <= problem.workload.maximum_stops[driver]:
            raise ValueError("Driver stop count violates workload bounds")
        visited.extend(stops)
        # Preserve legacy edge-by-edge accumulation (including floating-point order).
        cost = 0.0
        if stops:
            for a, b in zip(route, route[1:]):
                cost += problem.distance_matrix[indices[a]][indices[b]]
        if not math.isfinite(cost):
            raise ValueError("Route cost must be finite")
        distances.append(cost)
    if len(visited) != problem.n_stops or set(visited) != set(problem.stop_ids):
        raise ValueError("Every delivery stop must appear exactly once")
    try:
        total = sum(distances)
    except OverflowError:
        raise ValueError("Fleet cost must be finite") from None
    if not math.isfinite(total):
        raise ValueError("Fleet cost must be finite")
    return FleetValidation(tuple(distances), total, max(distances, default=0.0))
