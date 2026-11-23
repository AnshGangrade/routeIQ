"""Hand-calculated contract, adapter, and API regressions; no external services."""
import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import storage
from api.main import app
from engine.baselines import nearest_neighbor, nearest_neighbor_with_2opt
from engine.evaluation.evaluator import HeuristicEvaluator
from engine.heuristics import nearest_distance_heuristic
from engine.instances import InstanceGenerator
from engine.road.models import RoadDistanceResult
from engine.routing import FleetProblem, FleetRouter, validate_fleet_solution
from engine.routing.adapters import problem_from_instance, problem_from_road_result
from engine.routing.incumbent import select_incumbent
from engine.sandbox import CandidateHeuristic

NEAREST = '''def score_candidates(context):
    return {"scores": {s: context.distance_matrix[context.current_location, s] for s in context.candidate_stops}}
'''


def problem(**changes):
    fields = dict(depot_id=10, stop_ids=[20, 30, 40], num_drivers=2,
                  distance_matrix=[[0, 2, 7, 9], [3, 0, 4, 8], [6, 5, 0, 1], [10, 11, 12, 0]],
                  distance_units="meters", directed=True,
                  matrix_provenance={"source": "provided"}, instance_seed=0, search_seed=0,
                  coordinates=[[0, 0], [1, 1], [2, 1], [3, 1]], coordinate_system="cartesian")
    fields.update(changes)
    return FleetProblem(**fields)


def changed(p, **updates):
    return FleetProblem.model_validate({**p.model_dump(), **updates})


def test_directed_hand_calculated_costs_and_balanced_counts():
    p = problem()
    result = validate_fleet_solution(p, [[10, 20, 10], [10, 30, 40, 10]])
    assert result.route_distances == (5, 18)  # 2+3 and 7+1+10
    assert result.total_distance == 23
    assert result.longest_route_distance == 18
    reverse = validate_fleet_solution(p, [[10, 20, 10], [10, 40, 30, 10]])
    assert reverse.total_distance == 32  # 5 + 9+12+6, never symmetrized
    assert p.workload.minimum_stops == (1, 1)
    assert p.workload.maximum_stops == (2, 2)


def test_symmetric_hand_calculated_cost():
    p = problem(stop_ids=[20, 30], num_drivers=1, coordinates=None, coordinate_system=None,
                directed=False, distance_matrix=[[0, 3, 4], [3, 0, 5], [4, 5, 0]])
    assert validate_fleet_solution(p, [[10, 20, 30, 10]]).total_distance == 12


@pytest.mark.parametrize("matrix", [[], [[0]], [[0, 1], [1]], [[0]*4]*3,
    [[0, -1, 2, 3]]*4, [[0, float('nan'), 2, 3]]*4,
    [[0, float('inf'), 2, 3]]*4, [[0, float('-inf'), 2, 3]]*4])
def test_invalid_matrix_rejected(matrix):
    with pytest.raises(ValueError):
        problem(distance_matrix=matrix)


@pytest.mark.parametrize("updates", [
    {"stop_ids": [20, 20, 40]}, {"depot_id": 20}, {"stop_ids": [20, True, 40]},
    {"num_drivers": 0}, {"num_drivers": 1.5}, {"directed": False},
    {"coordinates": [[1, 2]]}, {"coordinates": [[0, 0, 0]]*4},
    {"coordinates": [[0, float('nan')]]*4}, {"coordinates": [[0, float('inf')]]*4},
    {"coordinate_system": "lon_lat", "coordinates": [[181, 0]]*4},
    {"coordinate_system": None}, {"distance_units": "degrees"},
    {"schema_version": "fleet-problem/v2"}, {"objective": {"primary": "duration"}},
    {"workload": {"minimum_stops": [0, 0], "maximum_stops": [3, 3]}},
    {"workload": {"minimum_stops": [2, 2], "maximum_stops": [2, 2]}},
    {"workload": {"minimum_stops": [1], "maximum_stops": [2]}},
])
def test_invalid_definition_rejected(updates):
    with pytest.raises(ValueError):
        problem(**updates)


