"""Offline API lifecycle and CLI tests; actual trusted optimizer, no model network."""
import json
from threading import Event
from fastapi.testclient import TestClient
import pytest
from api.main import app
from api.routers import strategies
from engine.strategies import evolution
from engine.strategies.models import ExperimentConfig,StrategyConfig
from engine.strategies.provider import OfflineProvider
from engine.strategies.evaluation import evaluate_one
from engine.routing.problem import FleetProblem
from scripts.run_strategy_evolution import main


@pytest.fixture
def payload():
    return {'config':{'population_size':4,'generations':1,'max_evaluations':4,
        'operations_per_evaluation':10000,'max_total_operations':40000,'seconds_per_evaluation':20,'max_seconds':120}}


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(strategies,'ROOT',tmp_path/'jobs')
    monkeypatch.setattr(strategies,'jobs',{})
    return TestClient(app)


def test_api_offline_start_history_details_export_and_cross_run_identity(client,payload):
    response=client.post('/api/strategy-experiments',json=payload)
    assert response.status_code==200
    key=response.json()['job_id']; base=f'/api/strategy-experiments/{key}'
    status=client.get(base).json(); assert status['status']=='completed'
    assert client.get(base+'/history').json()['history']
    data=client.get(base+'/export').json(); best=data['best_id']
    assert client.get(base+'/strategies/'+best).json()['configuration_fingerprint']
    second=client.post('/api/strategy-experiments',json=payload).json()['job_id']
    assert second!=key
    assert client.get(f'/api/strategy-experiments/{second}/strategies/{best}').status_code==404
    assert client.post(base+'/resume').status_code==409
    assert client.post(base+'/cancel').json()['status']=='completed'


def test_cancel_early_terminal_and_resume(client,payload,monkeypatch):
    original=strategies.execute
    def before(job_id,request,resume):
        strategies.jobs[job_id]['cancel'].set()
        original(job_id,request,resume)
    monkeypatch.setattr(strategies,'execute',before)
    key=client.post('/api/strategy-experiments',json=payload).json()['job_id']
    base=f'/api/strategy-experiments/{key}'
    assert client.get(base).json()['status']=='cancelled'
    monkeypatch.setattr(strategies,'execute',original)
    assert client.post(base+'/resume').status_code==200
    assert client.get(base).json()['status']=='completed'


def test_api_restart_export_and_resume(client,payload,monkeypatch):
    original=strategies.execute
    def before(job_id,request,resume):
        strategies.jobs[job_id]['cancel'].set(); original(job_id,request,resume)
    monkeypatch.setattr(strategies,'execute',before)
    key=client.post('/api/strategy-experiments',json=payload).json()['job_id']
    strategies.jobs.clear()
    assert client.get(f'/api/strategy-experiments/{key}/export').json()['status']=='cancelled'
    monkeypatch.setattr(strategies,'execute',original)
    assert client.post(f'/api/strategy-experiments/{key}/resume').status_code==200


@pytest.mark.parametrize('config',[{'case_ids':['heldout-n20-k2-uniform-symmetric-r0']},
    {'max_evaluations':1000},{'population_size':32},{'operations_per_evaluation':10000000}])
def test_api_rejects_holdout_and_excessive_requests(client,config):
    assert client.post('/api/strategy-experiments',json={'config':config}).status_code==422


def test_capacity_and_cancel_one_run_does_not_touch_other(client,payload):
    ids=['a'*32,'b'*32]
    for key in ids: strategies.jobs[key]={'state':{'status':'running'},'cancel':Event()}
    assert client.post('/api/strategy-experiments',json=payload).status_code==429
    assert client.post(f'/api/strategy-experiments/{ids[0]}/cancel').status_code==200
    assert strategies.jobs[ids[0]]['cancel'].is_set()
    assert not strategies.jobs[ids[1]]['cancel'].is_set()
    assert client.post('/api/strategy-experiments/'+('c'*32)+'/cancel').status_code==404


def test_failure_sanitized_and_terminal(client,payload,monkeypatch):
    def broken(*a,**k): raise RuntimeError('private-secret-never-export')
    monkeypatch.setattr(strategies,'run_experiment',broken)
    key=client.post('/api/strategy-experiments',json=payload).json()['job_id']
    response=client.get(f'/api/strategy-experiments/{key}/export')
    assert response.json()['status']=='failed' and 'private-secret' not in response.text


def test_cli_offline_execution_and_arguments(tmp_path,payload):
    config=tmp_path/'config.json'; config.write_text(json.dumps(payload['config']))
    output=tmp_path/'run'
    assert main(['run','--config',str(config),'--output',str(output)])==0
    assert json.loads((output/'results.json').read_text())['status']=='completed'
    with pytest.raises(SystemExit): main(['run','--config',str(config),'--output',str(output)])
    with pytest.raises(SystemExit): main(['heldout','--input','missing','--output',str(tmp_path/'test')])


def test_os_lock_prevents_parallel_resume(tmp_path,payload):
    with evolution.exclusive_run(tmp_path/'r'):
        with pytest.raises(OSError): evolution.run_experiment(ExperimentConfig(**payload['config']),tmp_path/'r')


def test_small_directed_problem_matches_exhaustive_objective(payload):
    from itertools import permutations
    matrix=((0,9,2,7),(3,0,8,1),(4,6,0,5),(2,7,9,0))
    p=FleetProblem(depot_id=0,stop_ids=(1,2,3),num_drivers=1,distance_matrix=matrix,
        directed=True,distance_units='map_units',matrix_provenance={'source':'provided'})
    c=ExperimentConfig(**{**payload['config'],'operations_per_evaluation':10000})
    r=evaluate_one(p,StrategyConfig(),c)
    optimum=min(sum(matrix[a][b] for a,b in zip((0,*order,0),(0,*order,0)[1:])) for order in permutations((1,2,3)))
    assert optimum==11 and r['total_distance']==11 and r['feasible']
    assert p.distance_matrix==matrix
