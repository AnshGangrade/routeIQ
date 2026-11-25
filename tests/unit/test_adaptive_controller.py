"""Offline, measured controller contracts. Scripted proposals are never live evidence."""
import asyncio
import json
import math
import time
from copy import deepcopy
from threading import Event, Timer

import httpx
import pytest
from fastapi.testclient import TestClient

from engine.evaluation.fleet_dataset import case_by_id
from engine.routing.search import solve_hybrid
from engine.routing.budget import SearchBudget
from engine.routing.validation import validate_fleet_solution
from engine.strategies.adaptive import AdaptiveController, ReplayController, ControllerUnavailable
from engine.strategies.adaptive_models import AdaptiveRequest, AdaptiveAction, InitialSelection
from engine.strategies.provider import AdaptiveOllamaProvider, ProviderConfig, parse_proposal
from engine.strategies.experience import summarize_problem, development_experience
from engine.strategies.models import StrategyConfig, StrategyRecord, ExperimentConfig
from engine.strategies.evaluation import evaluate_one


def problem(directed=False):
    return case_by_id('development-n20-k3-clustered-'+('directed' if directed else 'symmetric')+'-r0').problem(0)


class Scripted:
    mode='offline test fixture'
    def __init__(self, actions=(), config=None, allocation=100):
        self.items=[InitialSelection(config=config or StrategyConfig(construction='legacy_2opt',ils_iterations=3),operation_slice=allocation),*actions]
        self.prompts=[]; self.closed=False
    def request(self,prompt,schema,**kwargs):
        self.prompts.append(json.loads(prompt))
        item=self.items.pop(0) if self.items else AdaptiveAction(action='continue',operation_slice=100)
        return item,{'calls':1,'tokens':32,'seconds':0.,'error':None}
    def close(self): self.closed=True


def controlled(p=None, actions=(), **kwargs):
    provider=Scripted(actions)
    controller=AdaptiveController(AdaptiveRequest(limits={'max_calls':4,'max_checkpoints':3}),provider=provider)
    r=solve_hybrid(p or problem(),controller=controller,operation_budget=20000,time_limit_seconds=60,search_seed=0,**kwargs)
    return r,provider


@pytest.mark.parametrize('directed',[False,True])
def test_summary_uses_actual_problem_without_raw_locations(directed):
    p=problem(directed); s=summarize_problem(p)
    assert s['problem_fingerprint']==p.fingerprint and s['directed']==directed
    assert s['drivers']==3 and s['stops']==20
    assert s['matrix']['asymmetric_pair_fraction']==int(directed)
    assert s['geometry']['available']
    assert 'coordinates' not in s and 'distance_matrix' not in s and 'stop_ids' not in s
    assert 'capacity' in s['unsupported_constraints']


@pytest.mark.parametrize('raw',[
    {'action':'execute','code':'print(1)'},{'action':'reorder','operators':['swap','swap']},
    {'action':'reorder','operators':['three_opt']},{'action':'reorder'},
    {'action':'continue','operators':['swap']},{'action':'continue','operation_slice':0},
    {'action':'continue','operation_slice':20001},{'action':'continue','max_moves':True},
    {'action':'continue','operation_budget':1000000},{'action':'stop','route':[0,1,0]},
])
def test_finite_actions_reject_unsupported_fields(raw):
    with pytest.raises(ValueError): AdaptiveAction.model_validate(raw)


@pytest.mark.parametrize('directed',[False,True])
def test_adaptation_is_measured_bounded_independent_and_replayable(directed):
    p=problem(directed); before=p.model_dump()
    actions=[AdaptiveAction(action='reorder',operators=('cross_exchange','relocate'),operation_slice=150),
             AdaptiveAction(action='continue',operation_slice=200),AdaptiveAction(action='stop')]
    r,provider=controlled(p,actions)
    measured=validate_fleet_solution(p,r.final_solution.routes)
    assert measured.total_distance==r.final_solution.total_distance<=r.initial_solution.total_distance
    assert math.isclose(measured.total_distance,sum(sum(p.distance_matrix[a][b] for a,b in zip(route,route[1:])) for route in r.final_solution.routes))
    assert p.model_dump()==before and provider.closed
    assert r.operations_used<=20000
    feedback=provider.prompts[1]['telemetry']
    assert feedback['operations']>0 and feedback['remaining_operations']==20000-feedback['operations']
    assert feedback['best_distance']<=r.initial_solution.total_distance
    assert any(v['attempts']>0 for v in feedback['operator_statistics'].values())
    for v in feedback['operator_statistics'].values():
        assert v['attempts']==v['accepted_improvements']+v['rejected_moves']
    assert provider.prompts[2]['telemetry']['operator_order']==['cross_exchange','relocate']
    replay=solve_hybrid(p,controller=ReplayController(r.controller),operation_budget=20000,time_limit_seconds=60,search_seed=0)
    assert replay.final_solution.routes==r.final_solution.routes
    assert replay.operations_used==r.operations_used
    assert replay.controller['mode']=='recorded decision replay'


