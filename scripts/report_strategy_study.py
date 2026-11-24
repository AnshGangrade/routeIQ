"""Validate and report a finished paired study without executing any strategies."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.evaluation.fleet_dataset import case_by_id, digest
from engine.routing.validation import validate_fleet_solution
from scripts.audit_strategy_evidence import paired


def report(source,output):
    source=Path(source);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    data=json.loads((source/'results.json').read_text(encoding='utf-8'))
    frozen=json.loads((source/'protocol.json').read_text(encoding='utf-8'))
    assert data['finished'] and frozen['fingerprint']==digest({k:v for k,v in frozen.items() if k!='fingerprint'})==data['protocol_fingerprint']
    protocol=frozen['protocol'];problems={};counters=[]
    for row in data['rows']:
        assert row['split'] in ('development','validation')
        assert case_by_id(row['case_id']).split==row['split']
        key=(row['case_id'],row['search_seed'])
        if key not in problems:problems[key]=case_by_id(key[0]).problem(key[1])
        problem=problems[key]
        assert problem.fingerprint==row['problem_fingerprint'] and problem.matrix_fingerprint==row['matrix_fingerprint']
        assert row['operation_limit']==protocol['config']['operations_per_evaluation']
        assert row['time_limit_seconds']==protocol['config']['seconds_per_evaluation']
        assert 0<=row['operations']<=row['operation_limit']
        if row['feasible']:
            validated=validate_fleet_solution(problem,row['routes'])
            assert math.isclose(validated.total_distance,row['total_distance'],rel_tol=1e-12,abs_tol=1e-8)
            assert math.isclose(validated.longest_route_distance,row['longest_route'],rel_tol=1e-12,abs_tol=1e-8)
    for seed in protocol['seeds']:
        states={}
        for arm in ('random','llm'):
            directory=source/f'seed-{seed}'/arm
            state=json.loads((directory/'results.json').read_text(encoding='utf-8'))
            checkpoint=json.loads((directory/'checkpoint.json').read_text(encoding='utf-8'))
            assert digest(state)==checkpoint['checksum']==digest(checkpoint['state'])
            assert state['manifest']['config']=={**protocol['config'],'seed':seed}
            states[arm]=state
            records=state['records'];visited=set()
            def ancestry(key):
                if key in visited:return False
                visited.add(key);r=records[key]
                return r['creation_method']=='llm' and r['fitness'].get('eligible',False) or any(ancestry(k) for k in r['parents'])
            rows=[r for r in data['rows'] if r['split']=='development' and r['seed']==seed and r['arm']==arm]
            counters.append({'seed':seed,'arm':arm,'completed':sum(r['status']=='completed' for r in rows),
                'incomplete':sum(r['status']=='incomplete' for r in rows),'failed':sum(r['status']=='failed' for r in rows),
                'missing_reserved':state['reserved_evaluations']-len(rows),'proposal_attempts':state['proposals'],
                'source_attempts':state['proposals_by_source'],'source_accepted':state['accepted_by_source'],
                'llm_valid':sum(e['source']=='llm' and e['outcome']!='invalid' for e in state['proposal_events']),
                'llm_evaluated':sum(r['creation_method']=='llm' and bool(r['evaluation_history']) for r in records.values()),
                'winner_has_evaluated_llm_ancestry':bool(state['best_id']) and ancestry(state['best_id']),
                'rejections':state['rejections'],'operations':state['actual_operations'],'seconds':state['elapsed_seconds'],
                'tokens':state['llm_tokens'],'provider_calls':sum(u['calls'] for u in state['provider_usage']),
                'provider_seconds':sum(u['seconds'] for u in state['provider_usage']),
                'best_mean':records[state['best_id']]['fitness'].get('mean_distance') if state['best_id'] else None,
                'worst_case':records[state['best_id']]['fitness'].get('worst_distance') if state['best_id'] else None})
        assert states['llm']['manifest']['panel']==states['random']['manifest']['panel']
        assert states['llm']['manifest']['software']==states['random']['manifest']['software']==frozen['software']
        seeds=lambda s:[r['configuration_fingerprint'] for r in s['records'].values() if r['creation_method']=='seed']
        assert seeds(states['llm'])==seeds(states['random'])
        for split in ('development','validation'):
            inputs={}
            for arm in ('random','llm'):
                winner=states[arm]['best_id']
                inputs[arm]=[r for r in data['rows'] if r['split']==split and r['seed']==seed and r['arm']==arm and r['strategy_id']==winner]
            panel=protocol['config']['case_ids'] if split=='development' else protocol['validation_cases']
            recomputed=paired(inputs['llm'],inputs['random'],panel)
            recorded=next(c for c in data['paired'] if c['seed']==seed and c['split']==split)
            assert recomputed=={k:v for k,v in recorded.items() if k not in ('split','seed')}
    summary={k:v for k,v in data.items() if k!='rows'}
    summary.update(independently_validated_rows=len(data['rows']),counters=counters,protocol=protocol)
    (output/'report.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    columns=['split','seed','arm','strategy_id','case_id','total_distance','longest_route','status','feasible','termination','operations','seconds','operator_calls','accepted_moves','problem_fingerprint','matrix_fingerprint']
    with (output/'per-case.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(data['rows'])
    pairs=[{'split':c['split'],'seed':c['seed'],**r} for c in data['paired'] for r in c['per_case']]
    with (output/'paired.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=['split','seed','case_id','llm_distance','random_distance','difference','percentage','outcome','completed_pair']);writer.writeheader();writer.writerows(pairs)
    lines=['# Paired strategy study','',f"Model: {data['model']}. Frozen protocol: `{data['protocol_fingerprint']}`.",
        '','No held-out evaluation. These results do not establish AI superiority.','',
        '| Split | Seed | Bounded pairs / expected | Completed pairs | LLM win / tie / loss | Mean paired % |',
        '|---|---:|---:|---:|---:|---:|']
    for c in data['paired']:
        b=c['bounded'];lines.append(f"| {c['split']} | {c['seed']} | {b['pairs']} / {b['expected']} | {c['completed_only']['pairs']} | {b['wins']} / {b['ties']} / {b['losses']} | {b['mean_percentage']} |")
    lines += ['', '| Seed | Arm | Completed / incomplete / failed / missing | Work | Runtime s | Accepted LLM / evaluated | Tokens |', '|---|---|---:|---:|---:|---:|---:|']
    for c in counters:lines.append(f"| {c['seed']} | {c['arm']} | {c['completed']} / {c['incomplete']} / {c['failed']} / {c['missing_reserved']} | {c['operations']} | {c['seconds']:.3f} | {c['source_accepted'].get('llm',0)} / {c['llm_evaluated']} | {c['tokens']} |")
    lines+=['',protocol['attribution'], '',protocol['analysis'], '',
        'Positive percentage = (random - LLM) / random * 100 per case; average those percentages. Both zero => 0%; positive LLM against zero random => undefined and counted separately. Ties: relative and absolute tolerance 1e-9.',
        'Bootstrap: 2,000 draws, seed 7301. Per-case intervals condition on observed cases; aggregate intervals resample whole replicate means. Three seeds give weak uncertainty estimates. Development selection is biased; validation evaluates a fixed winner once per arm/replicate and is never fed back.',
        'Solver work and provider time are separate. Equal allocated caps are not equal consumed computation. Light frontend checks overlapped this study; wall time is descriptive, not a controlled hardware comparison.',
        'Full protocol, proposal sources/rejections, means/worst cases, missing counts and intervals: report.json. Every candidate-case: per-case.csv. Matched winners: paired.csv. Original checkpoints preserve full configurations and lineage.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Validated new-study rows and paired estimates:',len(data['rows']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();report(args.source,args.output)
