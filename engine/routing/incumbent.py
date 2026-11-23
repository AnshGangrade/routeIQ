"""Measured plan-level selection; research fitness never enters this decision."""

from engine.baselines import two_opt
from engine.routing.models import DriverRoute


def verify_fleet(router, result):
    """Validate assignments and recompute every cost using the trusted matrix."""
    assignments = {a.driver_id: a.stop_ids for a in router.assignments}
    if (len(result.driver_routes) != len(assignments)
            or {d.driver_id for d in result.driver_routes} != set(assignments)):
        raise ValueError("Fleet does not match driver assignments")
    for driver in result.driver_routes:
        expected = assignments[driver.driver_id]
        route = driver.route
        if (len(route) != len(expected) + 2 or route[0] != router.problem.depot_id or route[-1] != router.problem.depot_id
                or sorted(route[1:-1]) != sorted(expected)):
            raise ValueError("Route does not visit exactly its assigned stops")
        # The shared aggregator independently validates coverage/workload and costs.
    return router._aggregate_fleet_result(result.driver_routes, result.algorithm)


def select_incumbent(router, candidate_factory):
    """Evaluate all methods on one matrix/assignment, preferring baselines on ties.

    A failed method remains explicitly unavailable. No final result is returned
    unless at least one baseline can be verified.
    """
    measured, errors = {}, {}
    for name, solve in (("nearest_neighbor", router.route_fleet_with_nearest_neighbor),
                        ("2opt", router.route_fleet_with_2opt)):
        try:
            measured[name] = verify_fleet(router, solve())
        except Exception:
            errors[name] = "Baseline could not be validated"
    if not measured:
        raise ValueError("No valid baseline available")
    baseline_name = min(measured, key=lambda name: measured[name].total_distance)
    baseline = measured[baseline_name]
    raw = refined = None
    try:
        raw = verify_fleet(router, router.route_fleet_with_heuristic(candidate_factory()))
    except Exception:
        errors["raw_evolved"] = "Candidate validation or execution failed"
    if raw is not None:
        try:
            routes = []
            for driver in raw.driver_routes:
                indices = {node: i for i, node in enumerate(router.problem.node_ids)}
                improved = two_opt([indices[node] for node in driver.route], router.distance_matrix)
                routes.append(DriverRoute(
                    driver_id=driver.driver_id, assigned_stops=driver.assigned_stops,
                    route=[router.problem.node_ids[i] for i in improved.route], distance=improved.total_distance,
                    algorithm="Evolved + 2-Opt"))
            proposal = verify_fleet(router, router._aggregate_fleet_result(routes, "Evolved + 2-Opt"))
            if proposal.total_distance < raw.total_distance:
                refined = proposal
        except Exception:
            errors["refined_evolved"] = "Candidate refinement could not be validated"
    selected, source = baseline, baseline_name
    for name, result in (("raw_evolved", raw), ("refined_evolved", refined)):
        if result is not None and result.total_distance < selected.total_distance:
            selected, source = result, name
    distance = lambda value: value.total_distance if value is not None else None
    improvement = ((baseline.total_distance - selected.total_distance) / baseline.total_distance * 100
                   if baseline.total_distance else 0.0)
    report = {
        "nearest_neighbor_distance": distance(measured.get("nearest_neighbor")),
        "two_opt_distance": distance(measured.get("2opt")),
        "best_baseline_distance": baseline.total_distance,
        "raw_evolved_distance": distance(raw),
        "refined_evolved_distance": distance(refined),
        "selected_source": source,
        "baseline_retained": source in ("nearest_neighbor", "2opt"),
        "improvement_percent": improvement,
        "errors": errors,
    }
    return selected, report
