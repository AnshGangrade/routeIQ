"""Append-only matched trials around the existing hybrid/controller implementation."""
import csv
import json
import math
import os
from pathlib import Path
import random
import time
from copy import deepcopy
from pydantic import Field, StrictInt, model_validator

from engine.strategies.models import StrictModel, StrategyConfig
from engine.strategies.adaptive_models import AdaptiveRequest, InitialSelection, AdaptiveAction
from engine.strategies.adaptive import AdaptiveController
from engine.strategies.evolution import random_strategy
from engine.strategies.experience import summarize_problem
from engine.strategies.provider import AdaptiveOllamaProvider
from engine.routing.control import InitialControl, SearchAction
from engine.routing.search import solve_hybrid, SearchConfig
from engine.routing.validation import validate_fleet_solution
from .fleet_dataset import case_by_id, digest, DATASET_VERSION
from .fleet_benchmark import software_record
from .controller_reporting import ARMS, ABLATION_ARMS, summarize
from engine.routing.budget import SearchBudget

ROOT = Path(__file__).resolve().parents[2]


class ControllerProtocol(StrictModel):
    schema_version: str = 'controller-comparison/v1'
    paired_ablation: bool = False
    model_digest: str | None = None
    development_cases: tuple[str, ...] = (
        'development-n20-k1-uniform-symmetric-r0',
        'development-n50-k3-clustered-directed-r1',
        'development-n100-k5-mixed_density-symmetric-r2',
        'development-n200-k10-uniform-directed-r0')
    seeds: tuple[StrictInt, ...] = (0, 1, 2)
    trials: int = Field(2, strict=True, ge=1, le=8)
    operations: int = Field(20000, strict=True, ge=0, le=500000)
    seconds: float = Field(8., gt=0, le=30)
    adaptive: AdaptiveRequest = AdaptiveRequest(limits={'max_calls':3,'max_checkpoints':2,'max_model_seconds':6.})

    @model_validator(mode='after')
    def valid_panel(self):
        if self.schema_version not in ('controller-comparison/v1','controller-comparison/v2'): raise ValueError('Unknown protocol version')
        if self.paired_ablation and self.schema_version!='controller-comparison/v2': raise ValueError('Paired ablation requires v2')
        if not 1 <= len(self.development_cases) <= (120 if self.schema_version.endswith('/v2') else 12) or len(set(self.development_cases)) != len(self.development_cases):
            raise ValueError('Invalid unique development panel size')
        if any(case_by_id(c).split != 'development' for c in self.development_cases): raise ValueError('Development cases only')
        if not 1 <= len(self.seeds) <= 10 or len(set(self.seeds)) != len(self.seeds) or any(type(s) is not int or not 0<=s<2**32 for s in self.seeds):
            raise ValueError('Unique integer seeds required')
        if self.adaptive.experience_job_ids: raise ValueError('Experience disabled in this controlled protocol')
        return self

    @property
    def arms(self): return (*ARMS,*ABLATION_ARMS) if self.paired_ablation else ARMS


def balanced_panel():
    """24 independent cells: each size x distribution x direction once.

    Driver counts rotate deterministically through all five supported counts;
    this is not a full driver-count factorial (the existing full suite is 360).
    """
    from .fleet_dataset import SIZES, DISTRIBUTIONS, DRIVERS, Case
    return tuple(Case('development',n,DRIVERS[(i*6+j*2+d)%5],distribution,bool(d),0).id
                 for i,n in enumerate(SIZES) for j,distribution in enumerate(DISTRIBUTIONS) for d in (0,1))


def save_new(path, value):
    """No replace/rewrite: a failed write remains evidence, never auto-repaired."""
    path = Path(path)
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, allow_nan=False, indent=2)
        f.flush(); os.fsync(f.fileno())


def provenance():
    return {**software_record(ROOT), 'entrypoint': digest((ROOT/'scripts/run_controller_benchmark.py').read_text(encoding='utf-8'))}


def freeze_protocol(config, path):
    body = {'schema':'frozen-controller-protocol/v1','config':config.model_dump(mode='json'),
        'dataset':DATASET_VERSION,'software':provenance(), 'arms':list(config.arms),
        'panels':{split:[c.replace('development-',split+'-',1) for c in config.development_cases]
                  for split in ('development','validation','heldout')},
        'rules':{'selection':'lowest independently validated distance across identical trial slots; failed trials keep arm incomplete',
            'primary':'completed-only paired results; incomplete incumbents separate',
            'budget':'same per-trial caps, no redistribution; model latency consumes solver deadline',
            'order':'seeded shuffled arm order for each case/seed; sequential execution',
            'heldout':'execution disabled until separate reviewed final-evaluation implementation'}}
    saved = {**body,'fingerprint':digest(body)}
    save_new(path,saved)
    return saved


