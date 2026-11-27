"""Offline product integration: actual solver, independent cost/coverage oracles."""
import math
from threading import Event

import numpy as np
import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient
from api.main import app
from api import storage
from api.routers import optimization, routing, strategies
from engine.strategies.models import StrategyRecord, StrategyConfig


@pytest.fixture(autouse=True)
def clean():
    storage.instance_store.clear(); storage.routing_results.clear(); optimization.jobs.clear()
    yield
    storage.instance_store.clear(); storage.routing_results.clear(); optimization.jobs.clear()


def instance(client, stops=7, drivers=3, **extra):
    response = client.post('/api/instances', json={'num_stops': stops, 'num_drivers': drivers, 'seed': 0, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def assert_measured(plan, result):
    problem = storage.instance_store[plan['instance_id']]['problem']
    assert result['matrix_fingerprint'] == problem.matrix_fingerprint
    assert result['problem_fingerprint'] == problem.fingerprint
    routes = [r['route'] for r in result['drivers']]
    assert sorted(stop for route in routes for stop in route[1:-1]) == list(problem.stop_ids)
    assert len(routes) == problem.num_drivers
    costs=[]
    for i,route in enumerate(routes):
        assert route[0] == route[-1] == problem.depot_id
        assert problem.workload.minimum_stops[i] <= len(route)-2 <= problem.workload.maximum_stops[i]
        cost = math.fsum(problem.distance_matrix[a][b] for a,b in zip(route,route[1:]))
        assert result['drivers'][i]['distance'] == pytest.approx(cost)
        costs.append(cost)
    assert result['total_distance'] == pytest.approx(sum(costs))
    assert result['longest_route_distance'] == pytest.approx(max(costs))


@pytest.mark.parametrize('method', ['portfolio', 'vnd', 'vnd_ils'])
def test_actual_hybrid_application_and_same_matrix_comparison(method):
    with TestClient(app) as client:
        plan = instance(client)
        before = storage.instance_store[plan['instance_id']]['problem'].fingerprint
        for baseline in ('nearest_neighbor', '2opt'):
            measured = client.post('/api/routing/solve', json={'instance_id':plan['instance_id'],'method':baseline}).json()
            assert_measured(plan, measured)
        started = client.post('/api/optimization/jobs', json={'instance_id':plan['instance_id'],'method':method})
        assert started.status_code == 202
        job = client.get('/api/optimization/jobs/'+started.json()['job_id']).json()
        assert job['status'] in ('completed','incomplete')
        assert_measured(plan, job['result'])
        assert job['execution']['final_distance'] <= job['execution']['initial_distance']
        assert job['execution']['constructors']
        assert storage.instance_store[plan['instance_id']]['problem'].fingerprint == before
        comparison = client.get('/api/results/'+plan['instance_id']+'/comparison').json()
        assert len(comparison['comparisons']) == 3
        assert all(r['matrix_fingerprint']==plan['matrix_fingerprint'] for r in comparison['comparisons'])
        assert all(r['drivers'] for r in comparison['comparisons'])


def test_zero_work_is_incomplete_not_an_improvement_and_more_drivers_than_stops():
    with TestClient(app) as client:
        plan = instance(client,5,8)
        started=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id'],'operations':0,'seconds':0}).json()
        job=client.get('/api/optimization/jobs/'+started['job_id']).json()
        assert job['status']=='incomplete'
        assert job['execution']['budget_exhausted']
        assert job['execution']['improvement_percent']==0
        assert job['execution']['operations']==0
        assert job['execution']['selected_source']=='ordered_feasible_seed'
        assert_measured(plan,job['result'])
        assert sum(len(r['route'])==2 for r in job['result']['drivers'])==3


def test_cancellation_is_scoped_terminal_and_does_not_publish():
    with TestClient(app) as client:
        first=instance(client); second=instance(client,6,2)
    requests=[optimization.OptimizeRequest(instance_id=p['instance_id']) for p in (first,second)]
    started=[optimization.start(r,BackgroundTasks()) for r in requests]
    optimization.cancel(started[0]['job_id'])
    assert not optimization.jobs[started[1]['job_id']]['cancel'].is_set()
    for item,req in zip(started,requests): optimization.execute(item['job_id'],req,optimization.resolve(req))
    assert optimization.status(started[0]['job_id'])['status']=='cancelled'
    assert (first['instance_id'],'vnd') not in storage.routing_results
    assert optimization.status(started[1]['job_id'])['status'] in ('completed','incomplete')
    assert optimization.cancel(started[1]['job_id'])['status'] in ('completed','incomplete')


def test_running_solver_observes_cancellation(monkeypatch):
    with TestClient(app) as client: plan=instance(client)
    req=optimization.OptimizeRequest(instance_id=plan['instance_id'])
    started=optimization.start(req,BackgroundTasks())
    real=optimization.solve_hybrid
    def cancel_inside(problem,**kwargs):
        optimization.cancel(started['job_id'])
        assert kwargs['should_cancel']()
        return real(problem,**kwargs)
    monkeypatch.setattr(optimization,'solve_hybrid',cancel_inside)
    optimization.execute(started['job_id'],req,optimization.resolve(req))
    assert optimization.status(started['job_id'])['status']=='cancelled'
    assert not storage.routing_results


@pytest.mark.parametrize('field,value', [('operations',-1),('operations',500001),('operations',True),('seconds',31),('search_seed',-1),('method','unknown')])
def test_bounds_reject_before_work(field,value):
    with TestClient(app) as client:
        plan=instance(client)
        response=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id'],field:value})
        assert response.status_code==422
        assert not optimization.jobs


def test_duplicate_active_job_and_capacity():
    with TestClient(app) as client: plan=instance(client)
    req=optimization.OptimizeRequest(instance_id=plan['instance_id'])
    optimization.start(req,BackgroundTasks())
    with pytest.raises(HTTPException) as error: optimization.start(req,BackgroundTasks())
    assert error.value.status_code==409


def test_failures_sanitized_without_claiming_success(monkeypatch):
    def fail(*args,**kwargs): raise RuntimeError('sensitive-provider-diagnostic')
    monkeypatch.setattr(optimization,'solve_hybrid',fail)
    with TestClient(app) as client:
        plan=instance(client)
        item=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id']}).json()
        response=client.get('/api/optimization/jobs/'+item['job_id'])
        assert response.json()['status']=='failed'
        assert response.json()['result'] is None
        assert 'sensitive-provider-diagnostic' not in response.text
        assert not storage.routing_results


def test_matrix_mismatch_and_stale_comparison_fail_closed():
    with TestClient(app) as client:
        plan=instance(client)
        client.post('/api/routing/solve',json={'instance_id':plan['instance_id'],'method':'nearest_neighbor'})
        key=(plan['instance_id'],'nearest_neighbor')
        storage.routing_results[key]=storage.routing_results[key].model_copy(update={'matrix_fingerprint':'other'})
        comparison=client.get('/api/results/'+plan['instance_id']+'/comparison')
        assert comparison.status_code==200
        assert comparison.json()['comparisons'][0]['server_verified'] is False
        assert comparison.json()['comparisons'][0]['improvement_vs_nn'] is None
        storage.instance_store[plan['instance_id']]['distance_matrix']=np.zeros((8,8))
        assert client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id']}).status_code==409


def test_supported_workload_and_invalid_constraints():
    with TestClient(app) as client:
        fixed={'policy':'balanced_stop_count','minimum_stops':[3,2,2],'maximum_stops':[3,2,2]}
        plan=instance(client,workload=fixed)
        assert plan['workload']==fixed
        assert plan['problem_fingerprint'] != instance(client)['problem_fingerprint']
        item=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id']}).json()
        assert_measured(plan,client.get('/api/optimization/jobs/'+item['job_id']).json()['result'])
        assert client.post('/api/instances',json={'num_stops':7,'num_drivers':3,'workload':{
            **fixed,'maximum_stops':[1,1,1]}}).status_code==422


def test_strategy_recomputed_on_each_selected_instance_and_scoped(monkeypatch):
    from engine.strategies.product import product_config, product_seeds
    from engine.strategies.evaluation import development_panel, evaluate_one, fitness
    config=product_config().model_copy(update={'proposal_policy':'historical_mixed'})
    chosen=product_seeds()[0]
    rows=[]
    for case_id,problem in development_panel(config):
        row=evaluate_one(problem,chosen,config);row['case_id']=case_id;rows.append(row)
    strategy=StrategyRecord(strategy_id='winner',generation=0,creation_method='seed',config=chosen,
        fitness=fitness(rows,len(rows)),evaluation_history=({'rows':rows},))
    assert strategy.fitness['eligible']
    monkeypatch.setattr(strategies,'snapshot',lambda job: {'status':'completed',
        'manifest':{'config':config.model_dump(mode='json')},'records':{'winner':strategy.model_dump(mode='json')}})
    with TestClient(app) as client:
        plans=[instance(client,5,2),instance(client,9,3)]
        for plan in plans:
            item=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id'],'method':'strategy',
                'strategy_job_id':'job','strategy_id':'winner'}).json()
            job=client.get('/api/optimization/jobs/'+item['job_id']).json()
            assert_measured(plan,job['result'])
            assert job['status']=='completed'
            assert job['result']['total_distance'] != strategy.fitness['mean_distance']
            assert job['execution']['strategy_fingerprint']==strategy.configuration_fingerprint
        assert client.post('/api/optimization/jobs',json={'instance_id':plans[0]['instance_id'],'method':'strategy',
            'strategy_job_id':'job','strategy_id':'other'}).status_code==404


def test_road_geometry_failure_preserves_road_matrix_without_fake_geometry(monkeypatch):
    from engine.road.models import RoadDistanceResult
    import engine.road
    matrix=np.arange(36,dtype=float).reshape(6,6)+1
    np.fill_diagonal(matrix,0)
    monkeypatch.setattr(engine.road,'create_road_distance_matrix',lambda coordinates:(matrix,RoadDistanceResult(provider='osrm',distances=matrix.tolist())))
    monkeypatch.setattr(routing,'get_route_geometry_if_road',lambda stored,route:(None,None,'Road geometry unavailable'))
    with TestClient(app) as client:
        plan=instance(client,5,2,mode='road',depot_coords=[0,0],stop_coords=[[i*.01,.01] for i in range(5)])
        item=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id']}).json()
        job=client.get('/api/optimization/jobs/'+item['job_id']).json()
        assert_measured(plan,job['result'])
        assert job['result']['distance_units']=='meters'
        assert all(r['geometry'] is None and r['duration'] is None and r['geometry_error'] for r in job['result']['drivers'])
