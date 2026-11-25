import json
from pathlib import Path
import pytest

from engine.evaluation import controller_benchmark as cb
from engine.evaluation.controller_reporting import summarize, ARMS
from engine.evaluation.fleet_dataset import case_by_id, digest


@pytest.fixture
def protocol(tmp_path,monkeypatch):
    monkeypatch.setattr(cb,'provenance',lambda:{'source':'test-source'})
    monkeypatch.setattr(cb,'ROOT',tmp_path)
    config=cb.ControllerProtocol(development_cases=('development-n20-k2-uniform-symmetric-r0',),seeds=(0,),trials=2,operations=2000,seconds=10)
    saved=cb.freeze_protocol(config,tmp_path/'protocol.json')
    return config,saved


def test_shared_problem_seeds_budgets_and_matrix_immutability(protocol,tmp_path,monkeypatch):
    config,saved=protocol; calls=[]; original=cb.solve_hybrid
    def observed(problem,**kwargs):
        before=problem.distance_matrix
        result=original(problem,**kwargs)
        assert problem.distance_matrix==before
        calls.append((id(problem),problem.fingerprint,problem.matrix_fingerprint,kwargs['search_seed'],kwargs['operation_budget'],kwargs['time_limit_seconds']))
        return result
    monkeypatch.setattr(cb,'solve_hybrid',observed)
    result=cb.run(saved,tmp_path/'run')
    assert len(calls)==8
    assert len({r[:3] for r in calls})==1
    assert {r[3] for r in calls}=={0,1000003}
    assert all(r[4]==2000 and 0<r[5]<=10 for r in calls)
    assert len(result['trials'])==8 and len(result['rows'])==4
    assert all(r['feasible'] for r in result['rows'])
    assert not any(r['winner_llm_initial'] or r['winner_llm_checkpoint'] for r in result['rows'])


def test_reproducible_offline_trials_and_reports(protocol,tmp_path):
    _,saved=protocol
    a=cb.run(saved,tmp_path/'a'); b=cb.run(saved,tmp_path/'b')
    assert [(r['routes'],r['operations'],r['status']) for r in a['trials']]==[(r['routes'],r['operations'],r['status']) for r in b['trials']]
    assert cb.report(tmp_path/'a',a['manifest'])==a
    assert 'offline fixture' in (tmp_path/'a/report.md').read_text()
    assert len((tmp_path/'a/results.csv').read_text().splitlines())==5
    with pytest.raises(ValueError): cb.run(saved,tmp_path/'a')


def test_schema_split_seed_and_frozen_source_guards(protocol,tmp_path,monkeypatch):
    _,saved=protocol
    for patch in ({'development_cases':('heldout-n20-k2-uniform-symmetric-r0',)}, {'seeds':(True,)}, {'seeds':(0,0)}):
        with pytest.raises(ValueError): cb.ControllerProtocol(**patch)
    with pytest.raises(ValueError,match='Held-out'): cb.run(saved,tmp_path/'heldout',split='heldout')
    monkeypatch.setattr(cb,'provenance',lambda:{'source':'changed'})
    with pytest.raises(ValueError,match='Frozen'): cb.run(saved,tmp_path/'changed')


def test_validation_requires_matching_development_and_is_single_use(protocol,tmp_path):
    _,saved=protocol
    with pytest.raises(ValueError): cb.run(saved,tmp_path/'v',split='validation')
    dev=cb.run(saved,tmp_path/'dev')
    validation=cb.run(saved,tmp_path/'validation',split='validation',development=tmp_path/'dev')
    assert all(r['case_id'].startswith('validation-') for r in validation['rows'])
    assert {r['problem_fingerprint'] for r in dev['rows']}.isdisjoint(r['problem_fingerprint'] for r in validation['rows'])
    with pytest.raises(FileExistsError): cb.run(saved,tmp_path/'again',split='validation',development=tmp_path/'dev')


def test_missing_checkpoints_counted_without_reexecution(protocol,tmp_path,monkeypatch):
    _,saved=protocol
    result=cb.run(saved,tmp_path/'run')
    path=next((tmp_path/'run/measurements').glob('*hybrid--0.json')); path.unlink()
    monkeypatch.setattr(cb,'solve_hybrid',lambda *a,**k:pytest.fail('Audit must never execute'))
    recovered=cb.report(tmp_path/'run',result['manifest'])
    assert next(r for r in recovered['rows'] if r['arm']=='hybrid')['status']=='missing'
    assert recovered['summary']['arms']['hybrid']['counts']['missing']==1


def test_invalid_saved_cost_and_seed_rejected(protocol,tmp_path):
    _,saved=protocol
    result=cb.run(saved,tmp_path/'run')
    path=next((tmp_path/'run/measurements').glob('*hybrid--0.json'))
    envelope=json.loads(path.read_text()); original=json.loads(path.read_text())
    for key,value in [('total_distance',1),('trial_seed',99)]:
        envelope=json.loads(json.dumps(original)); envelope['measurement'][key]=value
        envelope['checksum']=digest(envelope['measurement']); path.write_text(json.dumps(envelope))
        with pytest.raises(ValueError): cb.report(tmp_path/'run',result['manifest'])


