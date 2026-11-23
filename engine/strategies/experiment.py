"""Comparable research arms and explicit, single-use frozen final evaluation."""
import csv
import json
from pathlib import Path
from .evolution import run_experiment, atomic_json
from .models import ExperimentConfig, StrategyRecord
from .evaluation import evaluate_one, fitness
from engine.evaluation.fleet_dataset import cases, digest, DATASET_VERSION
from .protocol import software_record
from engine.evaluation.fleet_reporting import improvement,tied,_statistics


def paired_controls(winners,case_ids):
    comparisons=[]
    for name in winners:
        for reference in winners:
            if name==reference: continue
            measured=[]
            for case_id in case_ids:
                a=winners[name].get(case_id); b=winners[reference].get(case_id)
                if not a or not b or not all(r['feasible'] and r['status']!='failed' and r['termination'] not in ('cancelled','interrupted','cancellation_error') for r in (a,b)):
                    continue
                for key in ('problem_fingerprint','matrix_fingerprint','search_seed','operation_limit','time_limit_seconds'):
                    if a[key]!=b[key]: raise ValueError('Unpaired control inputs or budgets')
                x,y=a['total_distance'],b['total_distance']
                measured.append({'case_id':case_id,'candidate_distance':x,'reference_distance':y,
                    'percentage':improvement(y,x),'completed_pair':a['status']==b['status']=='completed',
                    'outcome':'tie' if tied(x,y) else 'win' if x<y else 'loss'})
            def summary(rows):
                return {'pairs':len(rows),'unavailable':len(case_ids)-len(rows),
                    'wins':sum(r['outcome']=='win' for r in rows),'ties':sum(r['outcome']=='tie' for r in rows),
                    'losses':sum(r['outcome']=='loss' for r in rows),
                    'percentage':_statistics([r['percentage'] for r in rows if r['percentage'] is not None])}
            comparisons.append({'method':name,'reference':reference,'bounded_training':summary(measured),
                'completed_only':summary([r for r in measured if r['completed_pair']]),'per_case':measured})
    return comparisons


