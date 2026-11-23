"""Bounded fleet constructors. Historical FleetRouter baselines are untouched."""
import math
import random
from dataclasses import replace

from .budget import SearchStopped

from .problem import FleetProblem
from .trusted import MatrixCosts, WorkCounters, bounded_integer, checked_plan

MAX_NN_ATTEMPTS = 16


def _target_counts(problem):
    counts = list(problem.workload.minimum_stops)
    remaining = problem.n_stops - sum(counts)
    for driver, maximum in enumerate(problem.workload.maximum_stops):
        extra = min(remaining, maximum - counts[driver])
        counts[driver] += extra
        remaining -= extra
    return counts


def _nearest_route(problem, nodes, costs, first=None, budget=None):
    order = {node: i for i, node in enumerate(problem.stop_ids)}
    remaining = set(nodes)
    route, considered = [problem.depot_id], 0
    if first is not None:
        route.append(first)
        remaining.remove(first)
    while remaining:
        considered += len(remaining)
        def key(node):
            if budget is not None:
                budget.require()
            return costs(route[-1], node), order[node]
        chosen = min(remaining, key=key)
        route.append(chosen)
        remaining.remove(chosen)
    return route + [problem.depot_id], considered


def nearest_neighbor_starts(problem: FleetProblem, *, attempts: int = 4, budget=None):
    """Matrix-only fleet NN with at most 16 alternative first-stop choices.

    Attempt zero starts nearest to the depot. Other first stops are a seeded
    permutation without replacement. Each attempt fills fixed feasible driver
    quotas in slot order. This is a new constructor, not the legacy baseline.
    """
    bounded_integer(attempts, "attempts", MAX_NN_ATTEMPTS)
    costs = MatrixCosts(problem)
    quotas = _target_counts(problem)
    rank = {node: i for i, node in enumerate(problem.stop_ids)}
    def start_key(node):
        if budget is not None:
            budget.require()
        return costs(problem.depot_id, node), rank[node]
    starts = sorted(problem.stop_ids, key=start_key)
    if starts:
        alternatives = starts[1:]
        random.Random(problem.search_seed if problem.search_seed is not None else 0).shuffle(alternatives)
        starts = [starts[0]] + alternatives
    else:
        starts = [None]
    best, considered, completed = None, 0, 0
    try:
        for first in starts[:attempts]:
            remaining, routes = set(problem.stop_ids), []
            first_pending = first
            for quota in quotas:
                route = [problem.depot_id]
                for _ in range(quota):
                    if first_pending is not None:
                        node, first_pending = first_pending, None
                    else:
                        considered += len(remaining)
                        def key(node):
                            if budget is not None:
                                budget.require()
                            return costs(route[-1], node), rank[node]
                        node = min(remaining, key=key)
                    route.append(node)
                    remaining.remove(node)
                routes.append(route + [problem.depot_id])
            plan = checked_plan(problem, routes, "nearest_neighbor_starts",
                                WorkCounters(candidates_evaluated=considered,
                                             attempts=completed+1, full_validations=completed+1))
            completed += 1
            if best is None or plan.total_distance < best.total_distance:
                best = plan
    except SearchStopped as exc:
        exc.best = best
        raise
    return checked_plan(problem, best.routes, "nearest_neighbor_starts",
                        WorkCounters(candidates_evaluated=considered,
                                     attempts=completed, full_validations=completed + 1))