def test_failed_initial_model_does_not_substitute_random(protocol):
    config,_=protocol
    class Invalid(cb.OfflineFixture):
        def request(self,*a,**k): return None,{'calls':1,'tokens':None,'seconds':.1,'error':'invalid_response'}
    row=cb.trial(case_by_id(config.development_cases[0]).problem(0),config,'adaptive_llm',0,Invalid)
    assert row['status']=='failed' and not row['feasible'] and row['routes'] is None
    assert row['controller']['actual_calls']==1 and not row['controller']['usage_known']


def test_static_has_only_initial_selection_adaptive_has_feedback(protocol):
    config,_=protocol
    config=cb.ControllerProtocol.model_validate({**config.model_dump(),'operations':20000})
    problem=case_by_id(config.development_cases[0]).problem(0)
    static=cb.trial(problem,config,'static_llm',0,cb.OfflineFixture)
    adaptive=cb.trial(problem,config,'adaptive_llm',0,cb.OfflineFixture)
    assert len(static['controller']['decisions'])==1
    assert len(adaptive['controller']['decisions'])>1
    assert all(d['source']!='LLM proposal' for d in adaptive['controller']['decisions'])


def metric_row(arm,cost,status='completed',case='c',seed=0):
    return {'case_id':case,'seed':seed,'arm':arm,'stops':20,'drivers':2,'distribution':'uniform','directed':False,
        'status':status,'feasible':status not in ('failed','missing'),'total_distance':cost,
        'problem_fingerprint':'p','matrix_fingerprint':'m','allocation':{},'seconds':1.,'operations':10,
        'provider_seconds':0.,'model_calls':0,'reported_tokens':0,'unknown_token_trials':0,'unknown_work_trials':0,
        'winner_llm_initial':False,'winner_llm_checkpoint':False}


def test_paired_metrics_zero_ties_regressions_and_exclusion_denominators():
    rows=[]
    for i,(base,value,status) in enumerate([(100,80,'completed'),(100,120,'completed'),(0,0,'completed'),(0,1,'completed'),(100,50,'incomplete'),(100,None,'failed'),(100,None,'missing')]):
        rows.extend([metric_row('hybrid',base,case=str(i)),metric_row('adaptive_llm',value,status,case=str(i))])
    pair=next(p for p in summarize(rows)['paired'] if p['arm']=='adaptive_llm' and p['reference']=='hybrid')
    complete=pair['completed_only']
    assert complete['pairs']==4 and complete['percentage_pairs']==3
    assert (complete['wins'],complete['ties'],complete['losses'])==(1,1,2)
    assert complete['mean_percent']==0 and complete['median_percent']==0 and complete['worst_percent']==-20
    assert pair['excluded']=={'missing':1,'failed':1,'incomplete':1}
    assert pair['bounded_incumbents']['pairs']==5
    assert pair['by_characteristic']['stops']['20']['pairs']==4


def test_seed_replications_not_counted_as_independent_instances():
    rows=[metric_row(arm,cost,seed=seed) for seed in range(3) for arm,cost in [('hybrid',100),('static_llm',80)]]
    pair=next(p for p in summarize(rows)['paired'] if p['arm']=='static_llm' and p['reference']=='hybrid')
    assert pair['completed_only']['pairs']==3 and pair['completed_only']['independent_cases']==1
    assert pair['completed_only']['case_mean_dispersion']['mean_ci95'] is None
    rows[-1]['matrix_fingerprint']='wrong'
    with pytest.raises(ValueError,match='Unmatched'): summarize(rows)


def test_cli_freeze_audit_and_heldout_unavailable(protocol,tmp_path):
    from scripts.run_controller_benchmark import main
    _,saved=protocol
    cb.run(saved,tmp_path/'run')
    assert main(['audit','--input',str(tmp_path/'run'),'--output',str(tmp_path/'audit')])==0
    assert main(['audit','--input',str(tmp_path/'run'),'--output',str(tmp_path/'audit')])==2
    with pytest.raises(SystemExit): main(['run','--split','heldout','--output',str(tmp_path/'heldout')])


def test_winner_attribution_uses_selected_trial_not_any_participation(protocol):
    config,_=protocol; case=case_by_id(config.development_cases[0]); problem=case.problem(0)
    row=cb.trial(problem,config,'hybrid',0,cb.OfflineFixture)
    row.update(trial=0,controller={'decisions':[{'stage':'initial','source':'LLM proposal','accepted':True},
        {'stage':'checkpoint','source':'LLM proposal','accepted':True,'execution':{'status':'not_applied'},'proposal':{'action':'diversify'}}]})
    winner={**row,'trial':1,'total_distance':row['total_distance']-1,'controller':None}
    outcome=cb.aggregate([row,winner],config,case,0,'adaptive_llm',problem)
    assert not outcome['winner_llm_initial'] and not outcome['winner_llm_checkpoint']
    outcome=cb.aggregate([row],config,case,0,'adaptive_llm',problem)
    assert outcome['winner_llm_initial'] and not outcome['winner_llm_checkpoint'] and not outcome['winner_llm_changed_schedule']


def test_zero_operation_limit_prevents_model_request(protocol):
    config,_=protocol
    config=cb.ControllerProtocol.model_validate({**config.model_dump(),'operations':0})
    class Forbidden(cb.OfflineFixture):
        def request(self,*a,**k): pytest.fail('Model must not run after budget exhaustion')
    row=cb.trial(case_by_id(config.development_cases[0]).problem(0),config,'adaptive_llm',0,Forbidden)
    assert row['status']=='failed' and row['controller']['actual_calls']==0