def verify_protocol(saved):
    body={k:v for k,v in saved.items() if k!='fingerprint'}
    if saved.get('fingerprint')!=digest(body) or saved.get('software')!=provenance() or saved.get('dataset')!=DATASET_VERSION:
        raise ValueError('Frozen protocol, source or environment differs')
    config=ControllerProtocol.model_validate(saved['config'])
    if saved['arms']!=list(config.arms): raise ValueError('Arm mismatch')
    for split in ('development','validation','heldout'):
        if saved['panels'][split]!=[c.replace('development-',split+'-',1) for c in config.development_cases]:
            raise ValueError('Panel mismatch')
    return config


class FixedController:
    """Same checkpoint schedule, fixed random/LLM selection; never fake model calls."""
    def __init__(self, inner=None, config=None, checkpoints=2):
        self.inner, self.config, self.max_checkpoints = inner, config, checkpoints
        self.allocation=10000
    def initialize(self, problem, budget, seed):
        if self.inner:
            choice=self.inner.initialize(problem,budget,seed)
        else:
            choice=InitialControl(self.config.construction,self.config.search_config(),self.allocation)
        self.allocation=choice.operation_slice
        return choice
    def checkpoint(self, telemetry, budget):
        return SearchAction(operation_slice=self.allocation)
    def snapshot(self):
        return self.inner.snapshot() if self.inner else {'mode':'random proposal','configuration':self.config.model_dump(mode='json'),'decisions':[]}
    def close(self):
        if self.inner: self.inner.close()


class OfflineFixture:
    mode='offline fixture'
    def request(self, prompt, schema, **kwargs):
        proposal=InitialSelection(config=StrategyConfig(ils_iterations=2),operation_slice=100) if schema is InitialSelection else AdaptiveAction(action='reorder',operators=('cross_exchange','two_opt'),operation_slice=100)
        return proposal,{'calls':0,'tokens':0,'seconds':0.,'error':None}
    def close(self): pass


def shared_initial(problem, config, seed, provider_factory):
    """One proposal for both ablation arms. Failure is evidence, never resampled."""
    started=time.monotonic()
    controller=AdaptiveController(config.adaptive,provider=provider_factory())
    value={'problem_fingerprint':problem.fingerprint,'matrix_fingerprint':problem.matrix_fingerprint,
           'seed':seed,'accepted':False}
    try:
        controller.initialize(problem,SearchBudget(config.operations,config.seconds),seed)
        value['accepted']=True
    except Exception as exc:
        value['error_type']=type(exc).__name__
    finally:
        value['controller']=controller.snapshot()
        value['seconds']=time.monotonic()-started
        controller.close()
    return {**value,'fingerprint':digest(value)}


class SharedInitialController(AdaptiveController):
    def __init__(self, request, saved, provider):
        super().__init__(request,provider=provider)
        self.saved=saved

    def initialize(self, problem, budget, seed):
        if not self.saved['accepted'] or self.saved['problem_fingerprint']!=problem.fingerprint or self.saved['seed']!=seed:
            raise ValueError('Invalid shared initial selection')
        self.seed=seed
        self.state=deepcopy(self.saved['controller'])
        # Initial work/token reservations constrain both policies; actual usage is
        # recorded once in the shared artifact, not double-counted in arm totals.
        self.state.update(actual_calls=0,reported_tokens=0,usage_known=True,
            shared_initial_fingerprint=self.saved['fingerprint'],
            shared_initial_seconds=self.saved['seconds'])
        initial=InitialSelection.model_validate(self.state['decisions'][0]['proposal'])
        return InitialControl(initial.config.construction,initial.config.search_config(),initial.operation_slice)