@pytest.mark.parametrize("routes", [
    [[10, 20, 10], [10, 30, 10]],  # missing
    [[10, 20, 10], [10, 20, 40, 10]],  # duplicate
    [[10, 20, 10], [10, 30, 40]],  # missing depot return
    [[20, 10], [10, 30, 40, 10]],  # missing start
    [[10, 10], [10, 20, 30, 40, 10]],  # count bounds
    [[10, 20, 10]],  # missing driver
    [[10, 20, 10], [10, 30, 40, 10], [10, 10]],  # extra driver
    [[10, 20, 10], [10, 10, 30, 40, 10]],  # interior depot
    [[10, 20, 10], [10, 99, 40, 10]],  # unknown
    [[10, 20, 10], [10, 30., 40, 10]],  # noninteger
])
def test_invalid_fleet_rejected(routes):
    with pytest.raises(ValueError):
        validate_fleet_solution(problem(), routes)


def test_more_drivers_than_stops_and_idle_route_semantics():
    p = problem(stop_ids=[20], distance_matrix=[[17, 3], [7, 0]], num_drivers=3,
                coordinates=None, coordinate_system=None)
    measured = validate_fleet_solution(p, [[10, 20, 10], [10, 10], [10, 10]])
    assert measured.route_distances == (10, 0, 0)
    assert measured.total_distance == measured.longest_route_distance == 10
    assert p.workload.minimum_stops == (0, 0, 0)
    assert p.workload.maximum_stops == (1, 1, 1)


def test_zero_stops_can_route_all_idle_drivers():
    p = problem(stop_ids=[], distance_matrix=[[7]], num_drivers=3,
                coordinates=None, coordinate_system=None)
    assert FleetRouter(p).route_fleet_with_nearest_neighbor().total_distance == 0
    assert validate_fleet_solution(p, [[10, 10]]*3).longest_route_distance == 0


def test_matrix_and_nested_metadata_immutable_and_input_detached():
    source = [[0, 3, 4], [3, 0, 5], [4, 5, 0]]
    p = problem(stop_ids=[20, 30], distance_matrix=source, num_drivers=1,
                coordinates=None, coordinate_system=None)
    before = p.fingerprint
    source[0][1] = 999
    assert p.distance_matrix[0][1] == 3
    with pytest.raises(TypeError):
        p.distance_matrix[0][1] = 4
    with pytest.raises(ValidationError):
        p.num_drivers = 4
    with pytest.raises(ValidationError):
        p.workload.policy = "unbalanced"
    with pytest.raises(ValidationError):
        p.matrix_provenance.source = "road"
    array = p.matrix_array()
    with pytest.raises(ValueError):
        array[0, 1] = 0
    with pytest.raises(ValueError):
        array.setflags(write=True)
    assert p.fingerprint == before


def test_stable_serialization_and_separate_search_seed():
    p = problem()
    restored = FleetProblem.model_validate_json(p.model_dump_json())
    assert p == restored
    assert p.fingerprint == restored.fingerprint
    assert p.matrix_fingerprint == restored.matrix_fingerprint
    assert p.seed == p.search_seed == 0
    assert changed(p, search_seed=123).fingerprint == p.fingerprint
    assert changed(p, instance_seed=123).fingerprint != p.fingerprint


@pytest.mark.parametrize("updates", [
    {"num_drivers": 3, "workload": None}, {"depot_id": 11}, {"stop_ids": [30, 20, 40]},
    {"distance_units": "kilometers"}, {"coordinates": [[0, 0], [2, 2], [2, 1], [3, 1]]},
    {"matrix_provenance": {"source": "provided", "dataset_version": "v2"}},
    {"objective": {"secondary_metric": None}},
    {"workload": {"minimum_stops": [1, 2], "maximum_stops": [1, 2]}},
])
def test_relevant_problem_fields_change_fingerprint(updates):
    p = problem()
    other = changed(p, **updates)
    assert other.fingerprint != p.fingerprint
    assert other.matrix_fingerprint == p.matrix_fingerprint


def test_matrix_content_changes_both_fingerprints_and_symmetry_metadata_changes_identity():
    p = problem()
    matrix = [list(row) for row in p.distance_matrix]
    matrix[0][1] += 1
    other = changed(p, distance_matrix=matrix)
    assert other.fingerprint != p.fingerprint
    assert other.matrix_fingerprint != p.matrix_fingerprint
    symmetric = problem(distance_matrix=np.ones((4, 4)).tolist(), directed=False)
    assert changed(symmetric, directed=True).fingerprint != symmetric.fingerprint


