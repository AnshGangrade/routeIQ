"""Aggregate features and an explicit, revalidated development-only experience view.

No directory scanning, held-out reads, free-form rationales, raw coordinates or
route arrays enter prompts. Old records have event counts, not move-level work.
"""
import math
import statistics
from .models import StrategyRecord
from engine.evaluation.fleet_dataset import case_by_id
from engine.routing.validation import validate_fleet_solution
from engine.routing.search import OPERATORS


def summarize_problem(problem):
    n=problem.n_stops
    matrix=problem.distance_matrix
    distances=[v for i,row in enumerate(matrix) for j,v in enumerate(row) if i!=j]
    mean=statistics.fmean(distances) if distances else 0.
    pairs=[(matrix[i][j],matrix[j][i]) for i in range(len(matrix)) for j in range(i)]
    nearest=[min(matrix[i][j] for j in range(1,n+1) if j!=i) for i in range(1,n+1)] if n>1 else []
    geometry={'available':False}
    if problem.coordinates and n:
        points=problem.coordinates[1:]
        xs,ys=zip(*points)
        width,height=max(xs)-min(xs),max(ys)-min(ys)
        units='coordinate_units'
        if problem.coordinate_system=='lon_lat':
            # Spread only, never used for objective costs. Dateline boxes are not estimated.
            if width>180:
                width=height=None
            else:
                width*=111.32*abs(math.cos(math.radians(statistics.fmean(ys))))
                height*=111.32
            units='approximate_km'
        area=width*height if width is not None else None
        bins=[0]*16
        for x,y in points:
            col=min(3,int((x-min(xs))/(max(xs)-min(xs))*4)) if max(xs)>min(xs) else 0
            row=min(3,int((y-min(ys))/(max(ys)-min(ys))*4)) if max(ys)>min(ys) else 0
            bins[row*4+col]+=1
        geometry={'available':True,'coordinate_system':problem.coordinate_system,'spread_units':units,
                  'width':width,'height':height,'stops_per_box_area':n/area if area else None,
                  'occupied_grid_cells':sum(v>0 for v in bins),'largest_cell_fraction':max(bins)/n,
                  'clustering_note':'4x4 bounding-box occupancy proxy, not a fitted cluster count'}
    return {'schema':'problem-summary/v1','problem_fingerprint':problem.fingerprint,
        'matrix_fingerprint':problem.matrix_fingerprint,'stops':n,'drivers':problem.num_drivers,
        'distance_units':problem.distance_units,'matrix_source':problem.matrix_provenance.source,
        'directed':problem.directed,'objective':problem.objective.model_dump(mode='json'),
        'workload':{'policy':problem.workload.policy,'minimum':min(problem.workload.minimum_stops),
                    'maximum':max(problem.workload.maximum_stops),
                    'fixed_driver_slots':sum(a==b for a,b in zip(problem.workload.minimum_stops,problem.workload.maximum_stops)),
                    'empty_routes_allowed':True},
        'constraints':['exact stop coverage','depot return','balanced stop counts'],
        'unsupported_constraints':['capacity','time windows','service times'],
        'matrix':{'minimum':min(distances,default=0.),'maximum':max(distances,default=0.),'mean':mean,
                  'coefficient_of_variation':statistics.pstdev(distances)/mean if mean else 0.,
                  'asymmetric_pair_fraction':sum(a!=b for a,b in pairs)/len(pairs) if pairs else 0.,
                  'mean_pair_asymmetry':statistics.fmean(abs(a-b) for a,b in pairs)/mean if pairs and mean else 0.,
                  'nearest_stop_to_mean_ratio':statistics.fmean(nearest)/mean if nearest and mean else None},
        'geometry':geometry}


def development_experience(states, target, maximum=8):
    """Import only selected terminal development snapshots, rechecking every used row.

    Archive metrics are historical observations, not a matched experiment or proof
    of transfer. Their original budgets and completion states remain attached.
    """
    selected=[]
    for state in states:
        manifest=state['manifest']
        ids=manifest['config']['case_ids']
        if not 1<=len(ids)<=12 or len(set(ids))!=len(ids): raise ValueError('Experience panel limit')
        cases=[case_by_id(i) for i in ids]
        if not cases or any(c.split!='development' for c in cases):
            raise ValueError('Experience accepts development records only')
        if state['status'] not in ('completed','stopped'):
            raise ValueError('Experience requires a terminal experiment')
        seed=manifest['config']['search_seed']
        problems={c.id:c.problem(seed) for c in cases}
        for raw in list(state.get('records',{}).values())[:16]:
            record=StrategyRecord.model_validate(raw)
            for evaluation in record.evaluation_history[-1:]:
                for row in evaluation.get('rows',[]):
                    if row['case_id'] not in problems: raise ValueError('Unexpected experience case')
                    p=problems[row['case_id']]
                    if row['problem_fingerprint']!=p.fingerprint or row['matrix_fingerprint']!=p.matrix_fingerprint:
                        raise ValueError('Experience problem mismatch')
                    if row.get('status') not in ('completed','incomplete','failed'): raise ValueError('Unknown experience status')
                    measured=None
                    if row.get('feasible'):
                        measured=validate_fleet_solution(p,row['routes'])
                        if measured.total_distance!=row['total_distance']: raise ValueError('Experience cost mismatch')
                    if measured is None and row['status']!='failed': raise ValueError('Unvalidated experience result')
                    counters=None
                    if row.get('operator_telemetry') is not None:
                        counters={}
                        for operator,values in row['operator_telemetry'].items():
                            if operator not in OPERATORS:
                                raise ValueError('Unknown historical operator')
                            clean={k:values[k] for k in ('calls','attempts','accepted_improvements','rejected_moves','operations','distance_reduction','failures')}
                            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in clean.values()):
                                raise ValueError('Invalid historical counters')
                            if clean['attempts']!=clean['accepted_improvements']+clean['rejected_moves']: raise ValueError('Inconsistent historical counters')
                            clean['improvement_per_operation']=clean['distance_reduction']/clean['operations'] if clean['operations'] else None
                            counters[operator]=clean
                        if sum(v['calls'] for v in counters.values())!=row['operator_calls']: raise ValueError('Historical call mismatch')
                        if sum(v['operations'] for v in counters.values())>row['operations']: raise ValueError('Historical work mismatch')
                    # Event distances cannot independently establish which internal moves were rejected.
                    selected.append({'split':'development','case_id':row['case_id'],
                        'stops':p.n_stops,'drivers':p.num_drivers,'directed':p.directed,
                        'distribution':next(c.distribution for c in cases if c.id==row['case_id']),
                        'configuration':record.config.model_dump(mode='json'),
                        'configuration_fingerprint':record.configuration_fingerprint,
                        'source':record.creation_method,'status':row['status'],
                        'distance':measured.total_distance if measured and row['status']!='failed' else None,'distance_units':p.distance_units,
                        'operations':row.get('operations'),'operation_limit':row.get('operation_limit'),
                        'seconds':row.get('seconds'),'time_limit_seconds':row.get('time_limit_seconds'),
                        'operator_calls':row.get('operator_calls'),'accepted_moves':row.get('accepted_moves'),
                        'per_operator_efficiency':counters,'stagnation':None,
                        'limitation':'Recorded host counters when available; old records lack per-operator work. No checkpoint stagnation was recorded by fixed-strategy experiments.'})
    selected.sort(key=lambda r:(r['directed']!=target.directed,abs(r['stops']-target.n_stops),
                                abs(r['drivers']-target.num_drivers),r['case_id'],r['configuration_fingerprint']))
    return selected[:maximum]