def trial(problem, config, arm, seed, provider_factory, initial=None):
    if arm not in config.arms: raise ValueError('Unknown protocol arm')
    started=time.monotonic(); controller=None
    row={'status':'failed','feasible':False,'total_distance':None,'longest_route':None,'routes':None,
         'operations':0,'work_known':False,'operator_calls':0,'accepted_moves':0,'termination':'exception','controller':None}
    try:
        kwargs={}
        initial_charge=0.
        if arm in ABLATION_ARMS:
            if initial is None: raise ValueError('Shared initial required')
            row['shared_initial_fingerprint']=initial['fingerprint']
            row['shared_initial_charge_seconds']=initial['seconds']
            if not initial['accepted']:
                row['termination']='shared_initial_failed'
                return row
            inner=SharedInitialController(config.adaptive,initial,provider_factory())
            controller=inner if arm=='paired_adaptive' else FixedController(inner=inner,checkpoints=config.adaptive.limits.max_checkpoints)
            initial_charge=initial['seconds']
        elif arm in ('static_llm','adaptive_llm'):
            inner=AdaptiveController(config.adaptive,provider=provider_factory())
            controller=inner if arm=='adaptive_llm' else FixedController(inner=inner,checkpoints=config.adaptive.limits.max_checkpoints)
        elif arm=='random':
            rng=random.Random(seed); rejected=[]
            for _ in range(8):
                chosen=random_strategy(rng)
                if chosen.construction!='contiguous_sweep' or not problem.directed: break
                rejected.append(chosen.model_dump(mode='json'))
            row['rejected_random_proposals']=rejected
            if chosen.construction=='contiguous_sweep' and problem.directed:
                row.update(termination='inapplicable_random_proposal',proposal=chosen.model_dump(mode='json'))
                return row
            controller=FixedController(config=chosen,checkpoints=config.adaptive.limits.max_checkpoints)
        else:
            kwargs={'config':SearchConfig(),'construction_strategy':'portfolio'}
        remaining=max(0.,config.seconds-initial_charge-(time.monotonic()-started))
        outcome=solve_hybrid(problem,search_seed=seed,operation_budget=config.operations,time_limit_seconds=remaining,
                             controller=controller,**kwargs)
        measured=validate_fleet_solution(problem,outcome.final_solution.routes)
        indices={node:i for i,node in enumerate(problem.node_ids)}
        independent=sum(problem.distance_matrix[indices[a]][indices[b]]
                        for route in outcome.final_solution.routes if len(route)>2 for a,b in zip(route,route[1:]))
        if abs(independent-measured.total_distance)>1e-8: raise ValueError('Independent cost mismatch')
        row.update(status='failed' if outcome.errors or outcome.status=='failed' else 'completed' if outcome.status=='completed' else 'incomplete',
            execution_contract=outcome.execution_contract,
            feasible=True,total_distance=measured.total_distance,longest_route=measured.longest_route_distance,
            routes=[list(r) for r in outcome.final_solution.routes],operations=outcome.operations_used,work_known=True,
            operator_calls=outcome.operator_calls,accepted_moves=outcome.accepted_moves,termination=outcome.termination_reason,
            budget_exhausted=outcome.budget_exhausted,controller=outcome.controller,
            operator_telemetry=dict(outcome.operator_telemetry),selected_source=outcome.final_solution.method,
            initial_distance=outcome.initial_solution.total_distance,post_construction_gain=outcome.initial_solution.total_distance-measured.total_distance)
        if arm in ABLATION_ARMS:
            row['initial_routes_fingerprint']=digest(outcome.initial_solution.routes)
            row['controller']['model_seconds']=max(0.,row['controller']['model_seconds']-initial['controller']['model_seconds'])
    except Exception as exc:
        row['error_type']=type(exc).__name__
    finally:
        if controller:
            if row['controller'] is None: row['controller']=controller.snapshot()
            controller.close()
        row['seconds']=time.monotonic()-started
        row['deadline_overrun']=row['seconds']>config.seconds
        if initial is not None:
            row['charged_seconds']=row['seconds']+initial['seconds']
            row['deadline_overrun']=row['charged_seconds']>config.seconds
    return row


