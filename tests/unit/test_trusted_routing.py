"""Independent full-cost oracles for constructors and directed fleet neighborhoods."""
from collections import Counter
from dataclasses import FrozenInstanceError
from itertools import permutations
import math
import random

import pytest

from engine.instances import InstanceGenerator
from engine.routing import FleetProblem, FleetRouter, validate_fleet_solution
from engine.routing.construction import (
    nearest_neighbor_starts, cheapest_insertion, contiguous_sweep, legacy_angular_round_robin,
)
from engine.routing.operators import (
    Move, apply_move, improve_relocate, improve_swap, improve_or_opt_2,
    improve_cross_relocate, improve_cross_exchange, improve_two_opt,
)
from engine.routing.operators.moves import _delta_and_builder
from engine.routing.trusted import MatrixCosts

OPERATORS = dict(relocate=improve_relocate, swap=improve_swap, or_opt_2=improve_or_opt_2,
                 cross_relocate=improve_cross_relocate, cross_exchange=improve_cross_exchange)


def make_problem(n=5, drivers=2, *, directed=True, seed=0, equal=False, coordinates=False):
    rng = random.Random(seed)
    matrix = [[9 if i == j else (1 if equal else rng.randint(1, 40))
               for j in range(n+1)] for i in range(n+1)]
    if not directed:
        for i in range(n+1):
            for j in range(i):
                matrix[i][j] = matrix[j][i]
    # Deliberately nonzero depot and nonsequential IDs; matrix diagonals are nonzero.
    return FleetProblem(depot_id=100, stop_ids=tuple(10*i+1 for i in range(n)),
        num_drivers=drivers, distance_matrix=matrix, distance_units='meters', directed=directed,
        matrix_provenance={'source': 'provided'}, search_seed=seed,
        coordinates=tuple((i, i % 2) for i in range(n+1)) if coordinates else None,
        coordinate_system='cartesian' if coordinates else None)


def independent_cost(p, routes):
    mapping = {node: i for i, node in enumerate((p.depot_id,) + p.stop_ids)}
    costs = []
    for route in routes:
        value = 0.0
        if len(route) > 2:
            for a, b in zip(route, route[1:]):
                value += p.distance_matrix[mapping[a]][mapping[b]]
        costs.append(value)
    return sum(costs), tuple(costs)


def assert_plan(p, result):
    assert len(result.routes) == p.num_drivers
    assert Counter(s for r in result.routes for s in r[1:-1]) == Counter(p.stop_ids)
    for driver, route in enumerate(result.routes):
        assert route[0] == route[-1] == p.depot_id
        assert p.depot_id not in route[1:-1]
        assert p.workload.minimum_stops[driver] <= len(route)-2 <= p.workload.maximum_stops[driver]
    total, distances = independent_cost(p, result.routes)
    assert result.total_distance == total
    assert result.route_distances == distances
    assert result.longest_route_distance == max(distances, default=0)
    assert result.problem_fingerprint == p.fingerprint
    assert validate_fleet_solution(p, result.routes).total_distance == total


def closed(p, *routes):
    return tuple((p.depot_id, *route, p.depot_id) for route in routes)


@pytest.mark.parametrize('n,drivers', [(0, 1), (0, 4), (1, 5), (3, 2), (5, 2), (8, 3)])
@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('constructor', [nearest_neighbor_starts, cheapest_insertion])
def test_matrix_constructors_feasible_deterministic_and_immutable(n, drivers, directed, constructor):
    p = make_problem(n, drivers, directed=directed)
    before = p.model_dump_json()
    result = constructor(p)
    assert_plan(p, result)
    assert result == constructor(p)
    assert p.model_dump_json() == before
    with pytest.raises(FrozenInstanceError):
        result.total_distance = 0


@pytest.mark.parametrize('constructor', [nearest_neighbor_starts, cheapest_insertion])
@pytest.mark.parametrize('minimum,maximum', [([1, 2], [1, 2]), ([2, 1], [2, 1]), ([1, 1], [2, 2])])
def test_tighter_workloads_and_minimum_reservation(constructor, minimum, maximum):
    p = make_problem(3, 2, equal=True)
    p = FleetProblem.model_validate({**p.model_dump(), 'workload': {
        'minimum_stops': minimum, 'maximum_stops': maximum}})
    assert_plan(p, constructor(p))


