"""Phase 6 offline contracts, independent objectives, lifecycle and provider bounds."""
from copy import deepcopy
import json
from pathlib import Path
import random
from threading import Event
import httpx
import pytest
from pydantic import ValidationError
from engine.strategies.models import StrategyConfig,StrategyRecord,ExperimentConfig,Proposal
from engine.strategies.provider import OfflineProvider,OllamaProvider,ProviderConfig,parse_proposal
from engine.strategies.evaluation import development_panel,evaluate_one,fitness,rank
from engine.strategies.evolution import run_experiment,mutate,crossover,select_parent,survivors,hand_strategies
from engine.strategies import evolution,experiment
from engine.evaluation.fleet_dataset import digest


@pytest.fixture
def cfg():
    return ExperimentConfig(population_size=4,generations=3,max_proposals=50,max_evaluations=12,
        operations_per_evaluation=20000,max_total_operations=240000,seconds_per_evaluation=20,max_seconds=300)


@pytest.fixture(autouse=True)
def fast_software(monkeypatch):
    monkeypatch.setattr(evolution,'software_record',lambda root:{'test_source':'fixed'})
    monkeypatch.setattr(experiment,'software_record',lambda root:{'test_source':'fixed'})


@pytest.mark.parametrize('change',[
    {'operators':['exec']},{'operators':['swap','swap']},{'nn_attempts':0},{'nn_attempts':17},
    {'nn_attempts':True},{'max_operator_calls':1001},{'max_moves_per_operator':0},
    {'ils_iterations':101},{'perturbation_moves':9},{'max_diversifications':-1},
    {'search_seed':3},{'operation_budget':99999999},{'objective':'min_time'},
    {'scheduling':'alns'},{'acceptance':'annealing'},{'source_code':'print(1)'},
    {'construction':'untrusted'},{'schema_version':'other'}])
def test_schema_rejects_unsupported_or_host_owned_fields(change):
    with pytest.raises(ValidationError): StrategyConfig(**change)


def test_fingerprint_canonicalizes_inactive_knobs():
    a=StrategyConfig(operators=(),max_operator_calls=5,ils_iterations=0,perturbation_moves=8)
    b=StrategyConfig(operators=('swap',),max_operator_calls=0,ils_iterations=0)
    assert a.fingerprint==b.fingerprint
    assert StrategyConfig(operators=('swap','relocate')).fingerprint!=StrategyConfig(operators=('relocate','swap')).fingerprint
    r=StrategyRecord(strategy_id='a',config=a,creation_method='seed',generation=0)
    assert StrategyRecord.model_validate(r.model_dump()).configuration_fingerprint==a.fingerprint
    with pytest.raises(ValidationError): StrategyRecord(**{**r.model_dump(),'configuration_fingerprint':'fake'})


@pytest.mark.parametrize('text',['```json\n{}\n```','{"config":{"seed":1}}','{"config":{},"config":{}}',
    '{"config":{"nn_attempts":NaN}}','import os','{"config":{},"rationale":"x","python":"run()"}'])
def test_json_is_not_executable_or_lenient(text):
    with pytest.raises(ValueError): parse_proposal(text)


def test_json_limits_and_valid_proposal():
    assert parse_proposal('{"config":{"operators":["swap"]}}').config.operators==('swap',)
    with pytest.raises(ValueError): parse_proposal(' '*2000,1000)


def test_mutation_crossover_and_tournament_are_seeded():
    a,b=hand_strategies()[:2]
    assert mutate(a,random.Random(0))==mutate(a,random.Random(0))
    assert crossover(a,b,random.Random(0))==crossover(a,b,random.Random(0))
    records=[StrategyRecord(strategy_id=str(i),generation=0,creation_method='seed',config=c,fitness={'mean_distance':v}) for i,(c,v) in enumerate(zip(hand_strategies(),[9,4,7,2,8,6]))]
    assert rank(select_parent(records,random.Random(5)))==rank(select_parent(records,random.Random(5)))
    assert select_parent(records[:3],random.Random(0)).fitness['mean_distance']==4
    assert len({mutate(a,random.Random(i)).fingerprint for i in range(20)})>3


def test_elites_protected_and_low_distance_survive():
    records=[StrategyRecord(strategy_id=str(i),generation=0,creation_method='seed',config=c,protected=i==0,fitness={'mean_distance':v}) for i,(c,v) in enumerate(zip(hand_strategies(),[99,4,7,2,8,6]))]
    selected=survivors(records,4,2)
    assert {'0','3','1'}<={r.strategy_id for r in selected}


