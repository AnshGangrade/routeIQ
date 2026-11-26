"""Bounded declarative evolution with durable candidate-boundary checkpoints."""
from collections import Counter
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import random
import statistics
import time
import uuid
from .models import StrategyConfig, StrategyRecord, ExperimentConfig, Proposal
from .provider import OfflineProvider
from .evaluation import development_panel, evaluate_one, fitness, rank, candidate_rankings
from engine.evaluation.fleet_dataset import digest
from .protocol import software_record
from engine.routing.validation import validate_fleet_solution


def hand_strategies():
    return [StrategyConfig(), StrategyConfig(ils_iterations=5),
            StrategyConfig(operators=('two_opt',)),
            StrategyConfig(construction='cheapest_insertion'),
            StrategyConfig(operators=tuple(reversed(StrategyConfig().operators))),
            StrategyConfig(construction='nearest_neighbor_starts',nn_attempts=8)]


def random_strategy(rng):
    ops=list(StrategyConfig().operators); rng.shuffle(ops)
    return StrategyConfig(construction=rng.choice(['portfolio','legacy_2opt','nearest_neighbor_starts','cheapest_insertion','contiguous_sweep']),
        operators=tuple(ops[:rng.randint(1,6)]),nn_attempts=rng.choice([1,2,4,8]),
        max_operator_calls=rng.choice([100,250,500,1000]),max_moves_per_operator=rng.choice([1000,5000,10000]),
        ils_iterations=rng.choice([0,2,5,8]),perturbation_moves=rng.randint(1,4),max_diversifications=rng.choice([0,1,3]))


def mutate(config,rng):
    values=config.model_dump(); other=random_strategy(rng).model_dump()
    keys=['construction','operators','nn_attempts','max_operator_calls','max_moves_per_operator','ils_iterations','perturbation_moves','max_diversifications']
    key=rng.choice(keys); values[key]=other[key]
    return StrategyConfig.model_validate(values)


def crossover(left,right,rng):
    a,b=left.model_dump(),right.model_dump()
    return StrategyConfig.model_validate({k:a[k] if rng.random()<.5 else b[k] for k in a})


def select_parent(population,rng):
    return min(rng.sample(population,min(3,len(population))),key=rank)


def survivors(records,size,elites):
    ordered=sorted(records,key=rank)
    protected=[r for r in ordered if r.protected]
    chosen={r.strategy_id:r for r in protected}
    for r in ordered[:elites]: chosen[r.strategy_id]=r
    for r in ordered:
        if len(chosen)>=size: break
        chosen[r.strategy_id]=r
    return list(chosen.values())[:size]


def atomic_json(path,value):
    path=Path(path); temp=path.with_suffix('.tmp')
    with temp.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,allow_nan=False,separators=(',',':')); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp,path)


def manifest(config,arm,panel,provider,root):
    return {'schema':'strategy-run/v1','arm':arm,'config':config.model_dump(mode='json'),
        'panel':[{'case_id':i,'problem_fingerprint':p.fingerprint,'matrix_fingerprint':p.matrix_fingerprint} for i,p in panel],
        'software':software_record(root),'provider_mode':provider.mode,
        'offline_fixture_fingerprint':digest(provider.responses) if isinstance(provider,OfflineProvider) else None,
        'provider_config':provider.config.model_dump(mode='json') if hasattr(provider,'config') else None}


def prompt_for(parents,state):
    # Only development fitness is present in this state. Never read benchmark artifacts.
    return json.dumps({'task':'Propose ONE JSON routing strategy. No code. Minimize fleet distance.',
        'schema':Proposal.model_json_schema(),'semantics':'Fixed restart VND; mandatory legacy constructors; host owns seeds and budgets.',
        'parents':[{'config':p.config.model_dump(mode='json'),'development':p.fitness} for p in parents],
        'best_development_fitness':state['records'].get(state['best_id'],{}).get('fitness'),
        'failures':state['rejections'],'diversity':state['history'][-1] if state['history'] else {},
        'resource_limits':state['manifest']['config']},allow_nan=False)