@pytest.mark.parametrize('attempts', [0, -1, 17, 1.5, True, None])
def test_nn_attempt_limit_is_host_controlled(attempts):
    with pytest.raises(ValueError, match='attempts'):
        nearest_neighbor_starts(make_problem(), attempts=attempts)


def test_nn_starts_are_bounded_distinct_and_can_improve():
    p = make_problem(4, 1)
    # Starting with the closest stop is expensive; start 2 then 3,4,1 costs 6.
    data = p.model_dump()
    data['distance_matrix'] = [[0, 1, 2, 20, 20], [1, 0, 20, 20, 20],
                               [20, 20, 0, 1, 20], [20, 20, 20, 0, 1], [20, 1, 20, 20, 0]]
    p = FleetProblem.model_validate(data)
    single = nearest_neighbor_starts(p, attempts=1)
    multiple = nearest_neighbor_starts(p, attempts=16)
    assert multiple.total_distance == 6  # depot->2->3->4->1->depot
    assert multiple.total_distance < single.total_distance
    assert multiple.work.attempts == 4
    assert_plan(p, multiple)


def test_cheapest_insertion_uses_directed_insertion_delta():
    p = make_problem(3, 1)
    matrix = [[9, 1, 4, 7], [2, 9, 1, 8], [3, 6, 9, 1], [1, 5, 4, 9]]
    p = FleetProblem.model_validate({**p.model_dump(), 'distance_matrix': matrix})
    # First 1 (round trip 3), then 2 after 1 (delta 2), then 3 after 2 (delta -1).
    result = cheapest_insertion(p)
    assert result.routes == closed(p, p.stop_ids)
    assert result.total_distance == 4
    assert_plan(p, result)


@pytest.mark.parametrize('n,drivers', [(0, 3), (1, 4), (8, 3)])
def test_contiguous_sweep_has_contiguous_territories(n, drivers):
    p = InstanceGenerator(seed=0).generate_problem(n, drivers)
    result = contiguous_sweep(p)
    assert_plan(p, result)
    x, y = p.coordinates[0]
    angular = [node for node, coord in sorted(zip(p.stop_ids, p.coordinates[1:]),
        key=lambda pair: (math.atan2(pair[1][1]-y, pair[1][0]-x), pair[0]))]
    offset = 0
    for route in result.routes:
        count = len(route)-2
        assert set(route[1:-1]) == set(angular[offset:offset+count])
        offset += count
    assert offset == n


def test_contiguous_sweep_is_distinct_from_legacy_round_robin():
    p = InstanceGenerator(seed=7).generate_problem(8, 2)
    sweep, legacy = contiguous_sweep(p), legacy_angular_round_robin(p)
    assert {frozenset(r[1:-1]) for r in sweep.routes} != {frozenset(r[1:-1]) for r in legacy.routes}
    for method in ('nearest_neighbor', '2opt'):
        old = FleetRouter(p)
        expected = old.route_fleet_with_nearest_neighbor() if method == 'nearest_neighbor' else old.route_fleet_with_2opt()
        comparator = legacy_angular_round_robin(p, method=method)
        assert comparator.routes == tuple(tuple(r.route) for r in expected.driver_routes)
        assert comparator.total_distance == expected.total_distance


@pytest.mark.parametrize('p', [make_problem(), make_problem(directed=False, coordinates=True)])
def test_sweep_rejects_non_euclidean_inputs(p):
    with pytest.raises(ValueError, match='Euclidean'):
        contiguous_sweep(p)