def cheapest_insertion(problem: FleetProblem, *, budget=None):
    """Joint matrix-based assignment and insertion, with minimum-workload reserve.

    Every step chooses the cheapest directed insertion among eligible drivers.
    Once all remaining stops are needed for minimum workloads, only deficient
    drivers are eligible. Ties use driver, ordered stop ID position, then gap.
    """
    costs = MatrixCosts(problem)
    routes = [[problem.depot_id, problem.depot_id] for _ in range(problem.num_drivers)]
    remaining, evaluated = list(problem.stop_ids), 0
    while remaining:
        deficit = sum(max(0, minimum - (len(route) - 2))
                      for minimum, route in zip(problem.workload.minimum_stops, routes))
        best = None
        for driver, route in enumerate(routes):
            count = len(route) - 2
            if count == problem.workload.maximum_stops[driver]:
                continue
            if len(remaining) == deficit and count >= problem.workload.minimum_stops[driver]:
                continue
            for order, node in enumerate(remaining):
                for gap in range(1, len(route)):
                    if budget is not None:
                        budget.require()
                    evaluated += 1
                    delta = costs(route[gap-1], node) + costs(node, route[gap]) - costs(route[gap-1], route[gap])
                    key = (delta, driver, order, gap)
                    if best is None or key < best[0]:
                        best = (key, node)
        if best is None:
            raise ValueError("No workload-feasible insertion available")
        (_, driver, _, gap), node = best
        routes[driver].insert(gap, node)
        remaining.remove(node)
    return checked_plan(problem, routes, "cheapest_insertion",
                        WorkCounters(candidates_evaluated=evaluated, attempts=1, full_validations=1))


def contiguous_sweep(problem: FleetProblem, *, budget=None):
    """Contiguous angular territories followed by matrix NN within each territory."""
    if (problem.coordinates is None or problem.coordinate_system != "cartesian"
            or problem.directed or problem.matrix_provenance.source != "euclidean"):
        raise ValueError("Contiguous sweep requires coordinate-based Euclidean problems")
    x, y = problem.coordinates[0]
    def angle_key(item):
        if budget is not None:
            budget.require()
        return math.atan2(item[1][1]-y, item[1][0]-x), item[0]
    ordered = sorted(zip(problem.stop_ids, problem.coordinates[1:]), key=angle_key)
    costs, routes, offset, evaluated = MatrixCosts(problem), [], 0, 0
    for count in _target_counts(problem):
        nodes = [node for node, _ in ordered[offset:offset + count]]
        route, work = _nearest_route(problem, nodes, costs, budget=budget)
        routes.append(route)
        evaluated += work
        offset += count
    return checked_plan(problem, routes, "contiguous_sweep",
                        WorkCounters(candidates_evaluated=evaluated, attempts=1, full_validations=1))


def legacy_angular_round_robin(problem: FleetProblem, *, method="nearest_neighbor", budget=None):
    """Named compatibility comparator; preserves historical assignments and baselines."""
    from .fleet import FleetRouter
    router = FleetRouter(problem)
    if budget is not None:
        from engine.baselines import nearest_neighbor, two_opt
        if method not in ("nearest_neighbor", "2opt"):
            raise ValueError("Legacy comparator method must be nearest_neighbor or 2opt")
        result = router._route_fleet_with_baseline("Nearest Neighbor", lambda matrix:
            nearest_neighbor(matrix, checkpoint=lambda: budget.require("baseline_nn")))
        calls, validations = 1, 1
        current = checked_plan(problem, [r.route for r in result.driver_routes],
                               f"legacy_angular_round_robin/{method}", WorkCounters())
        if method == "2opt":
            indices = {node: i for i, node in enumerate(problem.node_ids)}
            matrix = problem.matrix_array()
            for driver, route in enumerate(current.routes):
                if len(route) < 4:
                    continue
                improved = two_opt([indices[node] for node in route], matrix,
                    max_iterations=1000, should_continue=lambda: budget.consume("baseline_2opt"))
                calls += 1
                validations += 1
                routes = list(current.routes)
                routes[driver] = tuple(problem.node_ids[i] for i in improved.route)
                measured = checked_plan(problem, routes, current.method, WorkCounters())
                if measured.total_distance < current.total_distance:
                    current = measured
                if budget.reason is not None:
                    break
        return replace(current, work=WorkCounters(baseline_calls=calls, full_validations=validations,
                       truncated=budget.reason is not None))
    if method == "nearest_neighbor":
        result = router.route_fleet_with_nearest_neighbor()
    elif method == "2opt":
        result = router.route_fleet_with_2opt()
    else:
        raise ValueError("Legacy comparator method must be nearest_neighbor or 2opt")
    return checked_plan(problem, [route.route for route in result.driver_routes],
                        f"legacy_angular_round_robin/{method}",
                        WorkCounters(baseline_calls=1, attempts=1, full_validations=1))