def aggregate(rows, config, case, seed, arm, problem):
    valid=[r for r in rows if r['feasible'] and r['status'] in ('completed','incomplete')]
    winner=min(valid,key=lambda r:r['total_distance']) if valid else None
    complete=len(rows)==config.trials and all(r['status']=='completed' for r in rows)
    status='missing' if len(rows)<config.trials else 'completed' if complete else 'incomplete' if winner else 'failed'
    traces=[r.get('controller') or {} for r in rows]
    decisions=(winner.get('controller') or {}).get('decisions',[]) if winner else []
    result={'case_id':case.id,'seed':seed,'arm':arm,'stops':case.stops,'drivers':case.drivers,'distribution':case.distribution,
        'directed':case.directed,'problem_fingerprint':problem.fingerprint,'matrix_fingerprint':problem.matrix_fingerprint,
        'allocation':{'trials':config.trials,'operations_per_trial':config.operations,'seconds_per_trial':config.seconds,
                      'model_limits_per_trial':config.adaptive.limits.model_dump(mode='json')},
        'status':status,'feasible':bool(winner),'total_distance':winner['total_distance'] if winner else None,
        'longest_route':winner['longest_route'] if winner else None,'winner_trial':winner['trial'] if winner else None,
        'winner_selected_source':winner.get('selected_source') if winner else None,
        'winner_post_construction_gain':winner.get('post_construction_gain') if winner else None,
        'counts':{s:sum(r['status']==s for r in rows) for s in ('completed','incomplete','failed')},
        'missing_trials':config.trials-len(rows),'seconds':sum(r['seconds'] for r in rows),
        'operations':sum(r['operations'] for r in rows),'unknown_work_trials':sum(not r['work_known'] for r in rows),
        'provider_seconds':sum(t.get('model_seconds',0) for t in traces),
        'model_calls':sum(t.get('actual_calls',0) for t in traces),'reported_tokens':sum(t.get('reported_tokens',0) for t in traces),
        'reserved_tokens':sum(t.get('reserved_tokens',0) for t in traces),
        'unknown_token_trials':sum(not t.get('usage_known',True) for t in traces),
        'winner_llm_initial':any(d['stage']=='initial' and d['source']=='LLM proposal' and d['accepted'] for d in decisions),
        'winner_llm_checkpoint':any(d['stage']=='checkpoint' and d['source']=='LLM proposal' and d['accepted'] and d.get('execution',{}).get('status')=='applied' for d in decisions),
        'winner_llm_changed_schedule':any(d['stage']=='checkpoint' and d['source']=='LLM proposal' and d['accepted'] and d.get('execution',{}).get('status')=='applied' and (d.get('proposal') or {}).get('action') in ('reorder','diversify') for d in decisions)}
    if arm in ABLATION_ARMS:
        result.update(shared_initial_fingerprints=[r.get('shared_initial_fingerprint') for r in rows],
                      initial_routes_fingerprints=[r.get('initial_routes_fingerprint') for r in rows],
                      charged_seconds=sum(r.get('charged_seconds',r['seconds']) for r in rows))
    return result


def report(output, manifest):
    """Reconstruct only from saved measurements. Never execute a missing trial."""
    output=Path(output); frozen=manifest['protocol']
    if digest({k:v for k,v in frozen.items() if k!='fingerprint'})!=frozen['fingerprint']:
        raise ValueError('Manifest protocol checksum mismatch')
    if manifest['split'] not in ('development','validation'): raise ValueError('Held-out audit not supported by this protocol')
    config=ControllerProtocol.model_validate(frozen['config'])
    rows=[]; trials=[]
    for case_id in manifest['protocol']['panels'][manifest['split']]:
        case=case_by_id(case_id)
        for seed in config.seeds:
            problem=case.problem(seed)
            for arm in config.arms:
                saved=[]
                for index in range(config.trials):
                    path=output/'measurements'/f'{case_id}--{seed}--{arm}--{index}.json'
                    if not path.exists(): continue
                    envelope=json.loads(path.read_text(encoding='utf-8')); row=envelope['measurement']
                    if envelope['checksum']!=digest(row): raise ValueError('Measurement checksum mismatch')
                    for key,value in {'case_id':case_id,'seed':seed,'trial_seed':(seed+index*1000003)%2**32,'arm':arm,'trial':index,'problem_fingerprint':problem.fingerprint,
                                      'matrix_fingerprint':problem.matrix_fingerprint,'protocol_fingerprint':manifest['protocol']['fingerprint']}.items():
                        if row.get(key)!=value: raise ValueError('Measurement identity mismatch')
                    if row['status'] not in ('completed','incomplete','failed') or not 0<=row['operations']<=config.operations:
                        raise ValueError('Invalid measurement status or work')
                    if not math.isfinite(row['seconds']) or row['seconds']<0: raise ValueError('Invalid runtime')
                    if row['feasible']:
                        measured=validate_fleet_solution(problem,row['routes'])
                        if measured.total_distance!=row['total_distance']: raise ValueError('Saved route cost mismatch')
                    if arm in ABLATION_ARMS:
                        shared=json.loads((output/'initials'/f'{case_id}--{seed}--{index}.json').read_text(encoding='utf-8'))
                        if digest({k:v for k,v in shared.items() if k!='fingerprint'})!=shared['fingerprint']:
                            raise ValueError('Shared initial checksum mismatch')
                        if (shared['fingerprint']!=row.get('shared_initial_fingerprint') or shared['problem_fingerprint']!=problem.fingerprint
                                or shared['matrix_fingerprint']!=problem.matrix_fingerprint or shared['seed']!=row['trial_seed']):
                            raise ValueError('Shared initial identity mismatch')
                        if row['feasible'] and (row.get('controller') or {}).get('decisions',[{}])[0].get('proposal')!=shared['controller']['decisions'][0].get('proposal'):
                            raise ValueError('Ablation initial proposal differs')
                    saved.append(row); trials.append(row)
                rows.append(aggregate(saved,config,case,seed,arm,problem))
    result={'schema':'controller-comparison-results/v1','manifest':manifest,'rows':rows,'trials':trials,'summary':summarize(rows,config.arms)}
    if config.paired_ablation:
        initials=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((output/'initials').glob('*.json'))]
        result['shared_initial_usage']={'selections':len(initials),'accepted':sum(i['accepted'] for i in initials),
            'actual_model_calls':sum(i['controller']['actual_calls'] for i in initials),
            'reported_tokens':sum(i['controller']['reported_tokens'] for i in initials),
            'seconds':sum(i['seconds'] for i in initials),
            'unknown_usage':sum(not i['controller']['usage_known'] for i in initials)}
    return result