def oracle_moves(p, routes, kind):
    """Enumerate neighbors by literal list edits; never use production deltas."""
    for driver, route in enumerate(routes):
        for start in range(1, len(route)-1):
            if kind in ('relocate', 'or_opt_2'):
                width = 2 if kind == 'or_opt_2' else 1
                if start + width >= len(route):
                    continue
                base = list(route)
                chain = base[start:start+width]
                del base[start:start+width]
                for target in range(1, len(base)):
                    candidate = [list(r) for r in routes]
                    candidate[driver] = base[:target] + chain + base[target:]
                    yield Move(kind, driver, start, driver, target), candidate
            elif kind == 'swap':
                for target in range(start+1, len(route)-1):
                    candidate = [list(r) for r in routes]
                    candidate[driver][start], candidate[driver][target] = route[target], route[start]
                    yield Move(kind, driver, start, driver, target), candidate
            else:
                for other, dest in enumerate(routes):
                    if driver == other:
                        continue
                    if kind == 'cross_relocate':
                        if len(route)-3 < p.workload.minimum_stops[driver] or len(dest)-1 > p.workload.maximum_stops[other]:
                            continue
                        for target in range(1, len(dest)):
                            candidate = [list(r) for r in routes]
                            node = candidate[driver].pop(start)
                            candidate[other].insert(target, node)
                            yield Move(kind, driver, start, other, target), candidate
                    else:
                        for target in range(1, len(dest)-1):
                            candidate = [list(r) for r in routes]
                            candidate[driver][start], candidate[other][target] = dest[target], route[start]
                            yield Move(kind, driver, start, other, target), candidate


@pytest.mark.parametrize('kind', list(OPERATORS))
@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('seed', [0, 9])
def test_exhaustive_small_fleet_neighborhoods_match_full_cost_oracle(kind, directed, seed):
    cross = kind.startswith('cross_')
    p = make_problem(5 if cross else 4, 2 if cross else 1, directed=directed, seed=seed)
    fingerprint = p.fingerprint
    # All 24 single-driver permutations, or all 240 feasible two-driver fleets.
    for order in permutations(p.stop_ids):
        for split in ((2, 3) if cross else (len(order),)):
            routes = closed(p, order[:split], order[split:]) if cross else closed(p, order)
            old_cost = independent_cost(p, routes)[0]
            expected = old_cost
            for move, candidate in oracle_moves(p, routes, kind):
                candidate_cost = independent_cost(p, candidate)[0]
                expected = min(expected, candidate_cost)
                delta, _ = _delta_and_builder(p, routes, move, MatrixCosts(p))
                assert delta == candidate_cost - old_cost
            actual = OPERATORS[kind](p, routes, max_moves=100_000)
            assert actual.total_distance == expected
            assert actual.work.accepted_moves == int(expected < old_cost)
            assert not actual.work.truncated
            assert_plan(p, actual)
    assert p.fingerprint == fingerprint


@pytest.mark.parametrize('kind,source,target', [
    ('relocate', ((1, 2, 3, 4),), ((2, 3, 4, 1),)),  # first -> last
    ('relocate', ((1, 2, 3, 4),), ((4, 1, 2, 3),)),  # last -> first
    ('swap', ((1, 2, 3, 4),), ((1, 3, 2, 4),)),  # adjacent
    ('swap', ((1, 2, 3, 4),), ((4, 2, 3, 1),)),  # nonadjacent
    ('or_opt_2', ((1, 2, 3, 4),), ((3, 4, 1, 2),)),
    ('cross_relocate', ((1, 2, 3), (4, 5)), ((1, 2), (3, 4, 5))),
    ('cross_exchange', ((1, 2), (3, 4)), ((1, 3), (2, 4))),
])
@pytest.mark.parametrize('directed', [False, True])
def test_known_improving_moves_have_measurable_gains(kind, source, target, directed):
    n = sum(map(len, source))
    matrix = [[0 if i == j else 20 for j in range(n+1)] for i in range(n+1)]
    for route in target:
        route = (0,) + route + (0,)
        for a, b in zip(route, route[1:]):
            matrix[a][b] = 1
            if not directed:
                matrix[b][a] = 1
    p = FleetProblem(depot_id=0, stop_ids=tuple(range(1, n+1)), num_drivers=len(source),
        distance_matrix=matrix, distance_units='map_units', directed=directed,
        matrix_provenance={'source': 'provided'})
    routes = closed(p, *source)
    result = OPERATORS[kind](p, routes)
    assert result.total_distance == n + len(source)
    assert result.total_distance < independent_cost(p, routes)[0]
    assert_plan(p, result)


