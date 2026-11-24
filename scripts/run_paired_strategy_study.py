"""Bounded, explicitly live local paired study; no held-out path exists here."""
import argparse
import json
from pathlib import Path
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.evaluation.fleet_dataset import case_by_id, digest
from engine.strategies.models import ExperimentConfig
from engine.strategies.provider import OllamaProvider, ProviderConfig
from engine.strategies.evolution import run_experiment, atomic_json
from engine.strategies.evaluation import evaluate_one
from engine.strategies.experiment import freeze
from engine.strategies.protocol import software_record
from api.routers.strategies import check_provider
from scripts.audit_strategy_evidence import paired, interval


def validate_protocol(protocol):
    config=ExperimentConfig.model_validate(protocol['config'])
    provider=ProviderConfig.model_validate(protocol['provider'])
    if provider.model!=protocol['model']:raise ValueError('Model differs')
    seeds=protocol['seeds']
    if len(seeds)<2 or len(seeds)!=len(set(seeds)):raise ValueError('Independent replicate seeds required')
    if len(protocol['arm_order'])!=len(seeds) or any(sorted(order)!=['llm','random'] for order in protocol['arm_order']):raise ValueError('Two paired arms required')
    panel=protocol['validation_cases']
    if not panel or len(panel)!=len(set(panel)) or any(case_by_id(c).split!='validation' for c in panel):raise ValueError('Validation-only selection panel required')
    for seed in seeds:ExperimentConfig.model_validate({**config.model_dump(),'seed':seed})
    return config,provider


def run(path,output):
    protocol=json.loads(Path(path).read_text())
    config,provider_config=validate_protocol(protocol)
    check=check_provider(provider_config)
    if not check['available']:raise ValueError(check['message'])
    root=Path(__file__).resolve().parents[1]
    frozen={'protocol':protocol,'software':software_record(root),'provider_check':check}
    frozen['fingerprint']=digest(frozen)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    atomic_json(output/'protocol.json',frozen)
    results=[]; runs=[]; all_rows=[]
    for seed,order in zip(protocol['seeds'],protocol['arm_order']):
        config=ExperimentConfig.model_validate({**protocol['config'],'seed':seed})
        winners={}
        for arm in order:
            directory=output/f'seed-{seed}'/arm
            state=run_experiment(config,directory,arm=arm,provider=OllamaProvider(provider_config) if arm=='llm' else None)
            winner=state['records'].get(state['best_id'])
            rows=winner['evaluation_history'][-1]['rows'] if winner else []
            winners[arm]=(winner,rows)
            runs.append({'seed':seed,'arm':arm,'state_file':str(directory/'results.json'),'status':state['status'],
                'termination':state['termination'],'proposals':state['proposals'],'sources':state['proposals_by_source'],
                'accepted':state['accepted_by_source'],'rejections':state['rejections'], 'operations':state['actual_operations'],
                'seconds':state['elapsed_seconds'],'tokens':state['llm_tokens'],'provider_usage':state['provider_usage'],
                'fitness':winner['fitness'] if winner else None})
            if winner and state['status'] in ('completed','stopped') and winner['fitness']['eligible']:
                freeze(directory,directory/'frozen-development-winner.json')
            for record in state['records'].values():
                for history in record['evaluation_history']:
                    all_rows.extend({'split':'development','seed':seed,'arm':arm,'strategy_id':record['strategy_id'],**r} for r in history['rows'])
            atomic_json(output/'progress.json',{'model':protocol['model'],'runs':runs,'paired':results,'rows':all_rows,'finished':False})
        results.append({'split':'development','seed':seed,**paired(winners['llm'][1],winners['random'][1],config.case_ids)})
        validation={}
        for arm in ('random','llm'):
            winner=winners[arm][0]; validation[arm]=[]
            if winner and winner['fitness']['eligible']:
                from engine.strategies.models import StrategyConfig
                strategy=StrategyConfig.model_validate(winner['config'])
                for case_id in protocol['validation_cases']:
                    row={'case_id':case_id,**evaluate_one(case_by_id(case_id).problem(config.search_seed),strategy,config)}
                    validation[arm].append(row)
                    all_rows.append({'split':'validation','seed':seed,'arm':arm,'strategy_id':winner['strategy_id'],**row})
                    atomic_json(output/'progress.json',{'model':protocol['model'],'runs':runs,'paired':results,'rows':all_rows,'finished':False})
        results.append({'split':'validation','seed':seed,**paired(validation['llm'],validation['random'],protocol['validation_cases'])})
    aggregate={}
    for split in ('development','validation'):
        comparisons=[r for r in results if r['split']==split]
        means=[r['bounded']['mean_percentage'] for r in comparisons if r['bounded']['mean_percentage'] is not None]
        aggregate[split]={'observed_replicates':len(means),'expected_replicates':len(protocol['seeds']),
            'mean_paired_percentage':statistics.mean(means) if means else None,'replicate_bootstrap_95':interval(means)}
    report={'model':protocol['model'],'protocol_fingerprint':frozen['fingerprint'],'finished':True,'runs':runs,'paired':results,
        'rows':all_rows,'replicate_summary':aggregate,'heldout':'Not accessed; no superiority conclusion','interpretation':protocol['attribution']}
    atomic_json(output/'results.json',report)
    print('Paired development/validation artifacts:',output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol',default='examples/paired-strategy-study.json')
    p.add_argument('--output',required=True)
    p.add_argument('--live-local-ollama',action='store_true',required=True)
    args=p.parse_args();run(args.protocol,args.output)