def compare(config,output,provider_factory,*,root=None):
    output=Path(output); output.mkdir(parents=True,exist_ok=False)
    arms={}; winners={}
    for arm in ('hand','random','llm'):
        # Same immutable host configuration and deterministic proposal/search seeds.
        state=run_experiment(config,output/arm,arm=arm,provider=provider_factory() if arm=='llm' else None,root=root)
        best=state['records'].get(state['best_id'])
        winners[arm]={r['case_id']:r for r in best['evaluation_history'][-1]['rows']} if best else {}
        arms[arm]={'status':state['status'],'termination':state['termination'],
            'best_id':state['best_id'],'fitness':best['fitness'] if best else None,
            'reserved_evaluations':state['reserved_evaluations'],'actual_operations':state['actual_operations'],
            'generation_seconds':state['generation_seconds'],'evaluation_seconds':state['evaluation_seconds'],
            'elapsed_seconds':state['elapsed_seconds'],'llm_calls_reserved':state['llm_calls'],
            'llm_calls_actual':sum(u['calls'] for u in state['provider_usage']),
            'tokens':state['llm_tokens'],'monetary_cost':None}
    result={'schema':'strategy-comparison/v1','config':config.model_dump(mode='json'),'arms':arms,
        'paired':paired_controls(winners,config.case_ids),
        'quality_policy':'bounded development incumbents, not completed-only Phase 5B statistics',
        'limitations':['Equal allocated caps; report actual usage separately. Hand portfolio stops after fixed seeds.',
            'Provider latency consumes the same wall allocation; inference FLOPs and monetary costs unavailable.',
            'Offline proposals do not establish LLM superiority; live output and wall deadlines are not deterministic.',
            'Development selection performance is biased; no validation or held-out evaluation occurred.']}
    atomic_json(output/'comparison.json',result)
    with (output/'comparison.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=['arm','mean_distance','completed_cases','incomplete_cases','evaluations','operations','total_seconds','llm_calls','tokens'])
        writer.writeheader()
        for arm,row in arms.items():
            f=row['fitness'] or {}
            writer.writerow({'arm':arm,'mean_distance':f.get('mean_distance'),'completed_cases':f.get('completed'),
                'incomplete_cases':f.get('incomplete'),'evaluations':row['reserved_evaluations'],'operations':row['actual_operations'],
                'total_seconds':row['elapsed_seconds'],'llm_calls':row['llm_calls_actual'],'tokens':row['tokens']})
    return result


def freeze(run_directory,destination,*,root=None):
    root=Path(root or Path(__file__).resolve().parents[2])
    state=json.loads((Path(run_directory)/'results.json').read_text())
    checkpoint=json.loads((Path(run_directory)/'checkpoint.json').read_text())
    if checkpoint['checksum']!=digest(checkpoint['state']) or digest(state)!=digest(checkpoint['state']):
        raise ValueError('Run result/checkpoint integrity failure')
    if state['status'] not in ('completed','stopped') or not state['best_id']: raise ValueError('No terminal evaluated winner')
    if state['manifest']['software']!=software_record(root): raise ValueError('Measured source differs')
    winner=StrategyRecord.model_validate(state['records'][state['best_id']])
    if not winner.fitness.get('eligible'): raise ValueError('Winner lacks full valid panel')
    content={'schema':'frozen-strategy/v1','strategy':winner.model_dump(mode='json'),
        'config':state['manifest']['config'],'software':state['manifest']['software'],
        'dataset_version':DATASET_VERSION,'training_experiment':state['experiment_id'],
        'selection':'development only; no held-out feedback','heldout_cases':[c.id for c in cases('heldout')]}
    frozen={**content,'fingerprint':digest(content)}
    with Path(destination).open('x',encoding='utf-8') as stream: json.dump(frozen,stream,indent=2,allow_nan=False)
    return frozen


def evaluate_frozen(path,output,*,acknowledge=False,root=None):
    if not acknowledge: raise ValueError('Explicit final held-out acknowledgement required')
    root=Path(root or Path(__file__).resolve().parents[2]); path=Path(path)
    saved=json.loads(path.read_text()); content={k:v for k,v in saved.items() if k!='fingerprint'}
    if saved['fingerprint']!=digest(content) or saved['software']!=software_record(root) or saved['dataset_version']!=DATASET_VERSION:
        raise ValueError('Frozen strategy protocol differs')
    selected=cases('heldout')
    if saved['heldout_cases']!=[c.id for c in selected]: raise ValueError('Held-out catalog mismatch')
    config=ExperimentConfig.model_validate(saved['config']); record=StrategyRecord.model_validate(saved['strategy'])
    # Registry is independent of artifact/output paths, including copied freezes.
    # A crash consumes this authorization; no repeated selection on test outcomes.
    output=Path(output)
    if output.exists(): raise ValueError('New output required')
    registry=root/'runs'/'strategy-heldout-locks'; registry.mkdir(parents=True,exist_ok=True)
    with (registry/(saved['fingerprint']+'.used')).open('x',encoding='utf-8') as stream:
        stream.write(saved['fingerprint'])
    output.mkdir(parents=True,exist_ok=False); rows=[]
    for case in selected:
        row=evaluate_one(case.problem(config.search_seed),record.config,config)
        row['case_id']=case.id; rows.append(row)
        atomic_json(output/'results.json',{'frozen_fingerprint':saved['fingerprint'],'split':'heldout',
            'finished':False,'rows':rows,'expected_cases':len(selected)})
    report={'frozen_fingerprint':saved['fingerprint'],'split':'heldout','finished':True,'rows':rows,
            'fitness':fitness(rows,len(selected)),'selection':'none; fixed strategy; incomplete remains labelled'}
    atomic_json(output/'results.json',report)
    return report