def test_counters_show_actual_improvement_without_weakening_incumbent():
    r,_=controlled(actions=[AdaptiveAction(action='reorder',operators=('cross_exchange','two_opt'),operation_slice=20000)])
    assert r.final_solution.total_distance < r.initial_solution.total_distance
    assert sum(v['distance_reduction'] for _,v in r.operator_telemetry)>0
    assert all(a.best_distance>=b.best_distance for a,b in zip(r.events,r.events[1:]))


def test_invalid_feedback_keeps_valid_incumbent_and_records_nonrandom_fallback():
    r,provider=controlled(actions=[None])
    decisions=r.controller['decisions']
    assert decisions[1]['source']=='deterministic fallback'
    assert not decisions[1]['accepted']
    assert 'random proposal' not in json.dumps(decisions)
    validate_fleet_solution(problem(),r.final_solution.routes)
    assert provider.closed


def test_initial_failure_never_starts_fake_ai_search():
    provider=Scripted();provider.items=[None]
    controller=AdaptiveController(provider=provider)
    with pytest.raises(ControllerUnavailable): solve_hybrid(problem(),controller=controller)
    assert provider.closed and controller.state['decisions'][0]['accepted'] is False


def test_zero_budget_closes_provider_without_request():
    provider=Scripted();controller=AdaptiveController(provider=provider)
    with pytest.raises(ControllerUnavailable): solve_hybrid(problem(),controller=controller,operation_budget=0)
    assert not provider.prompts and provider.closed


def test_token_and_call_limits_do_not_grant_extra_work():
    provider=Scripted()
    request=AdaptiveRequest(limits={'max_calls':8,'max_reserved_tokens':8960,'max_checkpoints':3})
    c=AdaptiveController(request,provider=provider)
    r=solve_hybrid(problem(),controller=c,operation_budget=8000,time_limit_seconds=60)
    assert r.controller['calls']==1 and len(provider.prompts)==1
    assert r.controller['reserved_tokens']==8960
    assert r.operations_used<=8000
    assert any(d.get('request',{}).get('error')=='model_token_limit' for d in r.controller['decisions'])


def test_diversification_remains_host_bounded_and_cannot_replace_best():
    r,_=controlled(actions=[AdaptiveAction(action='diversify',operation_slice=100)]*3)
    assert r.diversifications<=3 and r.ils_iterations<=3
    assert r.final_solution.total_distance<=r.initial_solution.total_distance


def test_initial_sweep_on_directed_problem_fails_closed():
    provider=Scripted(config=StrategyConfig(construction='contiguous_sweep'))
    with pytest.raises(ControllerUnavailable): solve_hybrid(problem(True),controller=AdaptiveController(provider=provider))
    assert provider.closed


def test_real_provider_serialization_seed_zero_schema_and_tokens():
    captured=[]
    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200,json={'done':True,'message':{'content':'{"action":"continue"}'},'prompt_eval_count':40,'eval_count':8})
    config=ProviderConfig(model='qwen3:1.7b',temperature=.2,timeout=1,retries=0,max_tokens=64)
    provider=AdaptiveOllamaProvider(config,httpx.MockTransport(handle))
    proposal,meta=provider.request('{}',AdaptiveAction,seed=0,seconds=1,context_tokens=4096,cancel=lambda:False)
    assert proposal.action=='continue' and meta['tokens']==48
    payload=captured[0]
    assert payload['model']=='qwen3:1.7b' and payload['options']=={'temperature':.2,'seed':0,'num_predict':64,'num_ctx':4096}
    assert payload['format']==AdaptiveAction.model_json_schema()


@pytest.mark.parametrize('content',['{"action":"stop","action":"continue"}','{"action":"continue","max_moves":NaN}','```json\n{}\n```'])
def test_controller_json_rejects_duplicate_nonfinite_and_fenced(content):
    with pytest.raises(ValueError): parse_proposal(content,schema=AdaptiveAction)


@pytest.mark.parametrize('cancelled',[False,True])
def test_total_deadline_and_cancellation_close_slow_response(cancelled):
    closed=[]; signal=Event()
    class Slow(httpx.AsyncByteStream):
        async def __aiter__(self):
            await asyncio.sleep(5)
            yield b'{}'
        async def aclose(self): closed.append(True)
    provider=AdaptiveOllamaProvider(ProviderConfig(timeout=1,retries=0),httpx.MockTransport(lambda r:httpx.Response(200,stream=Slow())))
    timer=Timer(.05,signal.set) if cancelled else None
    if timer:timer.start()
    start=time.monotonic()
    proposal,meta=provider.request('{}',AdaptiveAction,seed=0,seconds=.2,context_tokens=4096,cancel=signal.is_set)
    if timer:timer.join()
    assert proposal is None and meta['error']==('cancelled' if cancelled else 'timeout')
    assert time.monotonic()-start<1 and closed


