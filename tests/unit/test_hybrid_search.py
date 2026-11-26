"""Offline budget, VND, ILS and independent full-fleet result verification."""
from dataclasses import replace
from itertools import permutations
import random

import pytest

from engine.baselines import nearest_neighbor, two_opt
from engine.instances import InstanceGenerator
from engine.routing import FleetProblem, FleetRouter, validate_fleet_solution
from engine.routing.budget import SearchBudget, SearchStopped
from engine.routing.construction import nearest_neighbor_starts, legacy_angular_round_robin
from engine.routing.operators import improve_relocate, improve_two_opt
from engine.routing.search import SearchConfig, solve_hybrid, OPERATORS
from engine.routing.trusted import WorkCounters, checked_plan


def problem(n=8, drivers=2, seed=2, directed=True):
    rng = random.Random(seed)
    matrix = [[0 if i == j else rng.randint(1, 50) for j in range(n+1)] for i in range(n+1)]
    if not directed:
        for i in range(n+1):
            for j in range(i):
                matrix[i][j] = matrix[j][i]
    return FleetProblem(depot_id=0, stop_ids=tuple(range(1, n+1)), num_drivers=drivers,
        distance_matrix=matrix, distance_units='map_units', directed=directed,
        matrix_provenance={'source': 'provided'}, search_seed=0)


def cost(p, routes):
    ids = {node: i for i, node in enumerate(p.node_ids)}
    distances = []
    for route in routes:
        distance = 0.0
        if len(route) > 2:
            for a, b in zip(route, route[1:]):
                distance += p.distance_matrix[ids[a]][ids[b]]
        distances.append(distance)
    return sum(distances), tuple(distances)


def assert_result(p, result):
    plans = [result.initial_solution, result.final_solution]
    plans += [r.plan for r in result.construction_candidates if r.plan]
    plans += [event.raw_candidate for event in result.events if event.raw_candidate]
    for plan in plans:
        measured = validate_fleet_solution(p, plan.routes)
        total, distances = cost(p, plan.routes)
        assert plan.total_distance == measured.total_distance == total
        assert plan.route_distances == distances
        assert plan.longest_route_distance == max(distances, default=0)
        assert plan.problem_fingerprint == p.fingerprint
    assert result.final_solution.total_distance == min(plan.total_distance for plan in plans)
    assert result.final_solution.total_distance <= result.initial_solution.total_distance
    bests = [event.best_distance for event in result.events]
    assert bests == sorted(bests, reverse=True)
    assert result.operations_used <= result.operation_limit
    assert sum(value for _, value in result.work_by_category) == result.operations_used
    initial, final = result.initial_solution.total_distance, result.final_solution.total_distance
    assert result.improvement_percent == ((initial-final)/initial*100 if initial else 0)


def test_vnd_improves_and_restarts_order_on_a_real_constructed_case():
    p = InstanceGenerator(seed=42).generate_problem(20, 3)
    result = solve_hybrid(p, config=SearchConfig(ils_iterations=0),
                          operation_budget=200_000, time_limit_seconds=60)
    assert result.final_solution.total_distance < result.initial_solution.total_distance
    assert result.accepted_moves > 0
    steps = [event for event in result.events if event.stage == 'vnd']
    assert steps[0].method == 'relocate'
    for index, event in enumerate(steps[:-1]):
        if event.accepted:
            assert steps[index+1].method == 'relocate'
    assert result.status == 'completed'
    assert_result(p, result)


def test_ils_escapes_verified_local_optimum_and_respects_exhaustive_global_oracle():
    # Fixed directed 8-stop fixture generated with Python Random(2), integer arcs 1..50.
    p = problem()
    config = SearchConfig(ils_iterations=0, max_operator_calls=1000)
    vnd = solve_hybrid(p, config=config, operation_budget=500_000, time_limit_seconds=60)
    assert vnd.final_solution.total_distance == 151
    for operator in OPERATORS.values():
        assert operator(p, vnd.final_solution.routes).total_distance == 151
    ils = solve_hybrid(p, config=replace(config, ils_iterations=5),
                       operation_budget=500_000, time_limit_seconds=60)
    assert ils.final_solution.total_distance == 132
    assert ils.final_solution.total_distance < vnd.final_solution.total_distance
    optimum = min(cost(p, [(0, *order[:4], 0), (0, *order[4:], 0)])[0]
                  for order in permutations(p.stop_ids))
    assert optimum == 120  # ILS improves this fixture but does not find its global optimum.
    assert optimum <= ils.final_solution.total_distance
    assert ils.diversifications <= config.max_diversifications
    assert any(event.stage == 'perturbation' and event.raw_candidate.total_distance > event.best_distance
               for event in ils.events)
    assert_result(p, ils)