@pytest.mark.parametrize("drivers", [1, 2, 5])
@pytest.mark.parametrize("method", ["nearest_neighbor", "2opt", "heuristic"])
def test_application_and_evaluation_use_identical_problem_matrix_routes_and_metrics(drivers, method):
    p = problem(num_drivers=drivers)
    router, evaluator = FleetRouter(p), HeuristicEvaluator()
    if method == "nearest_neighbor":
        app_result = router.route_fleet_with_nearest_neighbor()
        benchmark = evaluator.evaluate_baseline_nn([p])
    elif method == "2opt":
        app_result = router.route_fleet_with_2opt()
        benchmark = evaluator.evaluate_baseline_2opt([p])
    else:
        app_result = router.route_fleet_with_heuristic(nearest_distance_heuristic)
        benchmark = evaluator.evaluate_candidate(CandidateHeuristic(source_code=NEAREST), [p], "nn")
    result = benchmark.per_instance_results[0]
    assert benchmark.failed_evaluations == 0
    assert result.instance_fingerprint == p.fingerprint
    assert result.num_drivers == drivers and result.distance_units == "meters"
    assert result.fleet_routes == [r.route for r in app_result.driver_routes]
    assert result.distance == app_result.total_distance
    assert result.longest_route_distance == app_result.longest_route_distance
    assert result.distance == validate_fleet_solution(p, result.fleet_routes).total_distance
    # Would be tiny coordinate distances if the provided matrix were discarded.
    assert result.distance == {1: 17, 2: 33, 5: 37}[drivers]


def test_reassignment_validator_is_global_not_locked_to_baseline_territories():
    p = problem()
    first = validate_fleet_solution(p, [[10, 20, 10], [10, 30, 40, 10]])
    second = validate_fleet_solution(p, [[10, 30, 10], [10, 20, 40, 10]])
    assert (first.total_distance, second.total_distance) == (23, 33)


def test_legacy_single_route_baseline_definitions_preserved():
    legacy = InstanceGenerator(seed=0).generate(8)
    matrix = problem_from_instance(legacy).matrix_array()
    evaluator = HeuristicEvaluator()
    for result, expected in [
        (evaluator.evaluate_baseline_nn([legacy]), nearest_neighbor(matrix)),
        (evaluator.evaluate_baseline_2opt([legacy]), nearest_neighbor_with_2opt(matrix, max_2opt_iterations=100))]:
        row = result.per_instance_results[0]
        assert row.route == expected.route and row.distance == expected.total_distance


def test_synthetic_generator_and_explicit_road_adapter():
    p = InstanceGenerator(seed=0).generate_problem(5, 3, search_seed=9)
    assert p.matrix_provenance.source == "euclidean"
    assert p.distance_units == "map_units" and not p.directed
    assert p.instance_seed == 0 and p.search_seed == 9
    instance = InstanceGenerator(seed=0).generate(3)
    # Safe latitude range for the explicit lon/lat adapter.
    for point in instance.get_all_locations():
        point.y /= 2
    matrix = [list(row) for row in problem().distance_matrix]
    road = problem_from_road_result(instance, 2, RoadDistanceResult(provider="offline", distances=matrix))
    assert road.distance_matrix == problem().distance_matrix
    assert road.distance_units == "meters" and road.directed
    assert road.matrix_provenance.source == "road"
    with pytest.raises(ValueError):
        problem_from_road_result(instance, 2, RoadDistanceResult(provider="offline", error="failed"))
    with pytest.raises(ValueError):
        problem_from_instance(instance, 2, distance_units="meters")


def test_matrix_only_single_driver_works_multi_driver_fails_explicitly():
    p = problem(num_drivers=1, coordinates=None, coordinate_system=None)
    result = HeuristicEvaluator().evaluate_baseline_nn([p])
    assert result.successful_evaluations == 1
    multi = changed(p, num_drivers=2, workload=None)
    result = HeuristicEvaluator().evaluate_baseline_nn([multi])
    assert result.failed_evaluations == 1 and result.mean_distance is None
    with pytest.raises(ValueError, match="requires coordinates"):
        FleetRouter(multi)


