import type { EvolutionProgressResponse } from '../types/api';
import { differenceText } from '../services/workflow';

export function EvaluationSummary({ evolution }: { evolution: EvolutionProgressResponse | null }) {
  const evaluation = evolution?.status === 'completed' ? evolution.test_evaluation : null;
  if (!evaluation || !Number.isFinite(evaluation.evolved_avg_distance) || !evaluation.baselines.length || evaluation.baselines.some(b => !Number.isFinite(b.avg_route_distance))) return <p className="muted">Held-out performance is unavailable until a run completes all evaluations.</p>;
  return <section className="evaluation-summary" aria-label="Held-out performance">
    <h3>Held-out performance</h3><p>{evaluation.test_instances_count} separate synthetic, single-driver instances. These are not results for your selected fleet.</p>
    <p><strong>Winner mean distance: {evaluation.evolved_avg_distance.toFixed(2)} map units</strong></p>
    <div className="table-scroll"><table><caption>Comparison on unseen test instances</caption><thead><tr><th>Baseline</th><th>Mean distance</th><th>Winner vs baseline</th></tr></thead><tbody>{evaluation.baselines.map(b => <tr key={b.algorithm}><th>{b.algorithm === 'nearest_neighbor' ? 'Nearest Neighbor' : b.algorithm === '2opt' || b.algorithm === 'two_opt' ? '2-Opt' : b.algorithm}</th><td>{b.avg_route_distance.toFixed(2)} map units</td><td>{differenceText(evaluation.evolved_avg_distance, b.avg_route_distance)}</td></tr>)}</tbody></table></div>

  </section>;
}
