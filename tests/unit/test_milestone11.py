"""Completed comparison and matched trusted-seed evidence, with no external services."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from api.main import app
from api import storage
from api.routers.results import verified, completed
from api.routers.strategies import trusted_seed_comparison
from engine.strategies.product import product_config, product_seeds
from engine.strategies.models import StrategyRecord
from engine.strategies.evaluation import development_panel, evaluate_one, fitness


@pytest.fixture
def cached():
    with TestClient(app) as client:
        plan=client.post('/api/instances',json={'num_stops':5,'num_drivers':2,'seed':0}).json()
        client.post('/api/routing/solve',json={'instance_id':plan['instance_id'],'method':'nearest_neighbor'})
        yield storage.instance_store[plan['instance_id']]['problem'],storage.routing_results[plan['instance_id'],'nearest_neighbor'],client


@pytest.mark.parametrize('corruption',['none','total','driver','longest','matrix','identity','duplicate_identity'])
def test_full_independent_metric_verification(cached,corruption):
    problem,row,client=cached
    changed=row.model_copy(deep=True)
    if corruption=='total': changed.total_distance+=1
    if corruption=='driver': changed.drivers[0].distance+=1
    if corruption=='longest': changed.longest_route_distance+=1
    if corruption=='matrix': changed.matrix_fingerprint='wrong'
    if corruption=='identity': changed.drivers[0].driver_id=9
    if corruption=='duplicate_identity': changed.drivers[0].driver_id=changed.drivers[1].driver_id
    assert verified(problem,changed)==(corruption=='none')
    storage.routing_results[row.instance_id,'nearest_neighbor']=changed
    response=client.get(f'/api/results/{row.instance_id}/comparison')
    assert response.status_code==200
    assert response.json()['comparisons'][0]['server_verified']==(corruption=='none')


@pytest.mark.parametrize('patch',[{'status':'incomplete'}, {'termination':'deadline'},
    {'budget_exhausted':True},{'neighborhoods_truncated':1},{'search_status':'cancelled'},{'schedule_completed':False}])
def test_feasibility_never_implies_completion(cached,patch):
    problem,row,_=cached
    changed=row.model_copy(update={'execution':{**row.execution,**patch}})
    assert not completed(problem,changed)


def test_trusted_seed_comparison_requires_full_matching_revalidated_panels():
    config=product_config();strategy=product_seeds()[0];rows=[]
    for case_id,problem in development_panel(config):
        row=evaluate_one(problem,strategy,config);row['case_id']=case_id;rows.append(row)
    seed=StrategyRecord(strategy_id='seed',creation_method='seed',generation=0,config=strategy,
        fitness=fitness(rows,len(rows)),evaluation_history=({'rows':rows},))
    winner=seed.model_copy(update={'strategy_id':'winner','creation_method':'llm'})
    state={'status':'completed','best_id':'winner','manifest':{'config':config.model_dump(mode='json')},
        'records':{'seed':seed.model_dump(mode='json'),'winner':winner.model_dump(mode='json')}}
    comparison=trusted_seed_comparison(state)
    assert comparison['verified'] and comparison['difference']==0 and comparison['cases']==2
    for target,field,value in [('seed','status','incomplete'),('winner','longest_route',-1),('seed','operation_limit',0),('winner','matrix_fingerprint','wrong')]:
        broken=deepcopy(state);broken['records'][target]['evaluation_history'][0]['rows'][0][field]=value
        assert trusted_seed_comparison(broken) is None
    assert state['records']['seed']['evaluation_history'][0]['rows'][0]['status']=='completed'