@pytest.mark.parametrize('limit', [0, 1, 10, 100, 1000, 4000])
def test_budget_exhaustion_always_returns_best_verified_feasible_plan(limit):
    p = problem(12, 3)
    result = solve_hybrid(p, operation_budget=limit, time_limit_seconds=60)
    assert result.operations_used == limit
    assert result.termination_reason == 'operation_budget'
    assert result.status == 'stopped' and result.budget_exhausted
    assert_result(p, result)


@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('seed', [0, 11])
def test_reproducible_work_trace_matrix_immutability_and_seed_zero(directed, seed):
    p = problem(directed=directed)
    before, rng_state = p.model_dump_json(), random.getstate()
    a = solve_hybrid(p, search_seed=seed, time_limit_seconds=60)
    b = solve_hybrid(p, search_seed=seed, time_limit_seconds=60)
    assert replace(a, elapsed_seconds=0) == replace(b, elapsed_seconds=0)
    assert a.search_seed == seed
    assert p.model_dump_json() == before and random.getstate() == rng_state
    assert_result(p, a)


def test_precancel_and_zero_deadline_do_not_claim_baselines_were_measured():
    p = problem()
    for args, reason in [({'should_cancel': lambda: True}, 'cancelled'),
                         ({'time_limit_seconds': 0}, 'deadline')]:
        result = solve_hybrid(p, **args)
        assert result.termination_reason == reason and result.status == 'stopped'
        assert result.operations_used == 0
        assert all(c.status == 'not_started' for c in result.construction_candidates[1:])
        assert result.final_solution.method == 'ordered_feasible_seed'
        assert_result(p, result)


def test_injected_clock_stops_during_construction():
    ticks = iter(i/100 for i in range(10000))
    result = solve_hybrid(problem(), time_limit_seconds=.08, clock=lambda: next(ticks))
    assert result.termination_reason == 'deadline' and result.budget_exhausted
    assert result.operations_used < result.operation_limit
    assert any(c.status == 'interrupted' for c in result.construction_candidates)
    assert_result(problem(), result)


@pytest.mark.parametrize('operator', [improve_relocate, improve_two_opt])
def test_cancellation_is_checked_inside_operator_scans(operator):
    p = problem(20, 1)
    routes = [(0, *p.stop_ids, 0)]
    budget = SearchBudget(10000, 60)
    budget.should_cancel = lambda: budget.used >= 7
    result = operator(p, routes, budget=budget)
    assert budget.reason == 'cancelled' and budget.used == 7
    assert result.work.truncated
    assert result.total_distance <= cost(p, routes)[0]
    assert result.total_distance == cost(p, result.routes)[0]


def test_improvement_found_before_scan_interruption_is_retained():
    p = problem(5, 1)
    matrix = [[0 if i == j else 1 for j in range(6)] for i in range(6)]
    matrix[0][1] = 20
    p = FleetProblem.model_validate({**p.model_dump(), 'distance_matrix': matrix})
    routes = [(0, *p.stop_ids, 0)]
    result = improve_relocate(p, routes, budget=SearchBudget(1, 60))
    assert result.total_distance == 6 < cost(p, routes)[0]
    assert result.work.truncated


def test_solver_cancellation_during_vnd_keeps_the_best_plan(monkeypatch):
    import engine.routing.search as module
    original = module.OPERATORS['relocate']
    cancel = [False]

    def interrupt(p, routes, *, budget, **kwargs):
        used = budget.used
        budget.should_cancel = lambda: budget.used >= used+3
        result = original(p, routes, budget=budget, **kwargs)
        cancel[0] = True
        return result

    monkeypatch.setitem(module.OPERATORS, 'relocate', interrupt)
    p = problem()
    result = solve_hybrid(p, time_limit_seconds=60)
    assert cancel[0] and result.termination_reason == 'cancelled'
    assert not result.budget_exhausted
    assert result.events[-1].status == 'interrupted'
    assert_result(p, result)


def test_nn_retains_complete_attempt_when_next_attempt_is_interrupted():
    p = problem(4, 1)
    # Four first-stop rankings + six next-stop comparisons complete attempt zero.
    budget = SearchBudget(11, 60)
    with pytest.raises(SearchStopped) as stopped:
        nearest_neighbor_starts(p, attempts=4, budget=budget)
    assert stopped.value.best is not None
    assert stopped.value.best.total_distance == nearest_neighbor_starts(p, attempts=1).total_distance
    validate_fleet_solution(p, stopped.value.best.routes)


@pytest.mark.parametrize('method', ['nearest_neighbor', '2opt'])
@pytest.mark.parametrize('drivers', [1, 3, 9])
def test_budget_hooks_do_not_change_legacy_baseline_results(method, drivers):
    p = InstanceGenerator(seed=0).generate_problem(7, drivers)
    plain = legacy_angular_round_robin(p, method=method)
    bounded = legacy_angular_round_robin(p, method=method, budget=SearchBudget(100000, 60))
    assert bounded.routes == plain.routes
    assert bounded.total_distance == plain.total_distance