def write_reports(output, result):
    output=Path(output)
    save_new(output/'results.json',result)
    fields=['case_id','seed','arm','status','feasible','total_distance','longest_route','winner_trial','seconds','operations','provider_seconds','model_calls','reported_tokens','unknown_token_trials','winner_llm_initial','winner_llm_checkpoint']
    with (output/'results.csv').open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); writer.writeheader(); writer.writerows(result['rows'])
    lines=['# Four-arm controller experiment', '', f"Split: {result['manifest']['split']}. Mode: {result['manifest']['mode']}.",
        f"Protocol: `{result['manifest']['protocol']['fingerprint']}`.",
        f"Model: `{result['manifest']['protocol']['config']['adaptive']['provider']['model']}`.", '',
        'Primary quality statistics use completed pairs only. Valid incomplete incumbents are separate in JSON.',
        'Each case/seed selects its best validated trial; failed and missing slots remain in the denominator.', '',
        '| Arm | Completed | Incomplete | Failed | Missing | Runtime s | Model calls |', '|---|---:|---:|---:|---:|---:|---:|']
    for arm,r in result['summary']['arms'].items():
        c=r['counts']; elapsed=sum(row['seconds'] for row in result['rows'] if row['arm']==arm)
        lines.append(f"| {arm} | {c['completed']} | {c['incomplete']} | {c['failed']} | {c['missing']} | {elapsed:.3f} | {r['actual_model_calls']} |")
    lines+=['','| Candidate vs reference | Completed pairs | W/T/L | Mean % | Median % | Worst % |','|---|---:|---|---:|---:|---:|']
    for p in result['summary']['paired']:
        r=p['completed_only']; lines.append(f"| {p['arm']} vs {p['reference']} | {r['pairs']}/{p['expected_pairs']} | {r['wins']}/{r['ties']}/{r['losses']} | {r['mean_percent']} | {r['median_percent']} | {r['worst_percent']} |")
    lines+=['','No automatic superiority conclusion. Participation and accepted decisions are not evidence of advantage.',
        'JSON includes every trial, source attribution, failures, missing counts, subgroup results, runtime/work distributions and case-level dispersion.',
        'Equal host caps are not equal hardware work: inference FLOPs/memory are unmetered. Deadlines are cooperative.',
        'Repeated seeds are not independent instances. The interval bootstraps per-case means; a small panel is exploratory.',
        'Conventional hybrid retains its existing schedule. Static/random freeze initial strategy; adaptive may change it. Different schedules are part of the treatment.',
        'LLM initial responses are independently generated with matched seed/options, not guaranteed identical. This is an end-to-end comparison, not a pure feedback ablation.',
        'Development results are selection-biased. Validation is single-use for this protocol. Held-out execution is disabled.']
    if result['manifest']['protocol']['config'].get('paired_ablation'):
        lines+=['', 'The paired_static/paired_adaptive ablation shares one accepted initial proposal per case/seed/trial.',
                'Both arms are charged the same initial-selection elapsed time and token/call reservation; actual initial usage is counted once in shared_initial_usage.',
                'Pairs with differing constructed initial routes are excluded from the ablation, not credited as adaptation.',
                'End-to-end static_llm/adaptive_llm arms still use independent initial proposals.',
                'Status v2 distinguishes configured ILS completion from global budget exhaustion. Historical records keep their recorded status.']
    with (output/'report.md').open('x',encoding='utf-8') as f: f.write('\n'.join(lines)+'\n')


