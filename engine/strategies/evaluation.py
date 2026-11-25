"""Raw bounded strategy measurements, distinct from any deployment guard."""
import math
import statistics
import time
from engine.evaluation.fleet_dataset import case_by_id, digest
from engine.routing.search import solve_hybrid
from engine.routing.validation import validate_fleet_solution


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
            time_limit_seconds=config.seconds_per_evaluation,should_cancel=cancel)
        row.update(operations=r.operations_used,work_known=True,operator_calls=r.operator_calls,accepted_moves=r.accepted_moves)
        checked=validate_fleet_solution(problem,r.final_solution.routes)
        # Raw global best is already guarded inside the unchanged hybrid. Do not
        # clip to an external baseline or credit selection as an improvement.
        row.update(status='failed' if r.errors or r.status=='failed' else 'completed' if r.status=='completed' else 'incomplete',
            feasible=True,total_distance=checked.total_distance,longest_route=checked.longest_route_distance,
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
    eligible=len(rows)==expected and all(r['feasible'] and r['status']!='failed' and r['termination'] not in ('cancelled','cancellation_error','interrupted') for r in rows)
    distances=[r['total_distance'] for r in rows] if eligible else []
    return {'mean_distance':statistics.mean(distances) if distances else None,
        'longest_driver_route':max((r['longest_route'] for r in rows if r['feasible']),default=None),
        'distance_sd':statistics.stdev(distances) if len(distances)>1 else None,
        'worst_distance':max(distances,default=None),'cases':len(rows),'expected_cases':expected,
        'completed':sum(r['status']=='completed' for r in rows),
        'incomplete':sum(r['status']=='incomplete' for r in rows),
        'failed':sum(r['status']=='failed' for r in rows),'eligible':eligible,
        'missing_cases':expected-len(rows),'work_unavailable_cases':sum(not r.get('work_known',False) for r in rows),
        'seconds':sum(r.get('seconds',0) for r in rows),'operations':sum(r['operations'] for r in rows),
        'behavior':digest([r.get('routes') for r in rows]) if eligible else None,
        'policy':'bounded_incumbent_training; incomplete is not completed; no external baseline clipping'}


def rank(record):
    value=record.fitness.get('mean_distance')
    return (value if value is not None and math.isfinite(value) else math.inf,record.configuration_fingerprint)