def test_ollama_payload_retries_bounds_and_cleanup():
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests)==1: raise httpx.ReadTimeout('sensitive body must not escape')
        return httpx.Response(200,json={'message':{'content':'{"config":{"operators":["swap"]}}'},'prompt_eval_count':5,'eval_count':7})
    p=OllamaProvider(ProviderConfig(model='test-model',temperature=.2,retries=2,max_tokens=128),httpx.MockTransport(handler))
    result,usage=p.propose('development prompt',index=0,allowance=2,seconds=10,cancel=lambda:False)
    assert result.config.operators==('swap',) and usage['calls']==2
    assert usage['tokens'] is None  # Failed attempt usage is unknown, never fabricated.
    assert requests[0]['model']=='test-model' and requests[0]['options']=={'temperature':.2,'num_predict':128}
    assert 'source_code' not in requests[0]['format']['properties']
    p.close(); assert p.client.is_closed


@pytest.mark.parametrize('response',[httpx.Response(500,text='SECRET'),httpx.Response(200,json={'message':{'content':'bad'}}),httpx.Response(200,content=b'x'*300000)])
def test_provider_failures_sanitized_and_bounded(response):
    p=OllamaProvider(ProviderConfig(retries=3),httpx.MockTransport(lambda r:response))
    result,usage=p.propose('x',index=0,allowance=1,seconds=10,cancel=lambda:False)
    assert result is None and usage['calls']==1 and 'SECRET' not in json.dumps(usage)
    p.close()


@pytest.mark.parametrize('endpoint',['https://example.com','http://user:password@localhost:11434','http://localhost/?token=x','file:///tmp/model'])
def test_provider_endpoint_never_accepts_credentials_or_remote_urls(endpoint):
    with pytest.raises(ValueError): ProviderConfig(endpoint=endpoint)


def test_provider_pre_cancel_uses_no_requests():
    p=OllamaProvider(transport=httpx.MockTransport(lambda r:pytest.fail('network call')))
    _,usage=p.propose('x',index=0,allowance=3,seconds=10,cancel=lambda:True)
    assert usage['calls']==0
    p.close()


def test_shared_matrix_and_independent_cost(cfg):
    _,problem=development_panel(cfg)[0]; before=problem.model_dump()
    r=evaluate_one(problem,StrategyConfig(),cfg.model_copy(update={"operations_per_evaluation":1000}))
    matrix=problem.distance_matrix
    actual=sum(sum(matrix[a][b] for a,b in zip(route,route[1:])) for route in r['routes'])
    assert actual==pytest.approx(r['total_distance'],rel=0,abs=1e-10) and r['operations']<=1000
    assert problem.model_dump()==before
    assert r['status']=='incomplete'  # Small explicit work cap; never relabelled.
    f=fitness([r],1); assert not f['eligible'] and f['mean_distance'] is None and f['bounded_mean_distance']==r['total_distance'] and f['incomplete']==1
    bad=deepcopy(r); bad['status']='failed'
    assert fitness([bad],1)['mean_distance'] is None
    assert fitness([r],2)['mean_distance'] is None


def signature(state):
    return [(r['config'],r['fitness'].get('mean_distance'),r['generation'],r['creation_method']) for r in state['records'].values()]


def test_deterministic_evolution_lineage_diversity_and_retention(tmp_path,cfg):
    a=run_experiment(cfg,tmp_path/'a'); b=run_experiment(cfg,tmp_path/'b')
    assert a['status']==b['status']=='completed'
    assert signature(a)==signature(b)
    assert len({r['configuration_fingerprint'] for r in a['records'].values()})==len(a['records'])
    assert a['history'][-1]['behavioral_diversity']>=1
    best=[h['best_so_far'] for h in a['history']]
    assert best==sorted(best,reverse=True)
    assert any(r['parents'] for r in a['records'].values())
    protected={k for k,r in a['records'].items() if r['protected']}
    assert all(protected<=set(h['population']) for h in a['history'])


def test_invalid_llm_continues_with_bounded_fallback(tmp_path,cfg):
    p=OfflineProvider(['not json'])
    state=run_experiment(cfg,tmp_path/'bad',provider=p)
    assert state['status']=='completed' and state['best_id']
    assert state['rejections']['llm_invalid_or_unavailable']>0
    assert state['accepted_by_source'].get('random',0)>0
    assert state['llm_calls']<=cfg.max_llm_calls


def test_duplicate_proposal_rejected(tmp_path,cfg):
    p=OfflineProvider([json.dumps({'config':StrategyConfig().model_dump(mode='json')})])
    state=run_experiment(cfg,tmp_path/'dup',provider=p)
    assert state['rejections']['duplicate']>0