def run(saved, output, *, split='development', live=False, provider_factory=None, development=None):
    config=verify_protocol(saved)
    if split not in ('development','validation'): raise ValueError('Held-out execution disabled; final frozen review required')
    output=Path(output)
    if output.exists(): raise ValueError('New output directory required; no overwrite or implicit resume')
    if live:
        from api.routers.strategies import check_provider
        if not check_provider(config.adaptive.provider)['available']: raise ValueError('Exact Ollama model unavailable; experiment not started')
        if config.schema_version.endswith('/v2'):
            import httpx
            with httpx.Client(trust_env=False,timeout=3) as client:
                response=client.get('http://127.0.0.1:11434/api/tags');response.raise_for_status()
                match=next((m for m in response.json()['models'] if m['name']==config.adaptive.provider.model),None)
            if not config.model_digest or match is None or match.get('digest')!=config.model_digest:
                raise ValueError('Frozen model digest unavailable or changed')
    if split=='validation':
        if development is None: raise ValueError('Completed development evidence required before validation')
        dev=json.loads((Path(development)/'results.json').read_text(encoding='utf-8'))
        if dev['manifest']['split']!='development' or dev['manifest']['protocol']!=saved or dev['manifest']['mode']!=('live' if live else 'offline fixture'):
            raise ValueError('Development protocol or mode differs')
        audited=report(development,dev['manifest'])
        if audited!=dev or any(r['status']=='missing' for r in dev['rows']): raise ValueError('Development evidence incomplete or changed')
        registry=ROOT/'runs'/'controller-validation-locks'; registry.mkdir(parents=True,exist_ok=True)
        save_new(registry/(saved['fingerprint']+('-live' if live else '-fixture')+'.used'),{'protocol':saved['fingerprint']})
    output.mkdir(parents=True,exist_ok=False); (output/'measurements').mkdir()
    if config.paired_ablation: (output/'initials').mkdir()
    manifest={'protocol':saved,'split':split,'mode':'live' if live else 'offline fixture','development':str(development) if development else None}
    save_new(output/'manifest.json',manifest)
    provider_factory=provider_factory or (lambda:AdaptiveOllamaProvider(config.adaptive.provider) if live else OfflineFixture())
    for case_id in saved['panels'][split]:
        case=case_by_id(case_id)
        for seed in config.seeds:
            problem=case.problem(seed); identity=problem.fingerprint
            initials={}
            order=list(config.arms); random.Random(int(digest([case_id,seed])[:16],16)).shuffle(order)
            for arm in order:
                for index in range(config.trials):
                    trial_seed=(seed+index*1000003) % 2**32
                    if arm in ABLATION_ARMS and index not in initials:
                        initials[index]=shared_initial(problem,config,trial_seed,provider_factory)
                        save_new(output/'initials'/f'{case_id}--{seed}--{index}.json',initials[index])
                    row=trial(problem,config,arm,trial_seed,provider_factory,initials.get(index) if arm in ABLATION_ARMS else None)
                    if problem.fingerprint!=identity: raise ValueError('Shared problem mutated')
                    row.update(case_id=case_id,seed=seed,trial_seed=trial_seed,arm=arm,trial=index,
                               problem_fingerprint=identity,matrix_fingerprint=problem.matrix_fingerprint,protocol_fingerprint=saved['fingerprint'])
                    save_new(output/'measurements'/f'{case_id}--{seed}--{arm}--{index}.json',{'measurement':row,'checksum':digest(row)})
                print(f'{split} {case_id} seed={seed} arm={arm} recorded',flush=True)
    result=report(output,manifest); write_reports(output,result)
    return result