def historical():
    cfg=ExperimentConfig(case_ids=('development-n20-k3-clustered-symmetric-r0',),operations_per_evaluation=1000,seconds_per_evaluation=60)
    strategy=StrategyConfig();p=problem()
    row=evaluate_one(p,strategy,cfg);row['case_id']=cfg.case_ids[0]
    record=StrategyRecord(strategy_id='a',generation=0,config=strategy,creation_method='seed',evaluation_history=({'rows':[row]},))
    return {'status':'completed','manifest':{'config':cfg.model_dump(mode='json')},'records':{'a':record.model_dump(mode='json')}}


def test_experience_revalidates_development_and_never_sends_routes_or_rationale():
    state=historical()
    state['records']['a']['evaluation_history'][0]['rows'][0].pop('operator_telemetry',None)
    data=development_experience([state],problem())
    assert data and data[0]['split']=='development'
    assert data[0]['per_operator_efficiency'] is None
    assert not any(k in json.dumps(data) for k in ('rationale','routes','raw_events','coordinates'))
    state['records']['a']['evaluation_history'][0]['rows'][0]['total_distance']+=1
    with pytest.raises(ValueError): development_experience([state],problem())


def test_new_development_records_provide_measured_operator_efficiency_and_failures():
    state=historical();data=development_experience([state],problem())
    assert data[0]['per_operator_efficiency'] is not None
    row=state['records']['a']['evaluation_history'][0]['rows'][0]
    row.update(status='failed',feasible=False,total_distance=None,routes=None)
    failed=development_experience([state],problem())
    assert failed[0]['status']=='failed' and failed[0]['distance'] is None


def test_cancellation_at_checkpoint_preserves_valid_best_and_closes_provider():
    signal=Event()
    provider=Scripted()
    original=provider.request
    def request(prompt,schema,**kw):
        result=original(prompt,schema,**kw)
        if schema is AdaptiveAction:signal.set()
        return result
    provider.request=request
    r=solve_hybrid(problem(),controller=AdaptiveController(provider=provider),operation_budget=20000,
                   time_limit_seconds=60,should_cancel=signal.is_set)
    assert r.termination_reason=='cancelled' and provider.closed
    assert r.final_solution.total_distance<=r.initial_solution.total_distance
    validate_fleet_solution(problem(),r.final_solution.routes)


def test_replay_rejects_changed_seed():
    r,_=controlled()
    with pytest.raises(ValueError,match='seed'):
        solve_hybrid(problem(),controller=ReplayController(r.controller),search_seed=5)


@pytest.mark.parametrize('split',['validation','heldout'])
def test_non_development_experience_is_rejected_before_rows_are_read(split):
    state=historical();state['manifest']['config']['case_ids']=[f'{split}-n20-k3-clustered-symmetric-r0']
    state['records']=None
    with pytest.raises(ValueError,match='development'): development_experience([state],problem())


def test_actual_api_adaptive_application_and_unavailable_provider(monkeypatch):
    from api.main import app
    from api import storage
    from api.routers import optimization,strategies
    optimization.jobs.clear();storage.instance_store.clear();storage.routing_results.clear()
    with TestClient(app) as client:
        plan=client.post('/api/instances',json={'num_stops':8,'num_drivers':2,'seed':0}).json()
        request={'instance_id':plan['instance_id'],'method':'adaptive','adaptive':{},'seconds':30}
        monkeypatch.setattr(strategies,'check_provider',lambda c:{'available':False,'message':'Local Ollama is unreachable.'})
        assert client.post('/api/optimization/jobs',json=request).status_code==503
        assert not optimization.jobs
        monkeypatch.setattr(strategies,'check_provider',lambda c:{'available':True})
        original=optimization.AdaptiveController
        monkeypatch.setattr(optimization,'AdaptiveController',lambda request,**kw:original(request,provider=Scripted(),**kw))
        response=client.post('/api/optimization/jobs',json=request)
        assert response.status_code==202,response.text
        job=client.get('/api/optimization/jobs/'+response.json()['job_id']).json()
        assert job['status'] in ('completed','incomplete'),job
        result=job['result'];p=storage.instance_store[plan['instance_id']]['problem']
        checked=validate_fleet_solution(p,[d['route'] for d in result['drivers']])
        assert result['total_distance']==checked.total_distance
        assert result['problem_fingerprint']==p.fingerprint
        assert result['execution']['controller']['mode']=='offline test fixture'
        assert any(r['method']=='adaptive' for r in client.get('/api/results/'+plan['instance_id']+'/comparison').json()['comparisons'])
    optimization.jobs.clear();storage.instance_store.clear();storage.routing_results.clear()