@pytest.mark.parametrize('budget',[0,1000,3000])
def test_total_allocation_is_bounded(tmp_path,cfg,budget):
    c=cfg.model_copy(update={'max_total_operations':budget})
    state=run_experiment(c,tmp_path/str(budget))
    assert state['reserved_operations']<=budget and state['actual_operations']<=budget
    assert state['reserved_evaluations']<=cfg.max_evaluations


def test_cancel_resume_matches_uninterrupted_at_candidate_boundary(tmp_path,cfg):
    event=Event()
    def progress(state):
        if sum(bool(r['evaluation_history']) for r in state['records'].values())==1: event.set()
    state=run_experiment(cfg,tmp_path/'resume',cancel=event.is_set,progress=progress)
    assert state['status']=='cancelled'
    resumed=run_experiment(cfg,tmp_path/'resume',resume=True)
    uninterrupted=run_experiment(cfg,tmp_path/'full')
    assert signature(resumed)==signature(uninterrupted)
    assert resumed['reserved_evaluations']==uninterrupted['reserved_evaluations']


def test_resume_refuses_changed_protocol_and_tampered_cost(tmp_path,cfg):
    run_experiment(cfg,tmp_path/'r')
    with pytest.raises(ValueError): run_experiment(cfg.model_copy(update={'seed':1}),tmp_path/'r',resume=True)
    path=tmp_path/'r'/'checkpoint.json'; e=json.loads(path.read_text())
    next(iter(e['state']['records'].values()))['evaluation_history'][0]['rows'][0]['total_distance']=-1
    e['checksum']=digest(e['state']); path.write_text(json.dumps(e))
    with pytest.raises(ValueError,match='objective'): run_experiment(cfg,tmp_path/'r',resume=True)


def test_resume_crash_consumes_reserved_panel_without_rerun(tmp_path,cfg):
    event=Event()
    def pause(state):
        if state['in_flight']: event.set()
    run_experiment(cfg,tmp_path/'r',cancel=event.is_set,progress=pause)
    path=tmp_path/'r'/'checkpoint.json'; e=json.loads(path.read_text())
    key=e['state']['queue'][0]
    e['state']['in_flight']=key; e['state']['records'][key]['evaluation_history']=[]
    e['state']['records'][key]['fitness']={}; e['checksum']=digest(e['state']); path.write_text(json.dumps(e))
    s=run_experiment(cfg,tmp_path/'r',resume=True)
    assert s['lost_panels']==1 and s['records'][key]['fitness']['mean_distance'] is None


@pytest.mark.parametrize('split',['validation','heldout'])
def test_training_panel_rejects_non_development(split):
    with pytest.raises(ValueError): ExperimentConfig(case_ids=(f'{split}-n20-k2-uniform-symmetric-r0',))


def test_evolution_never_reads_heldout_or_executes_code(tmp_path,cfg,monkeypatch):
    import engine.evaluation.fleet_dataset as dataset
    original=dataset.cases
    def guarded(split='development',profile='full'):
        assert split=='development'
        return original(split,profile)
    monkeypatch.setattr(dataset,'cases',guarded)
    state=run_experiment(cfg,tmp_path/'r',provider=OfflineProvider(['__import__("os").system("bad")']))
    assert state['best_id']
    for path in Path('engine/strategies').glob('*.py'):
        import ast
        tree=ast.parse(path.read_text())
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('exec','eval','compile') for n in ast.walk(tree))


def test_fair_control_caps_and_accounting(tmp_path,cfg):
    result=experiment.compare(cfg,tmp_path/'compare',OfflineProvider)
    for arm,r in result['arms'].items():
        state=json.loads((tmp_path/'compare'/arm/'results.json').read_text())
        assert state['manifest']['config']==cfg.model_dump(mode='json')
        assert r['actual_operations']<=r['reserved_evaluations']*cfg.operations_per_evaluation
        assert r['reserved_evaluations']<=cfg.max_evaluations
    assert result['arms']['random']['llm_calls_actual']==result['arms']['hand']['llm_calls_actual']==0
    assert (tmp_path/'compare'/'comparison.csv').is_file()


def test_frozen_heldout_explicit_single_use_and_no_selection(tmp_path,cfg,monkeypatch):
    run_experiment(cfg,tmp_path/'run')
    frozen=tmp_path/'frozen.json'; experiment.freeze(tmp_path/'run',frozen)
    with pytest.raises(ValueError): experiment.evaluate_frozen(frozen,tmp_path/'out')
    # Keep exact locked catalog identities; stub only numerical work for offline guard test.
    def fake(problem,strategy,config,**kwargs):
        return {'status':'completed','feasible':True,'total_distance':1.,'longest_route':1.,'operations':0,
                'seconds':0.,'termination':'local_search_complete','routes':[]}
    monkeypatch.setattr(experiment,'evaluate_one',fake)
    result=experiment.evaluate_frozen(frozen,tmp_path/'out',acknowledge=True,root=tmp_path)
    assert len(result['rows'])==360 and result['split']=='heldout' and result['finished']
    copy=tmp_path/'copied.json'; copy.write_bytes(frozen.read_bytes())
    with pytest.raises(FileExistsError): experiment.evaluate_frozen(copy,tmp_path/'other',acknowledge=True,root=tmp_path)


