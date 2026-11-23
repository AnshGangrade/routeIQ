"""Offline reliability regression tests; no secret-file or network access."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api import storage
from api.routers import evolution
from engine.llm import LLMConfig, LLMProvider, GenerationRequest, create_client
from engine.road.models import RoadRoutingConfig
from engine.road.osrm import OSRMClient
from tests.unit.test_phase3 import offline, client


@pytest.mark.parametrize('field,value', [('seed', -1), ('seed', 2**32), ('layout', 'invalid'), ('num_drivers', 0), ('num_drivers', 21), ('num_stops', 201)])
def test_instance_boundary(client, field, value):
    response = client.post('/api/instances', json={'num_stops': 5, 'num_drivers': 1, field: value})
    assert response.status_code == 422
    assert 'input' not in response.json()['detail'][0]


def test_uuid_instances_do_not_share_cached_routes(client):
    payload = {'num_stops': 5, 'num_drivers': 1, 'seed': 0}
    a, b = [client.post('/api/instances', json=payload).json() for _ in range(2)]
    assert a['instance_id'] != b['instance_id'] and a['stops'] == b['stops']
    assert client.post('/api/routing/solve', json={'instance_id': a['instance_id'], 'method': 'nearest_neighbor'}).status_code == 200
    assert client.get(f"/api/results/{b['instance_id']}/comparison").status_code == 404


def test_road_cache_namespaced_by_endpoint_and_https():
    config = RoadRoutingConfig(cache_enabled=False)
    assert config.base_url == 'https://router.project-osrm.org'
    with OSRMClient(config) as a, OSRMClient(config.model_copy(update={'base_url': 'http://localhost:5000'})) as b:
        assert a._cache_key([(1, 2)]) != b._cache_key([(1, 2)])
        assert a._cache_key([(1, 2)]) != a._cache_key([(2, 1)])


@pytest.mark.parametrize('other,expected', [(0., 0.), (1., None)])
def test_zero_distance_comparison(client, other, expected):
    instance = client.post('/api/instances', json={'num_stops': 5, 'num_drivers': 1}).json()['instance_id']
    for method, distance in [('nearest_neighbor', 0.), ('2opt', other)]:
        storage.routing_results[instance, method] = SimpleNamespace(total_distance=distance, longest_route_distance=distance, computation_time=0.)
    response = client.get(f'/api/results/{instance}/comparison')
    assert response.status_code == 200
    assert response.json()['comparisons'][1]['improvement_vs_nn'] == expected


def test_invalid_depot_rejected(client):
    instance = client.post('/api/instances', json={'num_stops': 5, 'num_drivers': 1}).json()['instance_id']
    storage.instance_store[instance]['instance'].depot.id = 7
    assert client.post('/api/routing/solve', json={'instance_id': instance, 'method': 'nearest_neighbor'}).status_code == 400


def test_capacity_limits(client, monkeypatch):
    monkeypatch.setattr(storage, 'MAX_INSTANCES', 1)
    assert client.post('/api/instances', json={'num_stops': 5, 'num_drivers': 1}).status_code == 200
    assert client.post('/api/instances', json={'num_stops': 5, 'num_drivers': 1}).status_code == 429
    monkeypatch.setattr(storage, 'MAX_ACTIVE_RUNS', 0)
    assert client.post('/api/evolution/runs', json={}).status_code == 429
    monkeypatch.setattr(storage, 'MAX_ACTIVE_RUNS', 2)
    monkeypatch.setattr(storage, 'MAX_RUNS', 0)
    assert client.post('/api/evolution/runs', json={}).status_code == 429


def test_expensive_request_slots_release_on_failure():
    with pytest.raises(RuntimeError):
        with storage.expensive_request():
            raise RuntimeError('test')
    with storage.expensive_request(), storage.expensive_request(), storage.expensive_request(), storage.expensive_request():
        with pytest.raises(Exception) as exc:
            with storage.expensive_request():
                pass
        assert exc.value.status_code == 429


def state(run_id):
    return {'run_id': run_id, 'status': 'pending', 'generations': [], 'error': None,
            'current_generation': 0, 'total_generations': 2, 'best_heuristic_id': None,
            'config': {'candidates_per_generation': 2}}


@pytest.mark.parametrize('mode', ['mock', 'replay', 'live'])
def test_configuration_seed_and_cleanup(client, monkeypatch, mode):
    captured = {}
    fake_client = Mock()
    def create(config):
        captured['llm'] = config
        return fake_client
    class Loop:
        def __init__(self, config, **kwargs):
            captured['evolution'] = config
        def run_evolution(self):
            raise RuntimeError('sensitive-upstream-marker')
    monkeypatch.setattr(evolution, 'create_client', create)
    monkeypatch.setattr(evolution, 'EvolutionLoop', Loop)
    monkeypatch.setenv('LLM_API_KEY', 'offline-placeholder')
    monkeypatch.setenv('LLM_BASE_URL', 'https://invalid.example')
    monkeypatch.delenv('LLM_MODEL', raising=False)
    monkeypatch.setenv('LLM_TEMPERATURE', 'invalid-but-overridden')
    response = client.post('/api/evolution/runs', json={'mode': mode, 'seed': 0, 'llm_model': 'chosen-model', 'temperature': 0.0})
    run_id = response.json()['run_id']
    assert len(run_id) == 32
    assert captured['llm'].model == 'chosen-model' and captured['llm'].temperature == 0.
    assert captured['evolution'].seed == 0
    fake_client.close.assert_called_once()
    result = client.get(f'/api/evolution/runs/{run_id}').json()
    assert result['status'] == result['stage'] == 'failed'
    assert 'sensitive-upstream-marker' not in str(result)
    assert 'traceback' not in storage.evolution_runs[run_id]


def test_cli_invalid_configuration(capsys):
    from scripts.run_evolution import main
    assert main(['--gens', '0']) == 2
    assert 'Traceback' not in capsys.readouterr().out


def test_cli_constructor_failure_closes_client(monkeypatch):
    from scripts import run_evolution
    fake = Mock()
    monkeypatch.setattr(run_evolution, 'MockLLMClient', lambda _: fake)
    monkeypatch.setattr(run_evolution, 'EvolutionLoop', Mock(side_effect=RuntimeError('private-marker')))
    assert run_evolution.main([]) == 1
    fake.close.assert_called_once()


def test_system_errors_are_sanitized_and_client_closed(client, monkeypatch):
    import engine.llm
    fake = Mock()
    fake.generate.side_effect = RuntimeError('private-upstream-marker')
    monkeypatch.setattr(engine.llm, 'LLMClient', lambda _: fake)
    for key, value in [('LLM_API_KEY', 'private-test-key'), ('LLM_MODEL', 'offline'), ('LLM_BASE_URL', 'https://invalid.example')]:
        monkeypatch.setenv(key, value)
    response = client.post('/api/system/test-llm')
    assert response.json()['status'] == 'error'
    assert 'private-' not in response.text
    fake.close.assert_called_once()


def test_cleanup_error_does_not_hide_terminal_failure(client, monkeypatch):
    fake = Mock()
    fake.close.side_effect = RuntimeError('private-cleanup-marker')
    monkeypatch.setattr(evolution, 'create_client', lambda _: fake)
    monkeypatch.setattr(evolution, 'EvolutionLoop', Mock(side_effect=RuntimeError('private-run-marker')))
    response = client.post('/api/evolution/runs', json={})
    result = client.get('/api/evolution/runs/' + response.json()['run_id'])
    assert result.json()['status'] == result.json()['stage'] == 'failed'
    assert 'private-' not in result.text
    fake.close.assert_called_once()


def test_cancel_pending_does_not_start_client_or_touch_other_run(client, monkeypatch):
    storage.evolution_runs.update(a=state('a'), b=state('b'))
    monkeypatch.setattr(evolution, 'create_client', lambda _: pytest.fail('cancelled job started'))
    assert client.post('/api/evolution/runs/a/cancel').json()['status'] == 'cancelling'
    evolution.run_evolution_background('a', {})
    assert storage.evolution_runs['a']['status'] == 'cancelled'
    assert storage.evolution_runs['b']['status'] == 'pending'
    assert client.post('/api/evolution/runs/missing/cancel').status_code == 404


def test_replay_returns_independent_responses():
    config = LLMConfig(provider=LLMProvider.REPLAY, base_url='replay://local', model='replay', replay_fixtures=['simple_nearest'])
    with create_client(config) as client:
        a = client.generate(GenerationRequest(prompt='offline', generation_id='a'))
        b = client.generate(GenerationRequest(prompt='offline', generation_id='b'))
    assert a.generation_id == 'a' and b.generation_id == 'b'
    assert a.metadata['call_count'] == 1 and b.metadata['call_count'] == 2


def test_cli_arguments_and_real_replay(tmp_path):
    from scripts.run_evolution import parse_args, main
    assert parse_args(['--replay', '--seed', '0']).mode == 'replay'
    assert parse_args(['--live']).mode == 'live'
    assert main(['--replay', '--seed', '0', '--gens', '1', '--candidates', '1', '--stops', '3', '--train-count', '1', '--test-count', '1', '--runs-dir', str(tmp_path)]) == 0
    import json
    saved = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert saved['status'] == 'completed'
    assert saved['test_evaluation'] is not None


def test_upstream_secrets_not_in_errors_or_repr(monkeypatch):
    config = LLMConfig(provider=LLMProvider.OPENAI, api_key='fake-sensitive-marker', base_url='https://invalid.example', model='test')
    assert 'fake-sensitive-marker' not in str(config)
    with create_client(config) as client:
        assert 'fake-sensitive-marker' not in repr(client)
        def fail(*args, **kwargs):
            response = httpx.Response(400, json={'error': {'message': 'fake-sensitive-marker'}}, request=httpx.Request('POST', 'https://invalid.example'))
            response.raise_for_status()
        monkeypatch.setattr(client.client, 'post', fail)
        with pytest.raises(RuntimeError) as exc:
            client.generate(GenerationRequest(prompt='offline'))
        assert '400' in str(exc.value) and 'fake-sensitive-marker' not in str(exc.value)


@pytest.mark.parametrize('payload', [{'temperature': 1.5}, {'seed': -1}, {'elites_kept': 11}, {'num_generations': 20, 'candidates_per_generation': 10, 'num_instances': 50, 'num_stops': 100}])
def test_evolution_limits(client, payload):
    assert client.post('/api/evolution/runs', json=payload).status_code == 422


@pytest.mark.parametrize('geometry,duration', [([[float('nan'), 1]], 1), ([[91, 1]], 1), ([[1, 1]], -1), ([[1, 1]], float('inf'))])
def test_invalid_road_geometry_is_explicit(monkeypatch, geometry, duration):
    from api.routers import routing
    mock = Mock()
    mock.__enter__ = Mock(return_value=mock)
    mock.__exit__ = Mock(return_value=False)
    mock.get_route.return_value = {'geometry': geometry, 'duration': duration}
    monkeypatch.setattr(routing, 'OSRMClient', lambda _: mock)
    points, seconds, error = routing.get_route_geometry_if_road(
        {'mode': 'road', 'instance': object(), 'depot_coords': [1, 1], 'stop_coords': [[2, 2]]}, [0, 1, 0])
    assert points is None and seconds is None and error
    mock.__exit__.assert_called_once()
