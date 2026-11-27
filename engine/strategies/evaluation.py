"""Raw bounded strategy measurements, distinct from any deployment guard."""
import math
import statistics
import time
from engine.evaluation.fleet_dataset import case_by_id, digest
from engine.routing.search import solve_hybrid
from engine.routing.validation import validate_fleet_solution
from engine.routing.status import COMPLETE_REASONS


def completed_evaluation(row):
    contract = row.get('execution_contract') or {}
    return (row.get('feasible') is True and row.get('independently_validated') is True
            and row.get('status') == 'completed' and row.get('termination') in COMPLETE_REASONS
            and contract.get('search_status') == 'completed' and contract.get('route_validity') == 'validated'
            and contract.get('schedule_completed') is True and not contract.get('budget_exhausted')
            and not contract.get('neighborhoods_truncated')
            and all(isinstance(row.get(k), (int,float)) and math.isfinite(row[k]) and row[k]>=0
                    for k in ('total_distance','longest_route')))


def development_panel(config):
    selected=[case_by_id(c) for c in config.case_ids]
    if any(c.split!='development' for c in selected): raise ValueError('Development only')
    return tuple((c.id,c.problem(config.search_seed)) for c in selected)


def evaluate_one(problem,strategy,config,cancel=lambda:False):
    before=problem.fingerprint; start=time.monotonic()
    row={'problem_fingerprint':before,'matrix_fingerprint':problem.matrix_fingerprint,
         'search_seed':config.search_seed,'operation_limit':config.operations_per_evaluation,
         'time_limit_seconds':config.seconds_per_evaluation,'distance_units':problem.distance_units,
         'status':'failed','feasible':False,'total_distance':None,'longest_route':None,
         'operations':0,'work_known':False,'operator_calls':0,'accepted_moves':0,'routes':None,'termination':'exception'}
    try:
        r=solve_hybrid(problem,construction_strategy=strategy.construction,config=strategy.search_config(),
            search_seed=config.search_seed,operation_budget=config.operations_per_evaluation,
            time_limit_seconds=config.seconds_per_evaluation,should_cancel=cancel,search_scope=config.search_scope)
        row.update(operations=r.operations_used,work_known=True,operator_calls=r.operator_calls,accepted_moves=r.accepted_moves)
        checked=validate_fleet_solution(problem,r.final_solution.routes)
        if (r.final_solution.problem_fingerprint != before or
                r.final_solution.total_distance != checked.total_distance or
                r.final_solution.longest_route_distance != checked.longest_route_distance or
                r.final_solution.route_distances != checked.route_distances):
            raise ValueError('Independent objective verification failed')
        # Raw global best is already guarded inside the unchanged hybrid. Do not
        # clip to an external baseline or credit selection as an improvement.
        row.update(status='failed' if r.errors or r.status=='failed' else 'completed' if r.status=='completed' else 'incomplete',
            execution_contract=r.execution_contract,
            feasible=True,independently_validated=True,search_scope=config.search_scope,
            total_distance=checked.total_distance,longest_route=checked.longest_route_distance,
            routes=r.final_solution.routes,operations=r.operations_used,operator_calls=r.operator_calls,
            accepted_moves=r.accepted_moves,termination=r.termination_reason,
            initial_distance=r.initial_solution.total_distance,
            raw_event_distances=[e.raw_candidate.total_distance if e.raw_candidate else None for e in r.events],
            raw_events=[{'stage':e.stage,'method':e.method,'status':e.status,'accepted':e.accepted,
                'raw_distance':e.raw_candidate.total_distance if e.raw_candidate else None,
                'retained_best_distance':e.best_distance} for e in r.events],
            selected_distance=r.final_solution.total_distance,
            operator_telemetry=dict(r.operator_telemetry),
            selection_policy='existing hybrid global incumbent; no external baseline clipping')
    except Exception as exc: row['error_type']=type(exc).__name__
    if problem.fingerprint != before: raise RuntimeError('Problem mutation')
    row['seconds']=time.monotonic()-start
    return row


def fitness(rows,expected):
    eligible=expected>0 and len(rows)==expected and all(completed_evaluation(r) for r in rows)
    if any('case_id' in r for r in rows): eligible &= len({r.get('case_id') for r in rows})==expected
    distances=[r['total_distance'] for r in rows] if eligible else []
    return {'mean_distance':statistics.mean(distances) if distances else None,
        'longest_driver_route':max((r['longest_route'] for r in rows if r['feasible']),default=None),
        'distance_sd':statistics.stdev(distances) if len(distances)>1 else None,
        'worst_distance':max(distances,default=None),'cases':len(rows),'expected_cases':expected,
        'completed':sum(r['status']=='completed' for r in rows),
        'incomplete':sum(r['status']=='incomplete' for r in rows),
        'failed':sum(r['status']=='failed' for r in rows),'eligible':eligible,
        'missing_cases':max(0,expected-len(rows)),'work_unavailable_cases':sum(not r.get('work_known',False) for r in rows),
        'seconds':sum(r.get('seconds',0) for r in rows),'operations':sum(r['operations'] for r in rows),
        'behavior':digest([r.get('routes') for r in rows]) if eligible else None,
        'bounded_mean_distance':statistics.mean(r['total_distance'] for r in rows) if rows and all(r.get('feasible') and r.get('total_distance') is not None for r in rows) else None,
        'policy':'completed_panel/v1'}


def rank(record):
    value=record.fitness.get('mean_distance')
    return (value if value is not None and math.isfinite(value) else math.inf,record.configuration_fingerprint)


def candidate_rankings(records):
    """Only completed panels can be recommended; bounded rows remain diagnostics."""
    bounded=sorted((r for r in records if r.fitness.get('eligible')
                    and r.fitness.get('mean_distance') is not None
                    and math.isfinite(r.fitness['mean_distance'])),key=rank)
    completed=[r for r in bounded if r.fitness.get('policy')=='completed_panel/v1' and r.fitness.get('expected_cases',0)>0
               and r.fitness.get('completed')==r.fitness['expected_cases']
               and not any(r.fitness.get(k,0) for k in ('incomplete','failed','missing_cases'))]
    return {'schema':'candidate-ranking/v2',
            'completed_only':[r.strategy_id for r in completed],
            'bounded_incumbents':[r.strategy_id for r in bounded],
            'recommended_id':completed[0].strategy_id if completed else None,
            'recommendation_kind':'completed' if completed else 'unavailable'}


def verify_completed_panel(record, config):
    """Recheck saved evidence against canonical matrices before application. No solver run."""
    if not record.evaluation_history: return False
    rows=record.evaluation_history[-1].get('rows', [])
    panel=development_panel(config)
    if len(rows)!=len(panel) or not fitness(rows,len(panel))['eligible']: return False
    for row,(case_id,problem) in zip(rows,panel):
        if (row.get('case_id')!=case_id or row.get('problem_fingerprint')!=problem.fingerprint
                or row.get('matrix_fingerprint')!=problem.matrix_fingerprint
                or row.get('distance_units')!=problem.distance_units
                or row.get('search_seed')!=config.search_seed
                or row.get('search_scope')!=config.search_scope
                or row.get('operation_limit')!=config.operations_per_evaluation
                or row.get('time_limit_seconds')!=config.seconds_per_evaluation): return False
        checked=validate_fleet_solution(problem,row['routes'])
        if checked.total_distance!=row['total_distance'] or checked.longest_route_distance!=row['longest_route']: return False
    return fitness(rows,len(panel)) == record.fitness
