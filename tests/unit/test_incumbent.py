"""Offline regressions for transparent, same-plan non-regression."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.storage import instance_store, routing_results, evolution_runs
from engine.evaluation.evaluator import HeuristicEvaluator
from engine.heuristics import HeuristicResult, nearest_distance_heuristic
from engine.instances import InstanceGenerator, calculate_route_cost
from engine.routing.fleet import FleetRouter
from engine.routing.incumbent import select_incumbent
from engine.sandbox import CandidateHeuristic

NEAREST = '''def score_candidates(context):
    return {"scores": {s: context.distance_matrix[context.current_location, s] for s in context.candidate_stops}}
'''


def make_router(seed=42, drivers=2, directed=False):
    instance = InstanceGenerator(seed=seed).generate(n_stops=8)
    router = FleetRouter(instance, drivers)
    if directed:
        rng = np.random.default_rng(seed)
        matrix = rng.uniform(1, 40, (9, 9))
        np.fill_diagonal(matrix, 0)
        router = FleetRouter(instance, drivers, matrix)
    return router


def farthest(context):
    return HeuristicResult(scores={s: -context.distance_matrix[context.current_location, s] for s in context.candidate_stops})


@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('drivers', [1, 3])
def test_selected_never_regresses_and_all_methods_share_assignments(directed, drivers):
    router = make_router(drivers=drivers, directed=directed)
    before = router.distance_matrix.copy()
    nn = router.route_fleet_with_nearest_neighbor()
    opt = router.route_fleet_with_2opt()
    raw = router.route_fleet_with_heuristic(farthest)
    result, report = select_incumbent(router, lambda: farthest)
    assert report['nearest_neighbor_distance'] == nn.total_distance
    assert report['two_opt_distance'] == opt.total_distance
    assert report['raw_evolved_distance'] == raw.total_distance
    assert result.total_distance <= min(nn.total_distance, opt.total_distance)
    for driver, assignment in zip(result.driver_routes, router.assignments):
        assert sorted(driver.route[1:-1]) == sorted(assignment.stop_ids)
        assert driver.distance == calculate_route_cost(driver.route, before, return_to_depot=False)
    np.testing.assert_array_equal(before, router.distance_matrix)


def test_tie_keeps_baseline_and_reports_zero():
    router = make_router()
    matrix = np.ones_like(router.distance_matrix)
    np.fill_diagonal(matrix, 0)
    router = FleetRouter(router.instance, router.num_drivers, matrix)
    result, report = select_incumbent(router, lambda: nearest_distance_heuristic)
    assert report['baseline_retained']
    assert report['raw_evolved_distance'] == result.total_distance
    assert report['improvement_percent'] == 0
    assert report['refined_evolved_distance'] is None


def test_verified_refinement_can_genuinely_beat_baseline():
    router = make_router(seed=3, drivers=1, directed=True)
    result, report = select_incumbent(router, lambda: farthest)
    assert report['raw_evolved_distance'] > report['best_baseline_distance']
    assert result.total_distance < report['best_baseline_distance']
    assert result.total_distance == report['refined_evolved_distance']
    assert report['selected_source'] == 'refined_evolved'
    assert not report['baseline_retained']
    assert report['improvement_percent'] == pytest.approx(
        100 * (report['best_baseline_distance'] - result.total_distance) / report['best_baseline_distance'])


def test_forged_cost_is_recomputed_and_invalid_route_is_rejected(monkeypatch):
    router = make_router()
    raw = router.route_fleet_with_heuristic(farthest)
    expected = raw.total_distance
    raw.total_distance = 0
    for driver in raw.driver_routes:
        driver.distance = 0
    monkeypatch.setattr(router, 'route_fleet_with_heuristic', lambda _: raw)
    _, report = select_incumbent(router, lambda: farthest)
    assert report['raw_evolved_distance'] == expected
    raw.driver_routes[0].route = [0, 0]
    _, report = select_incumbent(router, lambda: farthest)
    assert report['raw_evolved_distance'] is None
    assert report['baseline_retained']


@pytest.mark.parametrize('failure', ['validation', 'execution', 'timeout'])
def test_invalid_candidate_preserves_baseline(failure):
    router = make_router()
    def fail(*args):
        raise TimeoutError('sensitive') if failure == 'timeout' else ValueError('sensitive')
    factory = fail if failure == 'validation' else lambda: fail
    result, report = select_incumbent(router, factory)
    assert result.total_distance == report['best_baseline_distance']
    assert report['baseline_retained'] and report['raw_evolved_distance'] is None
    assert 'raw_evolved' in report['errors']
    assert 'sensitive' not in str(report)


def test_matrix_mutation_cannot_falsify_selection():
    router = make_router()
    before = router.distance_matrix.copy()
    def mutate(ctx):
        ctx.distance_matrix.setflags(write=True)
        ctx.distance_matrix[:] = 0
        return HeuristicResult(scores={s: s for s in ctx.candidate_stops})
    raw = router.route_fleet_with_heuristic(mutate)
    result, report = select_incumbent(router, lambda: mutate)
    np.testing.assert_array_equal(router.distance_matrix, before)
    assert report['raw_evolved_distance'] == sum(calculate_route_cost(d.route, before, return_to_depot=False) for d in raw.driver_routes)
    assert result.total_distance > 0


def test_failed_baseline_is_explicit_and_all_baselines_failed_is_error(monkeypatch):
    router = make_router()
    def fail():
        raise ValueError('baseline failed')
    monkeypatch.setattr(router, 'route_fleet_with_2opt', fail)
    _, report = select_incumbent(router, lambda: farthest)
    assert report['two_opt_distance'] is None and '2opt' in report['errors']
    monkeypatch.setattr(router, 'route_fleet_with_nearest_neighbor', fail)
    with pytest.raises(ValueError, match='No valid baseline'):
        select_incumbent(router, lambda: farthest)


def test_same_seed_and_size_with_different_coordinates_cannot_be_compared():
    evaluator = HeuristicEvaluator()
    instance = make_router().instance
    result = evaluator.evaluate_candidate(CandidateHeuristic(source_code=NEAREST), [instance], 'candidate')
    changed = instance.model_copy(deep=True)
    changed.stops[0].location.x += 10
    with pytest.raises(ValueError, match='match the comparison instances'):
        evaluator.compare_with_baselines(result, [changed])


def test_preview_does_not_apply_and_application_recomputes_different_plans():
    instance_store.clear(); routing_results.clear(); evolution_runs.clear()
    evolution_runs['winner'] = {'status': 'completed', 'best_code': NEAREST}
    try:
        with TestClient(app) as client:
            distances = []
            for seed in (0, 91):
                instance = client.post('/api/instances', json={'num_stops': 5, 'num_drivers': 2, 'seed': seed}).json()
                payload = {'instance_id': instance['instance_id'], 'method': 'evolved', 'run_id': 'winner'}
                preview = client.post('/api/routing/solve', json={**payload, 'preview': True})
                assert preview.status_code == 200, preview.json()
                assert (instance['instance_id'], 'evolved') not in routing_results
                applied = client.post('/api/routing/solve', json=payload).json()
                assert applied['total_distance'] == preview.json()['total_distance']
                assert applied['run_id'] == 'winner'
                assert applied['total_distance'] <= applied['optimization']['best_baseline_distance']
                comparison = client.get(f"/api/results/{instance['instance_id']}/comparison").json()
                assert comparison['comparisons'][0]['optimization'] == applied['optimization']
                distances.append(applied['total_distance'])
            assert distances[0] != distances[1]
    finally:
        instance_store.clear(); routing_results.clear(); evolution_runs.clear()
