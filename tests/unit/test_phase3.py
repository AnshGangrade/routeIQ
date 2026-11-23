"""Offline safety, lifecycle and route-application checks. No real HTTP transport."""
import importlib.util
import json
import os
from pathlib import Path
import threading

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.storage import evolution_runs, instance_store, routing_results
from engine.heuristics import HeuristicContext
from engine.instances import calculate_route_cost
from engine.llm.mock import MockLLMClient
from engine.road.models import RoadDistanceResult
from engine.sandbox import CandidateHeuristic, HeuristicExecutor, HeuristicValidator


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import dotenv
    import httpx
    def forbidden(*args, **kwargs):
        raise AssertionError('External HTTP and environment-file access forbidden')
    monkeypatch.setattr(dotenv, 'load_dotenv', forbidden)
    monkeypatch.setattr(dotenv, 'dotenv_values', forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)


@pytest.fixture
def client():
    instance_store.clear()
    evolution_runs.clear()
    routing_results.clear()
    with TestClient(app) as result:
        yield result
    instance_store.clear()
    evolution_runs.clear()
    routing_results.clear()


def context():
    return HeuristicContext(current_location=0, candidate_stops=[1, 2], partial_route=[0],
                            distance_matrix=np.array([[0., 2., 3.], [2., 0., 1.], [3., 1., 0.]]))


def test_real_worker_has_distinct_pid_resource_limits_and_is_reaped(monkeypatch):
    import engine.sandbox.executor as module
    original = module.subprocess.Popen
    launches = []
    def launch(*args, **kwargs):
        # Verify exact environment keys; never inspect host credential values.
        assert set(kwargs['env']) <= {'SYSTEMROOT'}
        assert args[0][1:4] == ['-I', '-S', '-B']
        process = original(*args, **kwargs)
        launches.append(process)
        return process
    monkeypatch.setattr(module.subprocess, 'Popen', launch)
    result = HeuristicExecutor().execute(CandidateHeuristic(source_code='''def score_candidates(context):
    return {"scores": {s: context.distance_matrix[0, s] for s in context.candidate_stops}}
'''), context())
    assert result.is_success, result.error
    assert result.output['scores'] == {1: 2., 2: 3.}
    assert result.details['pid'] != os.getpid()
    assert result.details['resource_limits']
    assert result.details['reaped']
    assert len(launches) == 1 and launches[0].poll() is not None


def test_infinite_worker_is_killed_and_reaped(monkeypatch):
    import engine.sandbox.executor as module
    original = module.subprocess.Popen
    processes = []
    def launch(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(module.subprocess, 'Popen', launch)
    result = HeuristicExecutor(timeout=0.2).execute(CandidateHeuristic(source_code='''def score_candidates(context):
    while True:
        pass
'''), context())
    assert result.status == 'timeout'
    assert processes and all(process.poll() is not None for process in processes)


@pytest.mark.parametrize('body', [
    'np.loadtxt("forbidden.txt")', 'np.save("forbidden.txt", [1])',
    'import os', 'context.__class__', 'getattr(context, "distance_matrix")',
    'open("forbidden.txt")', 'f = abs\n    f(-1)',
])
def test_unsupported_capabilities_fail_closed_before_launch(monkeypatch, body):
    import engine.sandbox.executor as module
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: pytest.fail('Must reject before launching'))
    candidate = CandidateHeuristic(source_code=f'def score_candidates(context):\n    {body}\n    return {{"scores": {{1: 1, 2: 2}}}}')
    assert not HeuristicValidator().validate(candidate).is_valid
    assert not HeuristicExecutor().execute(candidate, context()).is_success


