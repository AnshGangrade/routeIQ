"""Delivery acceptance gaps; all model/network responses are explicit fixtures."""
from copy import deepcopy
from dataclasses import replace
import json

import httpx
import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from engine.routing import search
from engine.routing.control import InitialControl, SearchAction
from engine.routing.validation import validate_fleet_solution
from engine.routing.trusted import TrustedPlan, WorkCounters
from engine.strategies.adaptive import AdaptiveController, ReplayController
from engine.strategies.adaptive_models import AdaptiveAction
from engine.strategies.provider import AdaptiveOllamaProvider, ProviderConfig
from tests.unit.test_adaptive_controller import problem, controlled, Scripted


@pytest.mark.parametrize('action',[
    SearchAction(action='execute'), SearchAction(operation_slice=20001),
    SearchAction(action='reorder',operators=('unknown_operator',)), SearchAction(max_moves=0),
])
def test_optimizer_rejects_invalid_controller_action_and_closes(action):
    class UntrustedController:
        max_checkpoints=1
        closed=False
        def initialize(self,*args): return InitialControl('legacy_2opt',search.SearchConfig(ils_iterations=0),100)
        def checkpoint(self,*args): return action
        def snapshot(self): return {}
        def close(self): self.closed=True
    p=problem(); before=p.model_dump(); controller=UntrustedController()
    with pytest.raises(ValueError): search.solve_hybrid(p,controller=controller,operation_budget=20000,time_limit_seconds=30)
    assert controller.closed and p.model_dump()==before


def test_forged_operator_success_is_independently_rejected(monkeypatch):
    def forged(p,routes,**kwargs):
        return TrustedPlan(tuple((0,0) for _ in routes),tuple(0. for _ in routes),0.,0.,p.fingerprint,'forged',WorkCounters(accepted_moves=1))
    monkeypatch.setitem(search.OPERATORS,'relocate',forged)
    p=problem(); before=p.distance_matrix
    result=search.solve_hybrid(p,config=search.SearchConfig(operators=('relocate',),ils_iterations=0),operation_budget=100000,time_limit_seconds=30)
    assert result.status=='failed' and result.termination_reason=='operator_error'
    assert result.final_solution.total_distance>0 and p.distance_matrix==before
    assert validate_fleet_solution(p,result.final_solution.routes).total_distance==result.final_solution.total_distance


@pytest.mark.parametrize('field',['source_fingerprint','operation_budget','final_routes_fingerprint','decision_fingerprint'])
def test_replay_rejects_tampered_evidence(field):
    original,_=controlled(); record=deepcopy(original.controller)
    record[field]=1 if field=='operation_budget' else 'tampered'
    with pytest.raises(ValueError,match='mismatch'):
        search.solve_hybrid(problem(),controller=ReplayController(record),operation_budget=20000,time_limit_seconds=30,search_seed=0)


@pytest.fixture
def api_context(monkeypatch):
    from api.main import app
    from api import storage
    from api.routers import optimization,strategies
    monkeypatch.setattr(optimization,'jobs',{})
    monkeypatch.setattr(storage,'instance_store',{})
    monkeypatch.setattr(storage,'routing_results',{})
    # Instance/router modules import these mappings; patch their references too.
    from api.routers import instances,routing,results
    for module in (instances,routing,results):
        for name in ('instance_store','routing_results'):
            if hasattr(module,name): monkeypatch.setattr(module,name,getattr(storage,name))
    monkeypatch.setattr(strategies,'check_provider',lambda _: {'available':True})
    with TestClient(app) as client: yield client,optimization,strategies,storage


@pytest.mark.parametrize('split',['validation','heldout'])
def test_api_rejects_protected_experience_before_model_creation(api_context,monkeypatch,split):
    client,opt,strategies,_=api_context
    plan=client.post('/api/instances',json={'num_stops':8,'num_drivers':2,'seed':0}).json()
    class Unreadable:
        def values(self): pytest.fail('Protected measurements must never be inspected')
    state={'status':'completed','manifest':{'config':{'case_ids':[f'{split}-n20-k3-clustered-symmetric-r0']}},'records':Unreadable()}
    monkeypatch.setattr(strategies,'snapshot',lambda _:state)
    monkeypatch.setattr(opt,'AdaptiveController',lambda *a,**k:pytest.fail('Model must not be created'))
    response=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id'],'method':'adaptive','adaptive':{'experience_job_ids':['protected']}})
    assert response.status_code==422 and 'development' in response.json()['detail'] and not opt.jobs


def test_scoped_adaptive_cancellation_reaches_terminal_without_affecting_other_job(api_context,monkeypatch):
    client,opt,_,storage=api_context
    providers=[]
    def controller(request,**kwargs):
        p=Scripted();providers.append(p);return AdaptiveController(request,provider=p,**kwargs)
    monkeypatch.setattr(opt,'AdaptiveController',controller)
    plans=[client.post('/api/instances',json={'num_stops':8,'num_drivers':2,'seed':seed}).json() for seed in (0,1)]
    requests=[opt.OptimizeRequest(instance_id=p['instance_id'],method='adaptive',adaptive={},operations=8000,seconds=30) for p in plans]
    jobs=[opt.start(r,BackgroundTasks()) for r in requests]
    assert client.post(f"/api/optimization/jobs/{jobs[0]['job_id']}/cancel").json()['status']=='cancelling'
    opt.execute(jobs[0]['job_id'],requests[0],opt.resolve(requests[0]))
    assert client.get(f"/api/optimization/jobs/{jobs[0]['job_id']}").json()['status']=='cancelled'
    assert opt.jobs[jobs[1]['job_id']]['state']['status']=='pending' and not providers
    opt.execute(jobs[1]['job_id'],requests[1],opt.resolve(requests[1]))
    result=opt.jobs[jobs[1]['job_id']]['state']['result']
    assert result['instance_id']==plans[1]['instance_id'] and providers[0].closed
    p=storage.instance_store[plans[1]['instance_id']]['problem']
    assert validate_fleet_solution(p,[d['route'] for d in result['drivers']]).total_distance==result['total_distance']
    assert (plans[0]['instance_id'],'adaptive') not in storage.routing_results


@pytest.mark.parametrize('failure',['unavailable','http_error','unfinished','oversize'])
def test_provider_failures_are_bounded_sanitized_and_never_fabricate_actions(failure):
    calls=[]
    def handle(request):
        calls.append(request)
        if failure=='unavailable': raise httpx.ConnectError('private-fixture-detail',request=request)
        if failure=='http_error': return httpx.Response(503,text='private-fixture-detail')
        if failure=='oversize': return httpx.Response(200,content=b'x'*70000)
        return httpx.Response(200,json={'done':False,'message':{'content':'{"action":"continue"}'}})
    provider=AdaptiveOllamaProvider(ProviderConfig(retries=0,timeout=1),httpx.MockTransport(handle))
    action,meta=provider.request('{}',AdaptiveAction,seed=0,seconds=1,context_tokens=4096,cancel=lambda:False)
    assert action is None and meta['error']=='provider_or_response_failure'
    assert len(calls)==1 and 'private-fixture-detail' not in json.dumps(meta)
