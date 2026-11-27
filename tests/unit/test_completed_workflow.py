"""Product workflow with actual solver/validators and explicitly mocked Ollama HTTP."""
from copy import deepcopy
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from api.main import app
from api import storage
from api.routers import strategies, optimization
from engine.strategies.provider import OllamaProvider, ProviderConfig
from engine.strategies.product import product_config, product_seeds, application_budget
from engine.strategies.models import StrategyRecord
from engine.strategies.evaluation import development_panel, evaluate_one, fitness, verify_completed_panel, candidate_rankings
from engine.strategies.evolution import run_experiment
from engine.routing.search import solve_hybrid
from engine.routing.validation import validate_fleet_solution


def mock_provider(invalid=False):
    calls=[]
    def response(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'done':True,'message':{'content':'invalid' if invalid else json.dumps({
            'config':{'construction':'legacy_2opt','operators':['relocate' if len(calls)==1 else 'swap'],
                      'max_moves_per_operator':100000},'rationale':'Automated HTTP fixture, not live evidence'})},
            'prompt_eval_count':10,'eval_count':20})
    provider=OllamaProvider(ProviderConfig(model='qwen3:1.7b',retries=1),httpx.MockTransport(response))
    return provider,calls


@pytest.fixture
def measured():
    config=product_config(); rows=[]
    for key,problem in development_panel(config):
        row=evaluate_one(problem,product_seeds()[0],config);row['case_id']=key;rows.append(row)
    return config,rows


@pytest.mark.parametrize('change',[
    {'status':'incomplete'}, {'status':'failed'}, {'status':'cancelled'}, {'status':'interrupted'},
    {'termination':'operation_budget'},{'termination':'deadline'},{'feasible':False},
    {'independently_validated':False},{'total_distance':float('nan')}])
def test_incomplete_or_unverified_panel_cannot_qualify(measured,change):
    _,rows=measured;rows[0].update(change)
    assert not fitness(rows,2)['eligible']
    assert fitness(rows,2)['mean_distance'] is None


def test_complete_panel_revalidated_and_missing_duplicate_tampered_rejected(measured):
    config,rows=measured
    record=StrategyRecord(strategy_id='test',config=product_seeds()[0],generation=0,creation_method='seed',
        fitness=fitness(rows,2),evaluation_history=({'rows':rows},))
    assert verify_completed_panel(record,config)
    assert candidate_rankings([record])['recommended_id']=='test'
    assert not fitness(rows[:1],2)['eligible']
    assert not fitness([rows[0],rows[0]],2)['eligible']
    for field,value in [('total_distance',0),('matrix_fingerprint','wrong'),('routes',[[0,0],[0,0]])]:
        bad=deepcopy(rows);bad[0][field]=value
        candidate=record.model_copy(update={'evaluation_history':({'rows':bad},),'fitness':fitness(bad,2)})
        try: assert not verify_completed_panel(candidate,config)
        except ValueError: pass


def test_product_llm_only_complete_winner_and_provider_cleanup(tmp_path):
    provider,calls=mock_provider()
    state=run_experiment(product_config(),tmp_path/'product',provider=provider)
    assert state['status']=='completed' and state['best_id']
    assert {r['creation_method'] for r in state['records'].values()}=={'seed','llm'}
    assert len(calls)==2 and all(c['think'] is False for c in calls)
    constraints=calls[0]['format']['$defs']['StrategyConfig']['properties']
    assert constraints['construction']['enum']==['legacy_2opt','nearest_neighbor_starts']
    assert constraints['operators']['maxItems']==2 and constraints['ils_iterations']['maximum']==0
    assert ['two_opt'] not in constraints['operators']['enum']
    winner=StrategyRecord.model_validate(state['records'][state['best_id']])
    assert winner.creation_method=='llm' and verify_completed_panel(winner,product_config())
    assert provider.client.is_closed


def test_failed_model_retries_then_stops_without_random_or_seed_winner(tmp_path):
    provider,calls=mock_provider(invalid=True)
    state=run_experiment(product_config(),tmp_path/'failed',provider=provider)
    assert len(calls)==2
    assert state['status']=='failed' and state['termination']=='llm_unavailable' and state['best_id'] is None
    assert {r['creation_method'] for r in state['records'].values()}=={'seed'}
    assert provider.client.is_closed


def test_schema_valid_but_oversized_proposals_are_bounded_and_attributed(tmp_path):
    calls=[]
    def response(request):
        calls.append(request)
        return httpx.Response(200,json={'message':{'content':json.dumps({'config':{},'rationale':'Oversized fixture'})},
            'prompt_eval_count':1,'eval_count':1})
    provider=OllamaProvider(ProviderConfig(model='qwen3:1.7b'),httpx.MockTransport(response))
    state=run_experiment(product_config(),tmp_path/'oversized',provider=provider)
    assert len(calls)==3 and state['llm_calls']==6
    assert state['status']=='failed' and state['termination']=='llm_proposal_limit' and state['best_id'] is None
    assert state['rejections']['product_schedule_limit']==3
    assert all(e['source']=='llm' and e['config']['construction']=='portfolio'
        for e in state['proposal_events'] if e['outcome']=='rejected_product_schedule')
    assert {r['creation_method'] for r in state['records'].values()}=={'seed'}