@pytest.mark.parametrize('n,drivers', [(0, 3), (1, 5), (3, 7)])
def test_more_drivers_than_stops_and_empty_routes(n, drivers):
    p = problem(n, drivers)
    result = solve_hybrid(p, time_limit_seconds=60)
    assert_result(p, result)
    if n < 2:
        assert result.termination_reason == 'no_perturbation_available'


@pytest.mark.parametrize('value', [0, 1])
def test_zero_distance_ties_do_not_claim_improvement_and_prefer_measured_baseline(value):
    p = InstanceGenerator(seed=0).generate_problem(5, 2)
    p = FleetProblem.model_validate({**p.model_dump(), 'distance_matrix': [[value]*6]*6})
    result = solve_hybrid(p, config=SearchConfig(ils_iterations=2), time_limit_seconds=60)
    assert result.improvement_percent == 0
    assert result.final_solution.method == 'legacy_angular_round_robin/nearest_neighbor'
    assert result.accepted_moves == 0
    assert_result(p, result)


def test_failed_and_forged_operator_outputs_cannot_improve_result(monkeypatch):
    import engine.routing.search as module
    p = problem()

    def invalid(p, routes, **kwargs):
        valid = checked_plan(p, routes, 'invalid', WorkCounters())
        return replace(valid, routes=((0, 0),)*p.num_drivers, total_distance=0)

    monkeypatch.setitem(module.OPERATORS, 'relocate', invalid)
    result = solve_hybrid(p, time_limit_seconds=60)
    assert result.status == 'failed' and result.termination_reason == 'operator_error'
    assert result.final_solution.total_distance == result.initial_solution.total_distance
    assert result.events[-1].raw_candidate is None
    assert_result(p, result)


def test_incorrect_reported_cost_is_recomputed_before_acceptance(monkeypatch):
    import engine.routing.search as module

    def forged(p, routes, **kwargs):
        plan = checked_plan(p, routes, 'forged', WorkCounters())
        return replace(plan, total_distance=0, longest_route_distance=0)

    monkeypatch.setitem(module.OPERATORS, 'relocate', forged)
    p = problem()
    result = solve_hybrid(p, config=SearchConfig(operators=('relocate',), ils_iterations=0), time_limit_seconds=60)
    assert result.improvement_percent == 0
    assert_result(p, result)


def test_failed_constructor_is_explicit_and_does_not_discard_baselines(monkeypatch):
    import engine.routing.search as module
    def fail(*args, **kwargs):
        raise ValueError('private error contents')
    monkeypatch.setattr(module, 'cheapest_insertion', fail)
    p = InstanceGenerator(seed=4).generate_problem(10, 2)
    result = solve_hybrid(p, config=SearchConfig(operators=(), ils_iterations=0), time_limit_seconds=60)
    assert any(c.method == 'cheapest_insertion' and c.status == 'failed' for c in result.construction_candidates)
    assert 'private error contents' not in repr(result)
    assert_result(p, result)


def test_independent_operator_and_neighborhood_caps_are_reported():
    p = problem(10, 2)
    capped = solve_hybrid(p, config=SearchConfig(max_operator_calls=1), time_limit_seconds=60)
    assert capped.operator_calls == 1
    assert capped.termination_reason == 'operator_call_limit' and capped.budget_exhausted
    partial = solve_hybrid(p, config=SearchConfig(max_moves_per_operator=1, ils_iterations=0), time_limit_seconds=60)
    assert partial.neighborhoods_truncated > 0
    assert partial.termination_reason == 'neighborhood_limit'
    assert partial.status == 'stopped' and not partial.budget_exhausted
    assert partial.execution_contract['neighborhoods_truncated'] > 0
    assert partial.execution_contract['schema_version'] == 'fleet-search-status/v2'


@pytest.mark.parametrize('kwargs', [dict(nn_attempts=17), dict(max_operator_calls=-1),
    dict(ils_iterations=101), dict(perturbation_moves=0), dict(max_diversifications=-1),
    dict(operators=('unknown',)), dict(operators=('swap', 'swap')), dict(max_moves_per_operator=True)])
def test_invalid_search_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        SearchConfig(**kwargs)


@pytest.mark.parametrize('kwargs', [dict(operation_budget=-1), dict(operation_budget=True),
    dict(time_limit_seconds=float('inf')), dict(time_limit_seconds=-1),
    dict(search_seed=True), dict(construction_strategy='unknown')])
