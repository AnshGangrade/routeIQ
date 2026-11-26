"""Paired evidence for the four-arm controller experiment; no solver decisions."""
import itertools
import statistics
from .fleet_reporting import improvement, tied, _statistics

ARMS = ('hybrid', 'random', 'static_llm', 'adaptive_llm')
ABLATION_ARMS = ('paired_static', 'paired_adaptive')


def summarize(rows, arms=ARMS):
    """Rows are one selected incumbent per case/replication/arm, not pooled trials."""
    by_key = {(r['case_id'], r['seed'], r['arm']): r for r in rows}
    if len(by_key) != len(rows):
        raise ValueError('Duplicate measurements')
    keys = sorted({(r['case_id'], r['seed']) for r in rows})
    paired = []
    for arm, reference in itertools.permutations(arms, 2):
        samples = []
        excluded = {k: 0 for k in ('missing', 'failed', 'incomplete')}
        if arm in ABLATION_ARMS and reference in ABLATION_ARMS:
            excluded['unmatched_initial'] = 0
        bounded = []
        for case, seed in keys:
            a, b = by_key.get((case, seed, arm)), by_key.get((case, seed, reference))
            if not a or not b or 'missing' in (a['status'], b['status']):
                excluded['missing'] += 1
                continue
            for field in ('problem_fingerprint', 'matrix_fingerprint', 'allocation'):
                if a[field] != b[field]: raise ValueError('Unmatched inputs or budgets')
            if arm in ABLATION_ARMS and reference in ABLATION_ARMS and (
                    not a.get('shared_initial_fingerprints') or
                    a['shared_initial_fingerprints'] != b.get('shared_initial_fingerprints') or
                    a.get('initial_routes_fingerprints') != b.get('initial_routes_fingerprints')):
                excluded['unmatched_initial'] += 1
                continue
            if not a['feasible'] or not b['feasible'] or 'failed' in (a['status'], b['status']):
                excluded['failed'] += 1
                continue
            x, y = a['total_distance'], b['total_distance']
            sample = {'case_id': case, 'seed': seed, 'candidate_distance': x, 'reference_distance': y,
                'percentage': improvement(y, x), 'outcome': 'tie' if tied(x, y) else 'win' if x < y else 'loss',
                'runtime_difference': a['seconds']-b['seconds'], 'work_difference': a['operations']-b['operations'],
                'stops': a['stops'], 'drivers': a['drivers'], 'distribution': a['distribution'], 'directed': a['directed']}
            bounded.append(sample)
            if a['status'] != 'completed' or b['status'] != 'completed': excluded['incomplete'] += 1
            else: samples.append(sample)

        def stats(values):
            percentages = [r['percentage'] for r in values if r['percentage'] is not None]
            # Seeds on the same instance are dependent: bootstrap case means, not individual seeds.
            groups = {}
            for r in values:
                if r['percentage'] is not None: groups.setdefault(r['case_id'], []).append(r['percentage'])
            return {'pairs': len(values), 'independent_cases': len({r['case_id'] for r in values}),
                'percentage_pairs': len(percentages), 'undefined_percentage_pairs': len(values)-len(percentages),
                'wins': sum(r['outcome']=='win' for r in values), 'ties': sum(r['outcome']=='tie' for r in values),
                'losses': sum(r['outcome']=='loss' for r in values),
                'mean_percent': statistics.mean(percentages) if percentages else None,
                'median_percent': statistics.median(percentages) if percentages else None,
                'worst_percent': min(percentages, default=None),
                'case_mean_dispersion': _statistics([statistics.mean(v) for v in groups.values()]),
                'runtime_difference': _statistics([r['runtime_difference'] for r in values]),
                'work_difference': _statistics([r['work_difference'] for r in values])}
        subgroups = {}
        for field in ('stops', 'drivers', 'distribution', 'directed'):
            subgroups[field] = {str(value): stats([r for r in samples if r[field]==value]) for value in sorted({r[field] for r in samples})}
        paired.append({'arm': arm, 'reference': reference, 'expected_pairs': len(keys),
            'excluded': excluded, 'completed_only': stats(samples), 'bounded_incumbents': stats(bounded),
            'by_characteristic': subgroups, 'per_pair': bounded})
    arm_stats = {}
    for arm in arms:
        values = [r for r in rows if r['arm']==arm]
        arm_stats[arm] = {'counts': {status: sum(r['status']==status for r in values) for status in ('completed','incomplete','failed','missing')},
            'runtime': _statistics([r['seconds'] for r in values]), 'operations': _statistics([r['operations'] for r in values]),
            'provider_seconds': sum(r['provider_seconds'] for r in values),
            'actual_model_calls': sum(r['model_calls'] for r in values),
            'reported_tokens': sum(r['reported_tokens'] for r in values),
            'unknown_token_trials': sum(r['unknown_token_trials'] for r in values),
            'unknown_work_trials': sum(r['unknown_work_trials'] for r in values),
            'winners_with_accepted_llm_initial': sum(r['winner_llm_initial'] for r in values),
            'winners_with_applied_llm_checkpoint': sum(r['winner_llm_checkpoint'] for r in values)}
    return {'arms': arm_stats, 'paired': paired,
        'conclusion': 'No superiority conclusion is automatic. Inspect paired completion, independent cases, repeatability, overhead and regressions.'}