def test_zero_budget_leaves_no_recommendation(tmp_path):
    provider,_=mock_provider()
    cfg=product_config().model_copy(update={'operations_per_evaluation':0})
    state=run_experiment(cfg,tmp_path/'empty',provider=provider)
    assert state['best_id'] is None and not any(r['fitness'].get('eligible') for r in state['records'].values())
    assert state['rankings']['recommended_id'] is None


def test_application_complete_publish_and_incomplete_retention(tmp_path,monkeypatch):
    monkeypatch.setattr(strategies,'ROOT',tmp_path/'api')
    monkeypatch.setattr(strategies,'jobs',{});monkeypatch.setattr(optimization,'jobs',{})
    monkeypatch.setattr(storage,'instance_store',{});monkeypatch.setattr(storage,'routing_results',{})
    from api.routers import instances,routing,results
    for module in (instances,routing,results):
        for name in ('instance_store','routing_results'):
            if hasattr(module,name): monkeypatch.setattr(module,name,getattr(storage,name))
    monkeypatch.setattr(strategies,'check_provider',lambda c:{'available':True})
    monkeypatch.setattr(strategies,'OllamaProvider',lambda config:mock_provider()[0])
    with TestClient(app) as client:
        response=client.post('/api/strategy-experiments',json={'workflow':'ai_product','mode':'ollama','arm':'llm'})
        job=response.json()['job_id'];state=client.get(f'/api/strategy-experiments/{job}/export').json()
        winner=state['best_id'];assert winner
        plan=client.post('/api/instances',json={'mode':'synthetic','num_stops':10,'num_drivers':2,'seed':0}).json()
        request={'instance_id':plan['instance_id'],'method':'strategy','strategy_job_id':job,'strategy_id':winner}
        start=client.post('/api/optimization/jobs',json=request);assert start.status_code==202,start.text
        result=client.get('/api/optimization/jobs/'+start.json()['job_id']).json()
        assert result['status']=='completed' and result['published']
        p=storage.instance_store[plan['instance_id']]['problem']
        checked=validate_fleet_solution(p,[d['route'] for d in result['result']['drivers']])
        assert checked.total_distance==result['result']['total_distance']
        assert result['request']['operations']==100000 and result['request']['seconds']==15
        previous=storage.routing_results[(plan['instance_id'],'strategy')]
        start=client.post('/api/optimization/jobs',json={**request,'operations':0,'seconds':15})
        limited=client.get('/api/optimization/jobs/'+start.json()['job_id']).json()
        assert limited['status']=='incomplete' and limited['result'] is None and not limited['published']
        assert limited['execution']['termination']=='operation_budget'
        assert storage.routing_results[(plan['instance_id'],'strategy')] is previous
        raw=strategies.jobs[job]['state']['records'][winner]
        raw['evaluation_history'][0]['rows'][0]['status']='incomplete'
        assert client.post('/api/optimization/jobs',json=request).status_code==409


@pytest.mark.parametrize('corruption',['cost','fingerprint','termination'])
def test_solver_claims_cannot_bypass_independent_publication_checks(monkeypatch,corruption):
    from dataclasses import replace
    real=optimization.solve_hybrid
    def corrupt(problem,**kwargs):
        outcome=real(problem,**kwargs)
        assert outcome.status=='completed'
        if corruption=='termination': return replace(outcome,termination_reason='deadline')
        final=replace(outcome.final_solution,**({'total_distance':0.} if corruption=='cost' else {'problem_fingerprint':'wrong'}))
        return replace(outcome,final_solution=final)
    monkeypatch.setattr(optimization,'solve_hybrid',corrupt)
    monkeypatch.setattr(optimization,'jobs',{})
    with TestClient(app) as client:
        plan=client.post('/api/instances',json={'num_stops':5,'num_drivers':2,'seed':0}).json()
        previous=client.post('/api/routing/solve',json={'instance_id':plan['instance_id'],'method':'2opt'}).json()
        start=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id'],'method':'portfolio'})
        job=client.get('/api/optimization/jobs/'+start.json()['job_id']).json()
        assert job['status']=='failed' and job['result'] is None
        assert (plan['instance_id'],'portfolio') not in storage.routing_results
        assert storage.routing_results[(plan['instance_id'],'2opt')].total_distance==previous['total_distance']


@pytest.mark.parametrize('n,k',[(20,2),(50,3),(100,5),(200,10)])
def test_size_aware_schedule_finishes_and_keeps_mandatory_baselines(n,k):
    from engine.evaluation.fleet_dataset import case_by_id
    p=case_by_id(f'development-n{n}-k{k}-clustered-directed-r0').problem(0)
    ops,seconds=application_budget(n)
    strategy=product_seeds()[0]
    result=solve_hybrid(p,construction_strategy=strategy.construction,config=strategy.search_config(),
        search_scope='best_construction',operation_budget=ops,time_limit_seconds=seconds)
    assert result.status=='completed' and result.operations_used<=ops<=500000 and seconds<=30
    assert {r.method for r in result.construction_candidates}>={'legacy_nn','legacy_2opt'}
    assert result.final_solution.total_distance==validate_fleet_solution(p,result.final_solution.routes).total_distance