def test_invalid_host_budget_and_strategy_are_rejected(kwargs):
    with pytest.raises(ValueError):
        solve_hybrid(problem(), **kwargs)


def test_cancellation_callback_failure_is_not_reported_as_completion():
    def fail():
        raise RuntimeError('private')
    result = solve_hybrid(problem(), should_cancel=fail)
    assert result.status == 'failed' and result.termination_reason == 'cancellation_error'
    assert 'private' not in repr(result)
    assert_result(problem(), result)


def test_baseline_is_retained_when_every_hybrid_candidate_is_worse(monkeypatch):
    import engine.routing.search as module
    p = InstanceGenerator(seed=42).generate_problem(20, 3)
    worse = module._bootstrap(p)
    baseline = FleetRouter(p).route_fleet_with_2opt()
    assert worse.total_distance > baseline.total_distance
    def bad(*args, **kwargs):
        return worse
    for name in ('nearest_neighbor_starts', 'cheapest_insertion', 'contiguous_sweep'):
        monkeypatch.setattr(module, name, bad)
    for name in module.OPERATORS:
        monkeypatch.setitem(module.OPERATORS, name, bad)
    result = solve_hybrid(p, config=SearchConfig(ils_iterations=0), time_limit_seconds=60)
    assert result.final_solution.total_distance == baseline.total_distance
    assert result.final_solution.method == 'legacy_angular_round_robin/2opt'
    assert result.accepted_moves == 0 and result.improvement_percent == 0
    assert any(e.raw_candidate and e.raw_candidate.total_distance > e.best_distance for e in result.events)
    assert_result(p, result)


def test_budgeted_legacy_baselines_match_directed_and_tied_matrices():
    p = InstanceGenerator(seed=4).generate_problem(8, 3)
    for matrix in (problem(8, 3).distance_matrix, [[1]*9]*9):
        q = FleetProblem.model_validate({**p.model_dump(), 'distance_matrix': matrix, 'directed': True})
        for method in ('nearest_neighbor', '2opt'):
            a = legacy_angular_round_robin(q, method=method)
            b = legacy_angular_round_robin(q, method=method, budget=SearchBudget(100_000, 60))
            assert a.routes == b.routes and a.total_distance == b.total_distance


def test_cancelled_2opt_keeps_already_accepted_reversals():
    p = problem(8, 1)
    route = list(range(9)) + [0]
    budget = SearchBudget(7, 60)
    result = two_opt(route, p.matrix_array(), should_continue=lambda: budget.consume('two_opt'))
    assert budget.used == 7 and budget.reason == 'operation_budget'
    assert result.total_distance < cost(p, [route])[0]
    assert result.total_distance == cost(p, [result.route])[0]


def test_cancellation_between_operator_admission_checks_returns_a_plan(monkeypatch):
    # Exercise the second check at operator admission rather than throwing out
    # the incumbent when cancellation arrives between two neighboring checks.
    admitted = []
    original = SearchBudget.consume
    def cancel_at_admission(self, category='search'):
        if category == 'operator_call':
            admitted.append(True)
            self.should_cancel = lambda: True
        return original(self, category)
    monkeypatch.setattr(SearchBudget, 'consume', cancel_at_admission)
    p = problem(3, 1)
    result = solve_hybrid(p, time_limit_seconds=60)
    assert admitted and result.termination_reason == 'cancelled'
    assert result.operator_calls == 0
    assert_result(p, result)


@pytest.mark.parametrize('operator', [improve_relocate, improve_two_opt])
def test_deadline_is_checked_inside_operator_scans(operator):
    ticks = iter(i/100 for i in range(10000))
    p = problem(20, 1)
    budget = SearchBudget(10000, .10, clock=lambda: next(ticks))
    result = operator(p, [(0, *p.stop_ids, 0)], budget=budget)
    assert budget.reason == 'deadline' and budget.used < budget.limit
    assert result.work.truncated
    assert cost(p, result.routes)[0] == result.total_distance


def test_budget_limit_never_increments_past_the_admitted_operation():
    budget = SearchBudget(3, 60)
    assert [budget.consume('test') for _ in range(5)] == [True, True, True, False, False]
    assert budget.used == 3 and dict(budget.counts) == {'test': 3}


def test_tighter_driver_workloads_remain_feasible_when_legacy_comparators_fail():
    p = InstanceGenerator(seed=42).generate_problem(5, 2)
    p = FleetProblem.model_validate({**p.model_dump(), 'workload': {
        'minimum_stops': (2, 3), 'maximum_stops': (2, 3)}})
    result = solve_hybrid(p, time_limit_seconds=60)
    assert any(c.method == 'legacy_nn' and c.status == 'failed' for c in result.construction_candidates)
    assert [len(r)-2 for r in result.final_solution.routes] == [2, 3]
    assert_result(p, result)