def test_full_fleet_incumbent_accepts_nonzero_depot_and_nonsequential_ids():
    p = problem()
    result, report = select_incumbent(FleetRouter(p), lambda: nearest_distance_heuristic)
    assert result.total_distance == validate_fleet_solution(p, [r.route for r in result.driver_routes]).total_distance
    assert result.total_distance <= report['best_baseline_distance']


@pytest.mark.parametrize("mode", ["synthetic", "road"])
def test_api_cached_problem_is_shared_with_evaluation(mode, monkeypatch):
    import engine.road
    from api.routers import routing
    matrix = np.arange(36, dtype=float).reshape(6, 6) + 10
    np.fill_diagonal(matrix, 0)
    monkeypatch.setattr(engine.road, 'create_road_distance_matrix', lambda coords:
        (matrix, RoadDistanceResult(provider='offline', distances=matrix.tolist())))
    monkeypatch.setattr(routing, 'get_route_geometry_if_road', lambda *args: (None, None, None))
    storage.instance_store.clear()
    storage.routing_results.clear()
    try:
        with TestClient(app) as client:
            payload = dict(num_stops=5, num_drivers=2, seed=0, mode=mode)
            if mode == 'road':
                payload.update(depot_coords=[12, 50], stop_coords=[[12+i/100, 50] for i in range(5)])
            created = client.post('/api/instances', json=payload)
            assert created.status_code == 200, created.text
            identifier = created.json()['instance_id']
            stored = storage.instance_store[identifier]
            p = stored['problem']
            assert p.distance_units == ('meters' if mode == 'road' else 'map_units')
            for method, evaluate in [('nearest_neighbor', HeuristicEvaluator().evaluate_baseline_nn),
                                     ('2opt', HeuristicEvaluator().evaluate_baseline_2opt)]:
                solved = client.post('/api/routing/solve', json=dict(instance_id=identifier, method=method))
                assert solved.status_code == 200, solved.text
                result = evaluate([p]).per_instance_results[0]
                assert solved.json()['total_distance'] == result.distance
                assert [d['route'] for d in solved.json()['drivers']] == result.fleet_routes
            # Legacy records remain supported without reconstructing their road matrix.
            del stored['problem']
            legacy = client.post('/api/routing/solve', json=dict(instance_id=identifier, method='2opt'))
            assert legacy.status_code == 200
            assert legacy.json()['total_distance'] == result.distance
    finally:
        storage.instance_store.clear()
        storage.routing_results.clear()


def test_comparison_rejects_different_matrix_and_driver_contract():
    p = problem()
    evaluator = HeuristicEvaluator()
    candidate = evaluator.evaluate_candidate(CandidateHeuristic(source_code=NEAREST), [p], 'candidate')
    matrix = [list(row) for row in p.distance_matrix]
    matrix[0][1] += 100
    for other in [changed(p, num_drivers=3, workload=None), changed(p, distance_units='kilometers'),
                  changed(p, distance_matrix=matrix)]:
        with pytest.raises(ValueError, match='match the comparison instances'):
            evaluator.compare_with_baselines(candidate, [other])
    assert evaluator.compare_with_baselines(candidate, [p]).improvement_vs_nn == 0


def test_training_and_held_out_can_consume_canonical_fleet_batches(monkeypatch):
    from engine.evolution import EvolutionConfig, EvolutionLoop
    from engine.llm.models import LLMResponse

    class OfflineClient:
        def generate(self, request):
            return LLMResponse(raw_content=NEAREST, provider='mock', model='offline',
                               generation_id=request.generation_id)

    train, held_out = problem(), problem(num_drivers=5, instance_seed=1)
    loop = EvolutionLoop(EvolutionConfig(num_generations=1, candidates_per_generation=1), OfflineClient())

    def supply_problems():
        loop.training_instances = [train]
        loop.test_instances = [held_out]
        loop.evaluator = HeuristicEvaluator()

    monkeypatch.setattr(loop, '_generate_instances', supply_problems)
    result = loop.run_evolution()
    assert result.status == 'completed'
    assert result.best_training_fitness == 33
    assert result.test_evaluation.evolved_avg_distance == 37
    assert all(b.avg_route_distance == 37 for b in result.test_evaluation.baselines)
    # The same evaluator can be used for a separate validation split without changing its objective.
    validation = HeuristicEvaluator().evaluate_candidate(CandidateHeuristic(source_code=NEAREST),
                                                         [train], 'validation')
    assert validation.mean_distance == result.best_training_fitness