@pytest.mark.parametrize('kind', list(OPERATORS))
@pytest.mark.parametrize('n,drivers', [(0, 3), (1, 4), (5, 2)])
def test_empty_routes_equal_cost_moves_and_immutable_inputs(kind, n, drivers):
    p = make_problem(n, drivers, equal=True)
    initial = cheapest_insertion(p)
    mutable = [list(r) for r in initial.routes]
    before = [r[:] for r in mutable]
    result = OPERATORS[kind](p, mutable)
    assert result.routes == initial.routes
    assert result.work.accepted_moves == 0
    assert mutable == before
    assert result == OPERATORS[kind](p, mutable)
    assert_plan(p, result)


@pytest.mark.parametrize('move', [Move('swap', 0, 0, 0, 2), Move('relocate', 0, 1, 0, 99),
    Move('or_opt_2', 0, 3, 0, 1), Move('swap', -1, 1, 0, 2), Move('swap', 0, 1, 1, 1),
    Move('cross_exchange', 0, 1, 0, 1), Move('cross_exchange', 0, 1, 1, 0),
    Move('cross_relocate', 1, 1, 0, 1), Move('unknown', 0, 1, 0, 1), Move('swap', 0, True, 0, 2)])
def test_invalid_moves_are_rejected(move):
    p = make_problem()
    routes = closed(p, p.stop_ids[:3], p.stop_ids[3:])
    with pytest.raises(ValueError):
        apply_move(p, routes, move)


@pytest.mark.parametrize('operator', [*OPERATORS.values(), improve_two_opt])
@pytest.mark.parametrize('bad', ['duplicate', 'missing', 'depot', 'workload'])
def test_invalid_input_fleets_are_rejected(operator, bad):
    p = make_problem()
    routes = [list(r) for r in closed(p, p.stop_ids[:3], p.stop_ids[3:])]
    if bad == 'duplicate':
        routes[0][1] = routes[1][1]
    elif bad == 'missing':
        routes[0].pop(1)
    elif bad == 'depot':
        routes[0].pop()
    else:
        routes[0].insert(1, routes[1].pop(1))
    with pytest.raises(ValueError):
        operator(p, routes)


@pytest.mark.parametrize('kind', list(OPERATORS))
def test_work_budget_is_enforced_and_reported(kind):
    p = make_problem(7, 2)
    routes = closed(p, p.stop_ids[:4], p.stop_ids[4:])
    result = OPERATORS[kind](p, routes, max_moves=1)
    assert result.work.candidates_evaluated == 1 and result.work.truncated
    assert result.total_distance <= independent_cost(p, routes)[0]
    for invalid in (0, 100_001, True, 1.5):
        with pytest.raises(ValueError):
            OPERATORS[kind](p, routes, max_moves=invalid)


def test_explicit_moves_use_actual_cost_and_preserve_workload_boundaries():
    p = make_problem()
    routes = closed(p, p.stop_ids[:3], p.stop_ids[3:])
    for kind in OPERATORS:
        for move, proposed in oracle_moves(p, routes, kind):
            result = apply_move(p, routes, move)
            assert result.total_distance == min(independent_cost(p, routes)[0], independent_cost(p, proposed)[0])
            assert_plan(p, result)
    # Equal counts cannot exchange count via relocation, but can exchange stops.
    equal = make_problem(4, 2)
    routes = closed(equal, equal.stop_ids[:2], equal.stop_ids[2:])
    assert improve_cross_relocate(equal, routes).work.candidates_evaluated == 0
    assert improve_cross_exchange(equal, routes).work.candidates_evaluated == 4


@pytest.mark.parametrize('directed', [False, True])
def test_existing_two_opt_integration_matches_first_improvement_full_cost_oracle(directed):
    p = make_problem(4, 1, directed=directed)
    gains = 0
    for order in permutations(p.stop_ids):
        routes = closed(p, order)
        expected, old = routes, independent_cost(p, routes)[0]
        found = False
        for first in range(1, len(routes[0])-2):
            for last in range(first+1, len(routes[0])-1):
                candidate = list(routes[0])
                candidate[first:last+1] = reversed(candidate[first:last+1])
                if independent_cost(p, [candidate])[0] < old:
                    expected, found = (tuple(candidate),), True
                    break
            if found:
                break
        result = improve_two_opt(p, routes, max_iterations=1)
        assert result.routes == expected
        gains += result.total_distance < old
        assert_plan(p, result)
    assert gains > 0


