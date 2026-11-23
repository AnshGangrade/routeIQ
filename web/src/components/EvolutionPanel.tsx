import type { EvolutionProgressResponse, RoutingResultResponse } from '../types/api';
import { EvaluationSummary } from './EvaluationSummary';
import { PlanSelection } from './PlanSelection';

interface EvolutionPanelProps { evolution: EvolutionProgressResponse; onClose: () => void;
  onApply?: () => void; canApply?: boolean; onCancel?: () => void; pollError?: string | null;
  measurement?: RoutingResultResponse | null; mode?: string; measuring?: boolean; measurementError?: string | null; onMeasure?: () => void; }

export function EvolutionPanel({ evolution, onClose, onApply, canApply, onCancel, pollError, measurement, mode = 'synthetic', measuring, measurementError, onMeasure }: EvolutionPanelProps) {
  const active = ['pending', 'running', 'cancelling'].includes(evolution.status);
  const candidates = evolution.generations.flatMap(gen => gen.candidates);
  const valid = candidates.filter(c => c.is_valid && c.fitness !== null && Number.isFinite(c.fitness));
  const winner = evolution.best_heuristic_id ? valid.find(c => c.heuristic_id === evolution.best_heuristic_id) : [...valid].sort((a, b) => a.fitness! - b.fitness!)[0];
  const stage = ({ preparing: 'Preparing examples', evaluating_candidates: 'Testing candidates', generation_completed: 'Generation evaluated', held_out: 'Evaluating held-out examples', pending: 'Waiting to start', cancelling: 'Finishing in-flight work' } as Record<string, string>)[evolution.stage || evolution.status] || evolution.status;
  return <section className="panel stack" aria-label="Evolution run">
    <div className="section-heading"><h2>{active ? 'Experiment progress' : 'Experiment results'}</h2><span className={`badge ${evolution.status === 'failed' ? 'danger' : ''}`}>{evolution.status}</span></div>
    {pollError && <p role="alert" className="notice error">Progress unavailable: {pollError}. Retrying.</p>}
    {active && <div className="stack"><p role="status">{stage} ? Generation {evolution.current_generation} of {evolution.total_generations}{evolution.stage === 'evaluating_candidates' && ` ? candidates ${evolution.candidates_done ?? 0}/${evolution.candidates_per_generation ?? 0}`}</p><progress aria-label="Evolution progress" value={evolution.generations.length} max={evolution.total_generations + 1} />
      <button className="button secondary fit" onClick={onCancel} disabled={evolution.status === 'cancelling'}>{evolution.status === 'cancelling' ? 'Cancellation requested' : 'Cancel evolution'}</button></div>}
    {evolution.status === 'cancelled' && <p>Evolution cancelled. No winner can be applied.</p>}
    {evolution.error && <p role="alert" className="notice error">{evolution.error}</p>}
    {evolution.status === 'completed' && winner && <>
      {measuring && <p role="status">Measuring the winner and baselines on your plan?</p>}
      {measurementError && <div role="alert"><p>{measurementError}</p><button className="button secondary" onClick={onMeasure}>Retry measurement</button></div>}
      {measurement?.optimization ? <PlanSelection selection={measurement.optimization} distance={measurement.total_distance} mode={mode} /> : !measuring && !measurementError && <p>Create a route plan to measure this winner against its baselines.</p>}
      <button className="button primary fit" onClick={onApply} disabled={!canApply || !!pollError || !measurement?.optimization || measuring}>Apply final route to this plan</button>
    </>}
    <details><summary>Held-out evaluation & candidate details ({candidates.length})</summary>
      <p className="small muted">Run {evolution.run_id}. Training uses synthetic single-driver examples; lower distance is better.</p>
      {evolution.status === 'completed' && winner && <section aria-label="Validated winner"><h3>Winner: {winner.heuristic_id}</h3><p>Training mean distance (map units): {winner.fitness?.toFixed(2)}</p><pre><code>{winner.code}</code></pre></section>}
      {evolution.status === 'completed' && <EvaluationSummary evolution={evolution} />}
      {evolution.generations.map(gen => <section className="generation" key={gen.generation}><h3>Generation {gen.generation}</h3><p>{gen.valid_count} valid ? {gen.invalid_count} invalid</p>
        {gen.candidates.map(candidate => <details key={candidate.heuristic_id}><summary>{candidate.heuristic_id} ? {candidate.is_valid && candidate.fitness !== null ? `${candidate.fitness.toFixed(2)} map units` : 'Invalid'}</summary><p>{candidate.rejection_reason || candidate.rationale}</p><pre><code>{candidate.code || 'No candidate code available.'}</code></pre></details>)}
      </section>)}
    </details>
    <button className="text-button fit" onClick={onClose}>Back to route plan</button>
  </section>;
}