def test_missing_os_resource_limits_refuses_execution(monkeypatch, capsys):
    path = Path('engine/sandbox/worker.py')
    spec = importlib.util.spec_from_file_location('test_worker', path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    def fail(*args):
        raise RuntimeError('No supported isolation')
    monkeypatch.setattr(worker, 'install_limits', fail)
    monkeypatch.setattr(worker.sys, 'argv', ['worker', '1'])
    monkeypatch.setattr(worker.Interpreter, 'run', lambda *a: pytest.fail('Candidate must not run'))
    worker.main()
    response = json.loads(capsys.readouterr().out)
    assert response['status'] == 'runtime_error'
    assert response['details']['resource_limits'] is None


def test_worker_memory_limit_returns_failure_not_host_allocation():
    result = HeuristicExecutor(timeout=2).execute(CandidateHeuristic(source_code='''def score_candidates(context):
    values = list(range(100000000))
    return {"scores": {1: 1, 2: 2}}
'''), context())
    assert not result.is_success
    assert result.status in ('runtime_error', 'timeout')


def test_apply_real_winner_recomputes_selected_instances_and_exposes_held_out(client):
    response = client.post('/api/evolution/runs', json={
        'num_stops': 10, 'num_instances': 3, 'num_generations': 2,
        'candidates_per_generation': 2, 'elites_kept': 1, 'mode': 'mock', 'seed': 42,
    })
    assert response.status_code == 200
    run_id = response.json()['run_id']
    best = client.get(f'/api/evolution/runs/{run_id}/best')
    assert best.status_code == 200, best.json()
    data = best.json()
    assert data['training_fitness'] == data['heuristic']['fitness']
    assert data['test_evaluation']['test_instances_count'] == 2
    assert data['validation_fitness'] == data['test_evaluation']['evolved_avg_distance']
    progress = client.get(f'/api/evolution/runs/{run_id}').json()
    assert progress['status'] == progress['stage'] == 'completed'
    assert progress['test_evaluation'] == data['test_evaluation']
    for count in (5, 7):
        instance = client.post('/api/instances', json={'num_stops': count, 'num_drivers': 2, 'seed': 9}).json()
        instance_id = instance['instance_id']
        for method in ('nearest_neighbor', '2opt', 'evolved'):
            result = client.post('/api/routing/solve', json={'instance_id': instance_id, 'method': method, 'run_id': run_id})
            assert result.status_code == 200, result.json()
            result = result.json()
            matrix = instance_store[instance_id]['distance_matrix']
            expected = sum(calculate_route_cost(d['route'], matrix, return_to_depot=False) for d in result['drivers'])
            assert result['total_distance'] == pytest.approx(expected)
            assert sorted(s for d in result['drivers'] for s in d['route'] if s) == list(range(1, count + 1))
        comparison = client.get(f'/api/results/{instance_id}/comparison').json()
        assert {c['method'] for c in comparison['comparisons']} == {'nearest_neighbor', '2opt', 'evolved'}


def test_progress_visible_while_running_and_cancellation_reaches_terminal_state(client, monkeypatch):
    import api.routers.evolution as module
    entered = threading.Event()
    release = threading.Event()
    clients = []
    class GatedClient(MockLLMClient):
        closed = False
        def generate(self, request):
            if self._call_count == 1:
                entered.set()
                assert release.wait(15)
            return super().generate(request)
        def close(self):
            self.closed = True
    def create(config):
        result = GatedClient(config)
        clients.append(result)
        return result
    monkeypatch.setattr(module, 'create_client', create)
    config = dict(num_stops=10, num_instances=3, num_generations=2,
                  candidates_per_generation=2, elites_kept=1, seed=42, mode='mock')
    evolution_runs['gated'] = dict(run_id='gated', config=config, status='pending', current_generation=0,
                                  total_generations=2, generations=[], best_heuristic_id=None, error=None)
    thread = threading.Thread(target=module.run_evolution_background, args=('gated', config))
    thread.start()
    try:
        assert entered.wait(15)
        progress = client.get('/api/evolution/runs/gated').json()
        assert thread.is_alive()
        assert progress['status'] == 'running'
        assert progress['current_generation'] == 1
        assert progress['candidates_done'] == 1
        assert progress['stage'] == 'evaluating_candidates'
        assert client.post('/api/evolution/runs/gated/cancel').json()['status'] == 'cancelling'
    finally:
        release.set()
        thread.join(15)
    assert not thread.is_alive()
    assert clients[0].closed
    assert client.get('/api/evolution/runs/gated').json()['status'] == 'cancelled'
    assert client.get('/api/evolution/runs/gated/best').status_code == 400
    instance = client.post('/api/instances', json={'num_stops': 5, 'num_drivers': 1}).json()
    assert client.post('/api/routing/solve', json={'instance_id': instance['instance_id'], 'method': 'evolved', 'run_id': 'gated'}).status_code == 409


@pytest.mark.parametrize('depot,stop,count', [([13], [13, 52], 5), ([13, 52, 1], [13, 52], 5),
    ([13, 52], [13], 5), ([13, 91], [13, 52], 5), ([13, 52], [13, 52], 100)])
def test_bad_road_coordinates_and_limits_fail_before_network(client, monkeypatch, depot, stop, count):
    import engine.road.adapter as module
    monkeypatch.setattr(module, 'get_osrm_table', lambda *a, **k: pytest.fail('No road request expected'))
    response = client.post('/api/instances', json={'num_stops': count, 'num_drivers': 1, 'mode': 'road',
        'depot_coords': depot, 'stop_coords': [stop] * count})
    assert response.status_code == 400


@pytest.mark.parametrize('matrix', [[[0.]], [[float('inf')] * 6] * 6, [[-1.] * 6] * 6])
def test_malformed_road_matrix_has_clear_service_error(client, monkeypatch, matrix):
    import engine.road.adapter as module
    monkeypatch.setattr(module, 'get_osrm_table', lambda *a, **k: RoadDistanceResult(provider='osrm', distances=matrix))
    response = client.post('/api/instances', json={'num_stops': 5, 'num_drivers': 1, 'mode': 'road',
        'depot_coords': [13.4, 52.5], 'stop_coords': [[13.5, 52.6]] * 5})
    assert response.status_code == 503
    assert 'matrix' in response.json()['detail']


def test_unique_instances_do_not_overwrite_results(client):
    request = {'num_stops': 5, 'num_drivers': 1, 'seed': 42}
    first = client.post('/api/instances', json=request).json()
    second = client.post('/api/instances', json=request).json()
    assert first['instance_id'] != second['instance_id']
    assert first['stops'] == second['stops']


@pytest.mark.parametrize('valid', [True, False])
def test_evolution_terminal_logs_work_on_windows_cp1252(monkeypatch, valid):
    import io
    import sys
    from engine.evolution import EvolutionConfig, EvolutionLoop
    from engine.llm.models import LLMResponse
    class Client:
        def generate(self, request):
            source = ('def score_candidates(context):\n'
                      '    return {"scores": {s: s for s in context.candidate_stops}}')
            return LLMResponse(raw_content=source if valid else 'invalid source', provider='mock', model='offline')
    output = io.TextIOWrapper(io.BytesIO(), encoding='cp1252')
    monkeypatch.setattr(sys, 'stdout', output)
    loop = EvolutionLoop(EvolutionConfig(num_generations=1, candidates_per_generation=1,
        training_instance_count=1, test_instance_count=1, num_stops=2), Client())
    result = loop.run_evolution()
    assert result.status == ('completed' if valid else 'failed')