def test_two_opt_empty_fleets_and_iteration_cap():
    p = make_problem(1, 3)
    routes = closed(p, p.stop_ids, (), ())
    result = improve_two_opt(p, routes)
    assert result.routes == routes and result.work.baseline_calls == 0
    assert_plan(p, result)
    for invalid in (0, 101, True):
        with pytest.raises(ValueError):
            improve_two_opt(p, routes, max_iterations=invalid)


@pytest.mark.parametrize('kind', list(OPERATORS))
@pytest.mark.parametrize('scale', [1e-9, 0.125, 1e12])
def test_fractional_and_large_costs_match_full_neighborhood_oracle(kind, scale):
    p = make_problem(5, 2, seed=13)
    p = FleetProblem.model_validate({**p.model_dump(), 'distance_matrix': [
        [value * scale / 7 for value in row] for row in p.distance_matrix]})
    routes = closed(p, p.stop_ids[:3], p.stop_ids[3:])
    expected = min([independent_cost(p, routes)[0]] + [
        independent_cost(p, proposal)[0] for _, proposal in oracle_moves(p, routes, kind)])
    result = OPERATORS[kind](p, routes)
    assert result.total_distance == expected
    assert_plan(p, result)


@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('drivers', [1, 2, 6])
def test_cheapest_insertion_matches_independent_partial_fleet_cost_oracle(directed, drivers):
    p = make_problem(5, drivers, directed=directed, seed=23)
    routes = [list(r) for r in closed(p, *[() for _ in range(drivers)])]
    remaining = list(p.stop_ids)
    while remaining:
        before = independent_cost(p, routes)[0]
        options = []
        for driver, route in enumerate(routes):
            for node_order, node in enumerate(remaining):
                for gap in range(1, len(route)):
                    proposal = [r[:] for r in routes]
                    proposal[driver].insert(gap, node)
                    counts = [len(r)-2 for r in proposal]
                    if any(count > maximum for count, maximum in zip(counts, p.workload.maximum_stops)):
                        continue
                    missing = sum(max(0, minimum-count) for minimum, count in zip(p.workload.minimum_stops, counts))
                    if missing > len(remaining)-1:
                        continue
                    delta = independent_cost(p, proposal)[0] - before
                    options.append(((delta, driver, node_order, gap), proposal, node))
        _, routes, node = min(options, key=lambda option: option[0])
        remaining.remove(node)
    actual = cheapest_insertion(p)
    assert actual.routes == tuple(tuple(r) for r in routes)
    assert_plan(p, actual)


def test_equal_improving_moves_choose_first_in_deterministic_scan_order():
    p = make_problem(4, 1, equal=True)
    matrix = [list(row) for row in p.distance_matrix]
    matrix[0][1] = 10
    p = FleetProblem.model_validate({**p.model_dump(), 'distance_matrix': matrix})
    routes = closed(p, p.stop_ids)
    result = improve_relocate(p, routes)
    assert result.total_distance == 5
    assert result.routes == closed(p, (p.stop_ids[1], p.stop_ids[0], *p.stop_ids[2:]))
    assert result == improve_relocate(p, routes)


def test_search_seed_zero_is_respected_without_changing_global_random_state():
    p = make_problem(8, 2, seed=0)
    before = random.getstate()
    zero = nearest_neighbor_starts(p, attempts=3)
    assert random.getstate() == before
    assert zero == nearest_neighbor_starts(p, attempts=3)
    no_seed = FleetProblem.model_validate({**p.model_dump(), 'search_seed': None})
    assert nearest_neighbor_starts(no_seed, attempts=3).routes == zero.routes


def test_delta_filter_reduces_full_validations_without_losing_known_gain():
    p = InstanceGenerator(seed=42).generate_problem(100, 5)
    initial = cheapest_insertion(p)
    result = improve_cross_exchange(p, initial.routes)
    assert result.total_distance < initial.total_distance
    assert result.work.candidates_evaluated == 4000
    assert result.work.full_validations < result.work.candidates_evaluated // 10
    assert_plan(p, result)
