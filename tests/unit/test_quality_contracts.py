"""Quality-pass contracts, independent measured costs and explicit fixture attribution."""
import math
import pytest
from engine.routing.status import search_status
from engine.routing.search import solve_hybrid, SearchConfig
from engine.routing.validation import validate_fleet_solution
from engine.evaluation.fleet_dataset import case_by_id
from engine.strategies.adaptive import AdaptiveController, ReplayController
from engine.strategies.adaptive_models import AdaptiveRequest, AdaptiveAction
from engine.strategies.models import StrategyConfig, StrategyRecord
from engine.strategies.evaluation import candidate_rankings
from tests.unit.test_adaptive_controller import Scripted


@pytest.mark.parametrize('reason,state,exhausted',[
    ('ils_iteration_limit','completed',False),('local_search_complete','completed',False),
    ('operation_budget','incomplete',True),('deadline','incomplete',True),
    ('operator_call_limit','incomplete',True),('neighborhood_limit','incomplete',False),
    ('controller_stop','incomplete',False),('cancelled','cancelled',False),
    ('operator_error','failed',False),('unknown_legacy','unknown',False)])
def test_status_separates_validity_schedule_and_resources(reason,state,exhausted):
    result=search_status(reason)
    assert result['route_validity']=='validated'
    assert result['search_status']==state and result['budget_exhausted']==exhausted
    assert result['schedule_completed']==(state=='completed')
    assert search_status(reason,truncated=1)['search_status']!='completed'


@pytest.mark.parametrize('n,k',[(20,1),(50,3),(100,5),(200,10)])
@pytest.mark.parametrize('directed',[False,True])
def test_portfolio_reaches_feedback_across_sizes_without_omitting_baselines(n,k,directed):
    case=f'development-n{n}-k{k}-clustered-{"directed" if directed else "symmetric"}-r0'
    p=case_by_id(case).problem(0); before=p.model_dump()
    provider=Scripted([AdaptiveAction(action='reorder',operators=('cross_exchange','two_opt'),operation_slice=100),
                       AdaptiveAction(action='stop')],config=StrategyConfig(),allocation=20000)
    controller=AdaptiveController(AdaptiveRequest(limits={'max_calls':3,'max_checkpoints':2}),provider=provider)
    r=solve_hybrid(p,controller=controller,operation_budget=100000,time_limit_seconds=60,search_seed=0)
    assert len(provider.prompts)==3
    assert provider.prompts[2]['telemetry']['operator_order']==['cross_exchange','two_opt']
    assert r.termination_reason=='controller_stop' and r.operations_used<=100000
    baselines=[c for c in r.construction_candidates if c.method in ('legacy_nn','legacy_2opt')]
    assert len(baselines)==2 and all(c.status=='completed' for c in baselines)
    assert all(r.final_solution.total_distance<=c.plan.total_distance for c in baselines)
    measured=validate_fleet_solution(p,r.final_solution.routes)
    cost=sum(p.distance_matrix[a][b] for route in r.final_solution.routes if len(route)>2 for a,b in zip(route,route[1:]))
    assert math.isclose(cost,measured.total_distance) and p.model_dump()==before and provider.closed
    replay=solve_hybrid(p,controller=ReplayController(r.controller),operation_budget=100000,time_limit_seconds=60,search_seed=0)
    assert replay.final_solution.routes==r.final_solution.routes


def test_actual_ils_schedule_completion_and_zero_budget():
    p=case_by_id('development-n20-k2-uniform-symmetric-r0').problem(0)
    r=solve_hybrid(p,construction_strategy='legacy_nn',config=SearchConfig(operators=(),ils_iterations=2),time_limit_seconds=60)
    assert r.ils_iterations==2 and r.termination_reason=='ils_iteration_limit'
    assert r.status=='completed' and not r.budget_exhausted
    stopped=solve_hybrid(p,operation_budget=0)
    assert stopped.status=='stopped' and stopped.execution_contract['route_validity']=='validated'


def test_completed_and_bounded_rankings_are_separate():
    def record(key,distance,complete):
        return StrategyRecord(strategy_id=key,config=StrategyConfig(),generation=0,creation_method='seed',
            fitness={'eligible':True,'mean_distance':distance,'completed':int(complete),'incomplete':int(not complete),'expected_cases':1})
    result=candidate_rankings([record('incomplete',1,False),record('complete',10,True)])
    assert result['completed_only']==['complete']
    assert result['bounded_incumbents']==['incomplete','complete']
    assert result['recommended_id']=='complete'
    assert candidate_rankings([record('incomplete',1,False)])['recommendation_kind']=='incomplete'


@pytest.mark.parametrize('change',[{}, {'feasible':False},{'matrix_fingerprint':'wrong'},
                                 {'problem_fingerprint':'wrong'},{'distance_units':'meters'},
                                 {'total_distance':-1},{'total_distance':float('nan')},
                                 {'total_distance':1}])
def test_server_comparison_revalidates_cost_identity_units_and_zero(change):
    from api.routers.results import verified
    from api.models import RoutingResultResponse, DriverRouteResponse
    from engine.routing.problem import FleetProblem
    p=FleetProblem(depot_id=0,stop_ids=(1,),num_drivers=2,distance_matrix=((0,0),(0,0)),
        distance_units='map_units',directed=False,matrix_provenance={'source':'provided'})
    row=RoutingResultResponse(instance_id='x',method='nearest_neighbor',feasible=True,
        total_distance=0,longest_route_distance=0,computation_time=0,
        matrix_fingerprint=p.matrix_fingerprint,problem_fingerprint=p.fingerprint,distance_units='map_units',
        execution={'status':'completed'},drivers=[DriverRouteResponse(driver_id=0,route=[0,1,0],distance=0),
                                                DriverRouteResponse(driver_id=1,route=[0,0],distance=0)])
    assert verified(p,row.model_copy(update=change))== (not bool(change))


def test_zero_matrix_endpoint_reports_valid_tie_without_dividing_by_zero(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from api.routers import results
    from api.models import RoutingResultResponse,DriverRouteResponse
    from engine.routing.problem import FleetProblem
    p=FleetProblem(depot_id=0,stop_ids=(1,),num_drivers=1,distance_matrix=((0,0),(0,0)),
        distance_units='map_units',directed=False,matrix_provenance={'source':'provided'})
    row=RoutingResultResponse(instance_id='zero',method='nearest_neighbor',feasible=True,
        total_distance=0,longest_route_distance=0,computation_time=0,
        matrix_fingerprint=p.matrix_fingerprint,problem_fingerprint=p.fingerprint,distance_units='map_units',
        execution={'status':'completed'},drivers=[DriverRouteResponse(driver_id=0,route=[0,1,0],distance=0)])
    monkeypatch.setattr(results,'instance_store',{'zero':{'problem':p,'response':SimpleNamespace(num_stops=1,num_drivers=1)}})
    monkeypatch.setattr(results,'routing_results',{('zero','nearest_neighbor'):row,('zero','2opt'):row.model_copy(update={'method':'2opt'})})
    response=asyncio.run(results.get_comparison('zero'))
    assert response.comparisons[1].improvement_vs_nn==0
