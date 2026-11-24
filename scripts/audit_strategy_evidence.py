"""Read-only paired analysis of saved Phase 6B evidence. Never invokes a solver/provider."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import statistics as stats
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.evaluation.fleet_dataset import case_by_id, digest
from engine.routing.validation import validate_fleet_solution


def interval(values, seed=7301):
    """Seeded paired percentile bootstrap; undefined with fewer than two units."""
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(stats.mean(rng.choices(values, k=len(values))) for _ in range(2000))
    return [means[49], means[1949]]


def paired(llm, random_rows, expected):
    def indexed(rows):
        result = {r['case_id']: r for r in rows}
        if len(result) != len(rows) or not set(result) <= set(expected):
            raise ValueError('Duplicate or unregistered cases')
        return result
    a, b = indexed(llm), indexed(random_rows)
    observed = []
    for key in expected:
        x, y = a.get(key), b.get(key)
        if x and y:
            for field in ('problem_fingerprint', 'matrix_fingerprint', 'search_seed', 'operation_limit', 'time_limit_seconds', 'distance_units'):
                if x[field] != y[field]:
                    raise ValueError('Mismatched paired inputs or budgets')
        valid = lambda r: r and r['feasible'] and r['status'] in ('completed', 'incomplete') and r['termination'] not in ('cancelled', 'interrupted', 'cancellation_error') and isinstance(r['total_distance'], (int, float)) and math.isfinite(r['total_distance']) and r['total_distance'] >= 0
        if not valid(x) or not valid(y):
            continue
        candidate, reference = x['total_distance'], y['total_distance']
        tie = math.isclose(candidate, reference, rel_tol=1e-9, abs_tol=1e-9)
        observed.append({'case_id': key, 'llm_distance': candidate, 'random_distance': reference,
            'difference': reference - candidate,
            'percentage': 100 * (reference - candidate) / reference if reference else 0. if not candidate else None,
            'outcome': 'tie' if tie else 'win' if candidate < reference else 'loss',
            'completed_pair': x['status'] == y['status'] == 'completed'})
    def summary(rows):
        differences = [r['difference'] for r in rows]
        percentages = [r['percentage'] for r in rows if r['percentage'] is not None]
        return {'expected': len(expected), 'pairs': len(rows), 'unavailable': len(expected)-len(rows),
            'wins': sum(r['outcome'] == 'win' for r in rows), 'ties': sum(r['outcome'] == 'tie' for r in rows), 'losses': sum(r['outcome'] == 'loss' for r in rows),
            'mean_difference': stats.mean(differences) if rows else None,
            'median_difference': stats.median(differences) if rows else None,
            'mean_percentage': stats.mean(percentages) if percentages else None,
            'median_percentage': stats.median(percentages) if percentages else None,
            'percentage_denominator': len(percentages), 'zero_reference_undefined': len(rows)-len(percentages),
            'difference_bootstrap_95': interval(differences), 'percentage_bootstrap_95': interval(percentages),
            'worst_difference': min(differences) if rows else None}
    return {'bounded': summary(observed), 'completed_only': summary([r for r in observed if r['completed_pair']]),
        'missing_llm': [c for c in expected if c not in a], 'missing_random': [c for c in expected if c not in b], 'per_case': observed}


def audit(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or source in output.parents:
        raise ValueError('Output must be separate from historical evidence')
    output.mkdir(parents=True, exist_ok=False)
    consumed = {}
    def read(name):
        path = source / name
        raw = path.read_bytes()
        consumed[name] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    protocol = read('protocol.json')
    assert protocol['fingerprint'] == digest({k:v for k,v in protocol.items() if k != 'fingerprint'})
    rows = read('per-instance.json')['rows']
    problems = {}
    for row in rows:
        key = (row['case_id'], row['search_seed'])
        if key not in problems:
            problems[key] = case_by_id(key[0]).problem(key[1])
        problem = problems[key]
        assert row['problem_fingerprint'] == problem.fingerprint
        assert row['matrix_fingerprint'] == problem.matrix_fingerprint
        if row['feasible']:
            checked = validate_fleet_solution(problem, row['routes'])
            assert math.isclose(checked.total_distance, row['total_distance'], rel_tol=1e-12, abs_tol=1e-8)
            assert math.isclose(checked.longest_route_distance, row['longest_route'], rel_tol=1e-12, abs_tol=1e-8)
        assert 0 <= row['operations'] <= row['operation_limit']
    runs, comparisons = [], []
    for config in protocol['configs']:
        seed, arms = config['seed'], {}
        for arm in ('random', 'llm'):
            state = read(f'seed-{seed}/{arm}/results.json')
            checkpoint = read(f'seed-{seed}/{arm}/checkpoint.json')
            assert digest(state) == checkpoint['checksum'] == digest(checkpoint['state'])
            assert state['manifest']['config'] == config
            arms[arm] = state
            measured = [r for record in state['records'].values() for h in record['evaluation_history'] for r in h['rows']]
            winner = state['records'].get(state['best_id'])
            sources = state['proposals_by_source']
            events = state['proposal_events']
            runs.append({'seed': seed, 'arm': arm, 'status': state['status'], 'termination': state['termination'],
                'proposals': state['proposals'], 'attempts_by_source': sources, 'accepted_by_source': state['accepted_by_source'],
                'valid_llm': sum(e['source']=='llm' and e['outcome']!='invalid' for e in events),
                'evaluated_llm': sum(r['creation_method']=='llm' and bool(r['evaluation_history']) for r in state['records'].values()),
                'rejections': state['rejections'], 'completed': sum(r['status']=='completed' for r in measured),
                'incomplete': sum(r['status']=='incomplete' for r in measured), 'failed': sum(r['status']=='failed' for r in measured),
                'missing_reserved': state['reserved_evaluations']-len(measured), 'operations': state['actual_operations'],
                'runtime': state['elapsed_seconds'], 'provider_seconds': state['generation_seconds'], 'provider_usage': state['provider_usage'],
                'tokens': state['llm_tokens'], 'best_id': state['best_id'], 'winner_source': winner['creation_method'] if winner else None,
                'fitness': winner['fitness'] if winner else None, 'history': state['history']})
        assert arms['llm']['manifest']['panel'] == arms['random']['manifest']['panel']
        assert arms['llm']['manifest']['software'] == arms['random']['manifest']['software']
        authored = lambda state: [r['configuration_fingerprint'] for r in state['records'].values() if r['creation_method']=='seed']
        assert authored(arms['llm']) == authored(arms['random'])
        winner_rows = lambda s: s['records'][s['best_id']]['evaluation_history'][-1]['rows'] if s['best_id'] else []
        comparisons.append({'split':'development', 'seed': seed, **paired(winner_rows(arms['llm']), winner_rows(arms['random']), config['case_ids'])})
    validation = read('validation-progress.json')['candidates']
    for config in protocol['configs']:
        by_arm = {c['arm']: c for c in validation if c['seed']==config['seed']}
        comparisons.append({'split':'validation', 'seed':config['seed'], **paired(by_arm['llm']['rows'], by_arm['random']['rows'], protocol['validation_cases'])})
    heldout = {arm:[r for r in rows if r['split']=='heldout' and r['arm']==arm] for arm in ('llm','random')}
    comparisons.append({'split':'heldout', 'seed':None, **paired(heldout['llm'], heldout['random'], protocol['heldout_cases'])})
    replicate_summary = {}
    for split in ('development','validation'):
        values = [c['bounded']['mean_percentage'] for c in comparisons if c['split']==split]
        replicate_summary[split] = {'replicates':len(values), 'mean_percentage':stats.mean(values), 'replicate_bootstrap_95':interval(values),
            'note':'Resample whole paired replicate means, not repeated seed-case rows as independent instances. Only three seeds; exploratory and selection-biased.'}
    report = {'schema':'strategy-evidence-audit/v1','model':protocol['model'], 'historical_protocol':protocol['fingerprint'],
        'evidence':'Historical saved measurements only; no new solver, LLM, validation or held-out calls.',
        'independently_validated_rows':len(rows), 'runs':runs, 'paired':comparisons, 'replicate_summary':replicate_summary,
        'source_sha256':consumed, 'ai_superiority_established':False,
        'limitations':['Development winners were selected on the same cases; not an unbiased estimate.',
            'LLM arm also uses mutations, crossover and authored seeds: no causal isolation of LLM contribution.',
            'Positive differences mean random minus LLM; percentages use each random-case distance as denominator.',
            'Both-zero percentage is zero; positive LLM distance against zero random distance is undefined.',
            'Ties use rel_tol=abs_tol=1e-9. Bounded feasible incomplete results are separate from completed-only pairs.',
            'Bootstrap: 2,000 draws, seed 7301, percentile 95%; per-case intervals condition on observed pairs. Missing held-out cases may be systematically different.',
            'Equal allocated solver caps are not equal actual work; inference adds hardware compute and consumes wall allowance.',
            'Held-out comparison remains incomplete; no rerun or guard modification.']}
    (output/'audit.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    flat = [{ 'split':c['split'],'seed':c['seed'], **r} for c in comparisons for r in c['per_case']]
    with (output/'paired.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    lines=['# Strategy evidence audit', '', 'Model: '+protocol['model']+'. Historical evidence only. No superiority claim.', '',
        '| Split | Seed | Bounded pairs / expected | Completed pairs | Win / tie / loss | Mean paired % |',
        '|---|---:|---:|---:|---:|---:|']
    for c in comparisons:
        b=c['bounded'];lines.append(f"| {c['split']} | {c['seed']} | {b['pairs']} / {b['expected']} | {c['completed_only']['pairs']} | {b['wins']} / {b['ties']} / {b['losses']} | {b['mean_percentage']} |")
    lines += ['', *['- '+s for s in report['limitations']], '', 'All per-case pairs, missing IDs, source hashes, full budgets, source counts, work, runtime and intervals are in audit.json / paired.csv and the unchanged source protocol.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert all(hashlib.sha256((source/name).read_bytes()).hexdigest()==value for name,value in consumed.items())
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default='runs/phase6b-qwen3-20261115')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=audit(args.source,args.output)
    print('Validated saved rows:',result['independently_validated_rows'])
    print('No evaluations rerun. Paired report:',args.output)