def test_failed_candidate_keeps_fleet_metadata_and_never_improves():
    p = problem()
    evaluator = HeuristicEvaluator()
    invalid = CandidateHeuristic(source_code='import os')
    result = evaluator.evaluate_candidate(invalid, [p], 'invalid')
    row = result.per_instance_results[0]
    assert row.num_drivers == 2 and row.distance_units == 'meters'
    assert row.instance_fingerprint == p.fingerprint
    comparison = evaluator.compare_with_baselines(result, [p])
    assert comparison.improvement_vs_nn is None and comparison.improvement_vs_2opt is None


def test_mixed_unit_batches_cannot_be_averaged():
    p = problem()
    with pytest.raises(ValueError, match='different units'):
        HeuristicEvaluator().evaluate_baseline_nn([p, changed(p, distance_units='kilometers')])


def test_finite_edges_cannot_produce_an_infinite_objective():
    p = problem(distance_matrix=[[1e308]*4]*4)
    with pytest.raises(ValueError, match='finite'):
        validate_fleet_solution(p, [[10, 20, 10], [10, 30, 40, 10]])


@pytest.mark.parametrize('corruption', ['depot', 'stop', 'count'])
def test_legacy_adapters_still_reject_invalid_index_contracts(corruption):
    instance = InstanceGenerator(seed=0).generate(3)
    if corruption == 'depot':
        instance.depot.id = 10
    elif corruption == 'stop':
        instance.stops[1].id = 99
    else:
        instance.n_stops = 2
    with pytest.raises(ValueError, match='Legacy instances'):
        problem_from_instance(instance)
    with pytest.raises(ValueError, match='Legacy instances'):
        FleetRouter(instance, 1)


def test_canonical_and_legacy_2opt_iteration_defaults_are_explicit(monkeypatch):
    import engine.evaluation.evaluator as module
    seen = []
    original = module.nearest_neighbor_with_2opt

    def observe(matrix, max_2opt_iterations):
        seen.append(max_2opt_iterations)
        return original(matrix, max_2opt_iterations=max_2opt_iterations)

    monkeypatch.setattr(module, 'nearest_neighbor_with_2opt', observe)
    evaluator = HeuristicEvaluator()
    evaluator.evaluate_baseline_2opt([InstanceGenerator(seed=0).generate(3)])
    evaluator.evaluate_baseline_2opt([problem(num_drivers=1)])
    evaluator.evaluate_baseline_2opt([problem(num_drivers=1)], max_2opt_iterations=7)
    assert seen == [100, 1000, 7]


@pytest.mark.parametrize('corruption', ['matrix', 'drivers', 'coordinates'])
def test_api_rejects_legacy_cache_fields_that_disagree_with_problem(corruption):
    storage.instance_store.clear()
    storage.routing_results.clear()
    try:
        with TestClient(app) as client:
            response = client.post('/api/instances', json=dict(num_stops=5, num_drivers=2, seed=0))
            assert response.status_code == 200
            identifier = response.json()['instance_id']
            stored = storage.instance_store[identifier]
            original = stored['problem'].fingerprint
            if corruption == 'matrix':
                stored['distance_matrix'] = stored['distance_matrix'].copy()
                stored['distance_matrix'][0, 1] += 1
            elif corruption == 'drivers':
                stored['num_drivers'] = 3
            else:
                stored['instance'].stops[0].location.x += 1
            result = client.post('/api/routing/solve', json=dict(instance_id=identifier, method='nearest_neighbor'))
            assert result.status_code == 400
            assert stored['problem'].fingerprint == original
            assert (identifier, 'nearest_neighbor') not in storage.routing_results
    finally:
        storage.instance_store.clear()
        storage.routing_results.clear()