def _run_experiment(config,output,*,arm='llm',provider=None,resume=False,cancel=lambda:False,progress=None,root=None):
    if arm not in ('llm','random','hand'): raise ValueError('Unknown arm')
    provider=provider or OfflineProvider(); root=Path(root or Path(__file__).resolve().parents[2])
    output=Path(output); panel=development_panel(config)
    registered=manifest(config,arm,panel,provider,root)
    rng=random.Random(config.seed); started=time.monotonic(); prior_elapsed=0.
    if resume:
        envelope=json.loads((output/'checkpoint.json').read_text(encoding='utf-8'))
        state=envelope['state']
        if envelope['checksum']!=digest(state) or state['manifest']!=registered:
            raise ValueError('Checkpoint checksum, source or protocol mismatch')
        def tuples(v): return tuple(tuples(x) for x in v) if isinstance(v,list) else v
        rng.setstate(tuples(state['rng']))
        prior_elapsed=state['elapsed_seconds']
        records={k:StrategyRecord.model_validate(v) for k,v in state['records'].items()}
        for key,r in records.items():
            if key!=r.strategy_id or any(p not in records for p in r.parents): raise ValueError('Checkpoint lineage mismatch')
            for evaluation in r.evaluation_history:
                rows=evaluation['rows']
                if len(rows)>len(panel): raise ValueError('Checkpoint panel length')
                for row,(case_id,problem) in zip(rows,panel):
                    if (row['case_id']!=case_id or row['problem_fingerprint']!=problem.fingerprint
                            or row['matrix_fingerprint']!=problem.matrix_fingerprint
                            or row['search_seed']!=config.search_seed
                            or row['operation_limit']!=config.operations_per_evaluation
                            or row['time_limit_seconds']!=config.seconds_per_evaluation
                            or row['status'] not in ('completed','incomplete','failed')
                            or not 0<=row['operations']<=config.operations_per_evaluation
                            or not math.isfinite(row['seconds']) or row['seconds']<0):
                        raise ValueError('Checkpoint evaluation input mismatch')
                    if row['feasible']:
                        checked=validate_fleet_solution(problem,row['routes'])
                        if checked.total_distance!=row['total_distance'] or checked.longest_route_distance!=row['longest_route']:
                            raise ValueError('Checkpoint objective mismatch')
                if r.fitness!=fitness(rows,len(panel)): raise ValueError('Checkpoint fitness mismatch')
        if len({r.configuration_fingerprint for r in records.values()}) != len(records): raise ValueError('Duplicate checkpoint configurations')
        if state['reserved_evaluations']>config.max_evaluations or state['reserved_operations']>config.max_total_operations:
            raise ValueError('Checkpoint budget mismatch')
        # A process crash may lose a reserved panel. Never silently rerun or score it.
        if state.get('in_flight'):
            key=state['in_flight']; r=records[key]
            records[key]=r.model_copy(update={'evaluation_history':({'rows':[],'status':'interrupted'},), 'fitness':fitness([],len(panel))})
            state['lost_panels']+=1; state['in_flight']=None
            prior_elapsed+=state.get('in_flight_seconds',0.)
        if state.get('in_flight_llm_seconds'):
            prior_elapsed+=state['in_flight_llm_seconds']
            state['in_flight_llm_seconds']=0.
        if state['status']=='completed':
            results_path=output/'results.json'
            if results_path.exists() and digest(json.loads(results_path.read_text()))!=digest(state):
                raise ValueError('Completed report differs from checkpoint')
            if not results_path.exists(): atomic_json(results_path,state)
            return state
    else:
        output.mkdir(parents=True,exist_ok=False)
        records={}
        state={'experiment_id':uuid.uuid4().hex,'manifest':registered,'status':'running','termination':None,
            'generation':0,'population':[],'queue':[],'records':{},'history':[],'best_id':None,
            'proposals':0,'rejections':{},'accepted_by_source':{},'llm_calls':0,'llm_tokens':0,
            'proposals_by_source':{},'proposal_events':[],'fallback_pending':False,
            'provider_usage':[],'generation_seconds':0.,'evaluation_seconds':0.,'elapsed_seconds':0.,
            'reserved_evaluations':0,'reserved_operations':0,'actual_operations':0,'in_flight':None,
            'lost_panels':0,'stagnation':0,'improvements_by_source':{},'selection_policy':'min mean bounded development distance; tournament 3; protected seeds + elites'}

    def elapsed(): return prior_elapsed+time.monotonic()-started
    def stopped(): return cancel() or elapsed()>=config.max_seconds
    def save():
        state['elapsed_seconds']=elapsed(); state['rng']=rng.getstate()
        state['records']={k:v.model_dump(mode='json') for k,v in records.items()}
        state['rankings']=candidate_rankings(records.values())
        atomic_json(output/'checkpoint.json',{'state':state,'checksum':digest(state)})
        if progress: progress(json.loads(json.dumps(state)))
    def reject(reason): state['rejections'][reason]=state['rejections'].get(reason,0)+1
    def admit(cfg,source,parents=(),rationale='',protected=False):
        state['proposals_by_source'][source]=state['proposals_by_source'].get(source,0)+1
        event={'source':source,'generation':state['generation'],'fingerprint':cfg.fingerprint,'outcome':'duplicate'}
        state['proposal_events'].append(event)
        if any(r.configuration_fingerprint==cfg.fingerprint for r in records.values()): reject('duplicate'); return None
        key=f"{state['experiment_id']}-{len(records):04d}-{cfg.fingerprint[:12]}"
        records[key]=StrategyRecord(strategy_id=key,parents=tuple(p.strategy_id for p in parents),generation=state['generation'],
            config=cfg,rationale=rationale,creation_method=source,protected=protected)
        state['accepted_by_source'][source]=state['accepted_by_source'].get(source,0)+1
        event.update(outcome='accepted',strategy_id=key)
        return key
    def propose():
        number=state['proposals']; state['proposals']+=1
        if state['fallback_pending']:
            state['fallback_pending']=False
            return admit(random_strategy(rng),'random')
        parents=[records[k] for k in state['population']]
        if state['generation']==0:
            seeds=hand_strategies()
            if number < min(config.population_size, len(seeds) if arm=='hand' else 4):
                return admit(seeds[number],'seed',rationale='Host-authored seed',protected=number<2)
            return admit(random_strategy(rng),'random')
        if arm=='random' or not parents: return admit(random_strategy(rng),'random')
        a,b=select_parent(parents,rng),select_parent(parents,rng)
        if number%3==0 and state['llm_calls']<config.max_llm_calls:
            index=state['llm_calls']
            allowance=min(config.max_llm_calls-index,getattr(getattr(provider,'config',None),'retries',0)+1)
            state['llm_calls']+=allowance  # Crash-safe reservation, including retries.
            state['in_flight_llm_seconds']=min(config.max_seconds-elapsed(),getattr(getattr(provider,'config',None),'timeout',0)*allowance)
            save()
            proposal,usage=provider.propose(prompt_for((a,b),state),index=index,
                allowance=allowance,seconds=max(0.,config.max_seconds-elapsed()),cancel=cancel)
            state['provider_usage'].append(usage)
            state['in_flight_llm_seconds']=0.
            state['llm_tokens']=None if usage['tokens'] is None or state['llm_tokens'] is None else state['llm_tokens']+usage['tokens']
            if proposal is None:
                reject('llm_invalid_or_unavailable'); state['fallback_pending']=True
                state['proposals_by_source']['llm']=state['proposals_by_source'].get('llm',0)+1
                state['proposal_events'].append({'source':'llm','generation':state['generation'],'outcome':'invalid'})
                return None
            return admit(proposal.config,'llm',(a,b),proposal.rationale)
        if number%3==1: return admit(mutate(a.config,rng),'mutation',(a,))
        if number%3==2: return admit(crossover(a.config,b.config,rng),'crossover',(a,b))
        return admit(random_strategy(rng),'random')

    state['status']='running'; state['termination']=None
    try:
        while state['generation']<config.generations:
            if stopped(): state['termination']='cancelled' if cancel() else 'time_limit'; break
            # Persist the entire proposal queue before evaluation; resume consumes it.
            if not state['queue']:
                t=time.monotonic()
                target=(min(config.population_size,len(hand_strategies())) if arm=='hand' else
                        config.population_size if state['generation']==0 else config.population_size-config.elites)
                while len(state['queue'])<target and state['proposals']<config.max_proposals and not stopped():
                    key=propose()
                    if key: state['queue'].append(key)
                state['generation_seconds']+=time.monotonic()-t; save()
                if not state['queue']: state['termination']='proposal_limit'; break
            for key in state['queue']:
                r=records[key]
                if r.evaluation_history: continue
                if stopped(): break
                count=len(panel); allocation=count*config.operations_per_evaluation
                if state['reserved_evaluations']+count>config.max_evaluations or state['reserved_operations']+allocation>config.max_total_operations:
                    state['termination']='evaluation_budget'; break
                # Reserve worst-case whole-panel work before invoking any solver.
                state['reserved_evaluations']+=count; state['reserved_operations']+=allocation
                state['in_flight_seconds']=min(config.max_seconds-elapsed(),count*config.seconds_per_evaluation)
                state['in_flight']=key; save(); rows=[]
                for case_id,problem in panel:
                    if stopped(): break
                    row=evaluate_one(problem,r.config,config,stopped); row['case_id']=case_id; rows.append(row)
                f=fitness(rows,len(panel))
                records[key]=r.model_copy(update={'evaluation_history':({'rows':rows,'status':'measured'},),'fitness':f})
                state['actual_operations']+=f['operations']; state['evaluation_seconds']+=f['seconds']
                old=records.get(state['best_id'])
                if f['eligible'] and (old is None or rank(records[key])<rank(old)):
                    # Ties may replace identity deterministically, but are not gains.
                    if old and f['mean_distance']<old.fitness['mean_distance']:
                        source=r.creation_method
                        state['improvements_by_source'][source]=state['improvements_by_source'].get(source,0)+old.fitness['mean_distance']-f['mean_distance']
                    state['best_id']=key
                state['in_flight']=None; save()
            if state['termination'] or stopped(): break
            evaluated=[r for r in records.values() if r.evaluation_history]
            selected=survivors(evaluated,config.population_size,config.elites)
            state['population']=[r.strategy_id for r in selected]
            scores=[r.fitness['mean_distance'] for r in selected if r.fitness.get('eligible')]
            best=records[state['best_id']].fitness['mean_distance'] if state['best_id'] else None
            previous=state['history'][-1]['best_so_far'] if state['history'] else None
            state['stagnation']=state['stagnation']+1 if previous is not None and best>=previous else 0
            state['history'].append({'generation':state['generation'],'best_so_far':best,
                'fitness_min':min(scores,default=None),'fitness_max':max(scores,default=None),
                'fitness_mean':statistics.mean(scores) if scores else None,'unique_configurations':len(records),
                'behavioral_diversity':len({r.fitness['behavior'] for r in selected if r.fitness.get('eligible')}),
                'population':state['population'][:],'stagnation':state['stagnation'],
                'duplicate_rate':state['rejections'].get('duplicate',0)/max(1,state['proposals']),
                'accepted_by_source':dict(state['accepted_by_source'])})
            state['generation']+=1; state['queue']=[]; save()
            if arm=='hand': state['termination']='fixed_hand_portfolio_finished'; break
        if stopped(): state['termination']='cancelled' if cancel() else 'time_limit'
        state['status']='cancelled' if state['termination']=='cancelled' else 'stopped' if state['termination'] in ('time_limit','proposal_limit','evaluation_budget') else 'completed'
        state['termination']=state['termination'] or 'generation_limit'
        if state['status']=='completed' and state['best_id'] is None:
            state.update(status='failed',termination='no_valid_strategy')
    except Exception as exc:
        state.update(status='failed',termination='experiment_failure',error_type=type(exc).__name__)
    finally:
        save()
    atomic_json(output/'results.json',state)
    return state


@contextmanager
def exclusive_run(output):
    """OS lock released on process death; no stale PID deletion or duplicate resume."""
    path=Path(output); path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_name(path.name+'.lock').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0: stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try: yield
        finally:
            stream.seek(0)
            if os.name=='nt': msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def run_experiment(config,output,*,provider=None,**kwargs):
    provider=provider or OfflineProvider()
    try:
        with exclusive_run(output):
            return _run_experiment(config,output,provider=provider,**kwargs)
    finally:
        provider.close()