def test_frozen_guard_rejects_source_change(tmp_path,cfg,monkeypatch):
    run_experiment(cfg,tmp_path/'run'); frozen=tmp_path/'frozen.json'; experiment.freeze(tmp_path/'run',frozen)
    monkeypatch.setattr(experiment,'software_record',lambda root:{'test_source':'changed'})
    with pytest.raises(ValueError): experiment.evaluate_frozen(frozen,tmp_path/'out',acknowledge=True)


def test_provider_closed_on_bad_resume(tmp_path,cfg):
    p=OllamaProvider(transport=httpx.MockTransport(lambda r:pytest.fail('network')))
    with pytest.raises(FileNotFoundError): run_experiment(cfg,tmp_path/'absent',provider=p,resume=True)
    assert p.client.is_closed


def test_proposals_and_llm_reservations_are_hard_caps(tmp_path,cfg):
    c=cfg.model_copy(update={'max_proposals':7,'max_llm_calls':1})
    state=run_experiment(c,tmp_path/'r',provider=OfflineProvider(['invalid']))
    assert state['proposals']<=7 and state['llm_calls']<=1
    assert sum(state['proposals_by_source'].values())<=7
    assert len(state['proposal_events'])<=7


def test_control_comparisons_distinguish_bounded_incomplete_and_zero():
    def row(value,status):
        return {'feasible':True,'status':status,'termination':'operation_budget','total_distance':value,
                'problem_fingerprint':'p','matrix_fingerprint':'m','search_seed':0,'operation_limit':100,'time_limit_seconds':1.}
    results=experiment.paired_controls({'llm':{'a':row(0,'completed'),'b':row(1,'incomplete')},
        'random':{'a':row(0,'completed'),'b':row(0,'completed')}},('a','b'))
    p=next(r for r in results if r['method']=='llm')
    assert p['bounded_training']['pairs']==2 and p['bounded_training']['losses']==1
    assert p['bounded_training']['percentage']['n']==1 and p['bounded_training']['percentage']['mean']==0
    assert p['completed_only']['pairs']==1 and p['completed_only']['ties']==1


def test_no_eligible_strategy_cannot_produce_fake_best(tmp_path,cfg,monkeypatch):
    def broken(problem,strategy,config,*args):
        return {'status':'failed','feasible':False,'total_distance':None,'longest_route':None,
                'termination':'exception','operations':0,'seconds':0}
    monkeypatch.setattr(evolution,'evaluate_one',broken)
    state=run_experiment(cfg,tmp_path/'r')
    assert state['best_id'] is None
    assert all(r['fitness']['mean_distance'] is None for r in state['records'].values() if r['evaluation_history'])


def test_pre_cancel_and_total_deadline_terminal_without_evaluation(tmp_path,cfg,monkeypatch):
    state=run_experiment(cfg,tmp_path/'cancel',cancel=lambda:True)
    assert state['status']=='cancelled' and state['reserved_evaluations']==0
    ticks=iter(range(1000))
    monkeypatch.setattr(evolution.time,'monotonic',lambda:next(ticks))
    state=run_experiment(cfg.model_copy(update={'max_seconds':.001}),tmp_path/'time')
    assert state['status']=='stopped' and state['termination']=='time_limit'
    assert state['reserved_evaluations']==0


def test_completed_checkpoint_recovers_missing_report_without_rerun(tmp_path,cfg,monkeypatch):
    a=run_experiment(cfg,tmp_path/'r'); (tmp_path/'r'/'results.json').unlink()
    monkeypatch.setattr(evolution,'evaluate_one',lambda *a:pytest.fail('rerun'))
    b=run_experiment(cfg,tmp_path/'r',resume=True)
    assert signature(a)==signature(b) and (tmp_path/'r'/'results.json').exists()


def test_provider_cancellation_between_retries():
    event=Event()
    def handler(request): event.set(); raise httpx.ReadTimeout('private')
    p=OllamaProvider(ProviderConfig(retries=3),httpx.MockTransport(handler))
    _,usage=p.propose('x',index=0,allowance=4,seconds=10,cancel=event.is_set)
    assert usage['calls']==1
    p.close()
