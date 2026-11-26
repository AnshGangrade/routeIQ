import json
from pathlib import Path
import pytest
from engine.evaluation.controller_benchmark import (
    ControllerProtocol, balanced_panel, freeze_protocol, run, report, trial,
    shared_initial, OfflineFixture, verify_protocol,
)
from engine.evaluation.fleet_dataset import case_by_id


def config():
    return ControllerProtocol(schema_version='controller-comparison/v2',paired_ablation=True,
        development_cases=('development-n20-k3-clustered-directed-r0',),
        seeds=(0,),trials=1,operations=10000,seconds=10)


def test_balanced_panel_and_split_rejection():
    panel=[case_by_id(i) for i in balanced_panel()]
    assert len(panel)==24 and len({c.id for c in panel})==24
    assert {c.drivers for c in panel}=={1,2,3,5,10}
    for n in (20,50,100,200):
        assert {(c.distribution,c.directed) for c in panel if c.stops==n}=={
            (d,b) for d in ('uniform','clustered','mixed_density') for b in (False,True)}
    with pytest.raises(ValueError):
        ControllerProtocol(development_cases=(panel[0].id.replace('development','heldout'),))
    with pytest.raises(ValueError): ControllerProtocol(paired_ablation=True)


def test_shared_initial_changes_only_feedback_and_preserves_problem():
    c=config();p=case_by_id(c.development_cases[0]).problem(0);before=p.model_dump()
    initial=shared_initial(p,c,0,OfflineFixture)
    a=trial(p,c,'paired_static',0,OfflineFixture,initial)
    b=trial(p,c,'paired_adaptive',0,OfflineFixture,initial)
    assert a['feasible'] and b['feasible']
    assert a['shared_initial_fingerprint']==b['shared_initial_fingerprint']
    assert a['initial_routes_fingerprint']==b['initial_routes_fingerprint']
    assert a['controller']['decisions'][0]['proposal']==b['controller']['decisions'][0]['proposal']
    assert len(a['controller']['decisions'])==1
    assert any(d.get('execution',{}).get('schedule_changed') for d in b['controller']['decisions'][1:])
    assert a['operations']<=c.operations and b['operations']<=c.operations and p.model_dump()==before
    assert initial['controller']['mode']=='offline fixture' and a['controller']['actual_calls']==0


def test_failed_initial_is_not_retried_or_substituted():
    class Failed(OfflineFixture):
        def request(self,*a,**k): return None,{'calls':1,'tokens':None,'seconds':0.,'error':'timeout'}
    c=config();p=case_by_id(c.development_cases[0]).problem(0)
    initial=shared_initial(p,c,0,Failed)
    assert not initial['accepted']
    for arm in ('paired_static','paired_adaptive'):
        row=trial(p,c,arm,0,lambda:pytest.fail('must not retry'),initial)
        assert row['status']=='failed' and row['routes'] is None and row['termination']=='shared_initial_failed'


def test_saved_report_reconstruction_and_tampering(tmp_path):
    c=config();protocol=freeze_protocol(c,tmp_path/'protocol.json')
    output=tmp_path/'experiment'
    result=run(protocol,output)
    assert len(result['trials'])==6
    assert result==report(output,result['manifest'])
    assert result['shared_initial_usage']['selections']==1
    pair=next(p for p in result['summary']['paired'] if p['arm']=='paired_adaptive' and p['reference']=='paired_static')
    assert pair['bounded_incumbents']['pairs']==1
    with pytest.raises(ValueError):run(protocol,output)
    with pytest.raises(ValueError):run(protocol,tmp_path/'heldout',split='heldout')
    path=next((output/'initials').glob('*.json'))
    raw=json.loads(path.read_text());raw['seed']=99;path.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='checksum'):report(output,result['manifest'])


def test_missing_arm_remains_missing(tmp_path):
    c=config();protocol=freeze_protocol(c,tmp_path/'protocol.json');output=tmp_path/'run'
    result=run(protocol,output)
    path=next((output/'measurements').glob('*paired_adaptive*.json'))
    path.unlink()  # disposable test artifact, never historical evidence
    reconstructed=report(output,result['manifest'])
    assert next(r for r in reconstructed['rows'] if r['arm']=='paired_adaptive')['status']=='missing'
