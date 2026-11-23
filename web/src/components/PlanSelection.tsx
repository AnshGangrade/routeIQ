import type { OptimizationSelection } from '../types/api';
import { formatDistance } from '../services/distance';
import { differenceText } from '../services/workflow';

interface Props { selection: OptimizationSelection; distance: number; mode: string; }
export function PlanSelection({ selection: s, distance, mode }: Props) {
  const format = (value: number | null) => value === null ? 'Unavailable' : formatDistance(value, mode);
  const sources: Record<string, string> = { nearest_neighbor: 'Nearest Neighbor', '2opt': '2-Opt', raw_evolved: 'Raw evolved candidate', refined_evolved: 'Evolved candidate + 2-Opt' };
  return <section className="stack" aria-label="Current-plan selection">
    <div><h3>{s.baseline_retained ? 'Baseline retained' : 'Evolution improved this plan'}</h3>
      <p>{differenceText(distance, s.best_baseline_distance)}{distance === s.best_baseline_distance ? ' (0%)' : ''} vs best baseline. Selected: {sources[s.selected_source] || s.selected_source}.</p>
      {s.raw_evolved_distance !== null && <p className="small muted">Raw candidate: {differenceText(s.raw_evolved_distance, s.best_baseline_distance)} vs best baseline.</p>}
    </div>
    <div className="selection-metrics"><div><span>Best baseline</span><strong>{format(s.best_baseline_distance)}</strong></div><div><span>Raw evolved</span><strong>{format(s.raw_evolved_distance)}</strong></div><div><span>Final selected route</span><strong>{format(distance)}</strong></div></div>
    <div className="table-scroll"><table className="comparison-table"><caption>Current plan · {mode === 'road' ? 'road distances' : 'synthetic map units'}</caption><thead><tr><th scope="col">Method</th><th scope="col">Distance</th><th scope="col">Vs best baseline</th></tr></thead><tbody>
      {([
        ['Nearest Neighbor', s.nearest_neighbor_distance], ['2-Opt', s.two_opt_distance], ['Raw evolved', s.raw_evolved_distance],
        ...(s.refined_evolved_distance !== null ? [['Evolved + 2-Opt', s.refined_evolved_distance]] : []), ['Final selected', distance],
      ] as [string, number | null][]).map(([name, value]) => <tr key={name}><th scope="row">{name}</th><td>{format(value)}</td><td>{value === null ? 'Unavailable' : differenceText(value, s.best_baseline_distance)}</td></tr>)}
    </tbody></table></div>
    {Object.entries(s.errors).map(([method, error]) => <p role="alert" className="small" key={method}>{method.replace(/_/g, ' ')}: {error}. {s.baseline_retained ? 'The best valid baseline was retained.' : 'Excluded from selection.'}</p>)}
  </section>;
}
