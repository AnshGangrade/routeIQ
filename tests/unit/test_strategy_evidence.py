"""Read-only evidence metrics and provider states. No live requests."""
import pytest
import httpx
from api.routers.strategies import check_provider
from engine.strategies.provider import ProviderConfig
from scripts.audit_strategy_evidence import paired, interval


def row(case, cost, status='completed'):
    return dict(case_id=case,total_distance=cost,status=status,feasible=status!='failed',termination='finished',
        problem_fingerprint=case,matrix_fingerprint=case,search_seed=0,operation_limit=10,time_limit_seconds=1,distance_units='map_units')


def test_paired_independent_arithmetic_and_missing():
    a=[row('a',8),row('b',12,'incomplete'),row('c',0),row('d',1),row('e',1,'failed')]
    b=[row('a',10),row('b',10),row('c',0),row('d',0),row('e',2),row('f',3)]
    report=paired(a,b,list('abcdef'))
    bounded=report['bounded']
    assert (bounded['pairs'],bounded['unavailable'])==(4,2)
    assert (bounded['wins'],bounded['ties'],bounded['losses'])==(1,1,2)
    assert bounded['mean_difference']==-.25
    assert bounded['mean_percentage']==0
    assert bounded['percentage_denominator']==3 and bounded['zero_reference_undefined']==1
    assert report['completed_only']['pairs']==3
    assert report['missing_llm']==['f']


def test_no_pairs_no_estimate():
    result=paired([],[],['a'])
    assert result['bounded']['mean_percentage'] is None
    assert result['bounded']['difference_bootstrap_95'] is None


def test_seeded_intervals_and_ties():
    assert interval([1,2,3])==interval([1,2,3])
    assert interval([0,0,0])==[0,0]
    assert interval([1]) is None
    assert paired([row('a',1+1e-10)],[row('a',1)],['a'])['bounded']['ties']==1


@pytest.mark.parametrize('field,value',[('search_seed',1),('matrix_fingerprint','changed'),('operation_limit',20),('time_limit_seconds',2)])
def test_reject_unpaired(field,value):
    a=row('a',1);a[field]=value
    with pytest.raises(ValueError):paired([a],[row('a',2)],['a'])


def test_reject_duplicate_and_unregistered():
    with pytest.raises(ValueError):paired([row('a',1)]*2,[],['a'])
    with pytest.raises(ValueError):paired([row('b',1)],[],['a'])


@pytest.mark.parametrize('body,status',[({'models':[{'name':'qwen3:1.7b'}]},'available'),({'models':[]},'model_missing'),({},'check_failed'),({'models':[{}]},'check_failed'),({'models':'bad'},'check_failed')])
def test_inventory_states(monkeypatch,body,status):
    client=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body)),**kw))
    result=check_provider(ProviderConfig(model='qwen3:1.7b'))
    assert result['status']==status
    assert result['available']==(status=='available')


@pytest.mark.parametrize('error,status',[(httpx.ConnectError,'unreachable'),(httpx.ReadTimeout,'check_failed')])
def test_network_states_sanitized(monkeypatch,error,status):
    client=httpx.Client
    def response(r):raise error('sensitive exception',request=r)
    monkeypatch.setattr(httpx,'Client',lambda **kw:client(transport=httpx.MockTransport(response),**kw))
    result=check_provider(ProviderConfig())
    assert result['status']==status and not result['available']
    assert 'sensitive' not in str(result)


@pytest.mark.parametrize('change',['validation_heldout','development_heldout','duplicate_seed','different_model','wrong_arms'])
def test_live_study_protocol_rejects_unpaired_or_leaking_panels(change):
    import json
    from pathlib import Path
    from scripts.run_paired_strategy_study import validate_protocol
    protocol=json.loads(Path('examples/paired-strategy-study.json').read_text(encoding='utf-8'))
    validate_protocol(protocol)
    if change=='validation_heldout':protocol['validation_cases']=[protocol['validation_cases'][0].replace('validation','heldout')]
    elif change=='development_heldout':protocol['config']['case_ids']=[protocol['config']['case_ids'][0].replace('development','heldout')]
    elif change=='duplicate_seed':protocol['seeds']=[1,1,1]
    elif change=='different_model':protocol['model']='unrequested'
    else:protocol['arm_order'][0]=['llm','llm']
    with pytest.raises(ValueError):validate_protocol(protocol)
