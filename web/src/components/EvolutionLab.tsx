import type { Dispatch, SetStateAction } from 'react';
import type { EvolutionProgressResponse, StartEvolutionRequest, RoutingResultResponse } from '../types/api';
import { EvolutionPanel } from './EvolutionPanel';

export const initialEvolution: StartEvolutionRequest = { num_stops: 20, num_instances: 5, num_generations: 3, candidates_per_generation: 4, elites_kept: 2, seed: 42, mode: 'mock', temperature: 0.7 };
interface Props { config: StartEvolutionRequest; setConfig: Dispatch<SetStateAction<StartEvolutionRequest>>;
  evolution: EvolutionProgressResponse | null; busy: boolean; pollError: string | null; hasInstance: boolean;
  measurement?: RoutingResultResponse | null; mode?: string; measuring?: boolean; measurementError?: string | null; onMeasure?: () => void;
  onStart: () => void; onCancel: () => void; onApply: () => void; }
export function EvolutionLab({ config, setConfig, evolution, busy, pollError, hasInstance, onStart, onCancel, onApply, measurement, mode, measuring, measurementError, onMeasure }: Props) {
  const running = !!evolution && ['pending', 'running', 'cancelling'].includes(evolution.status);
  const fields = [ ['num_stops', 'Stops per example', 10, 100], ['num_instances', 'Training examples', 3, 50], ['num_generations', 'Generations (rounds)', 2, 20], ['candidates_per_generation', 'Candidates per round', 2, 10], ['elites_kept', 'Strategies retained', 1, 10] ] as const;
  return <section className="stack"><div className="page-heading"><div><h1>Evolution Lab</h1><p>Test a strategy. Keep the shortest verified route.</p></div></div>
    <form className="panel stack lab-experiment" noValidate onSubmit={e => { e.preventDefault(); onStart(); }}>
      <fieldset disabled={busy || running} className="stack"><legend className="sr-only">Evolution settings</legend>
        <label className="narrow-field">Experiment mode<select value={config.mode} onChange={e => setConfig(prev => ({ ...prev, mode: e.target.value as StartEvolutionRequest['mode'] }))}><option value="live">Live LLM</option><option value="mock">Offline Demo</option></select></label>
        <p className="small muted">{config.mode === 'live' ? 'Generates new candidates with your configured provider; usage may incur costs.' : 'Predefined candidates. No live model or external API calls.'}</p>
        <details><summary>Advanced settings</summary><p className="small muted">Training examples are synthetic, single-driver plans. Each generation tests candidates and retains strategies to guide the next round.</p><div className="form-grid">{fields.map(([key, label, min, max]) => <label key={key}>{label}<input type="number" min={min} max={max} required value={config[key] || ''} onChange={e => setConfig(prev => ({ ...prev, [key]: Number(e.target.value) }))} /></label>)}
          <label>Random seed<input type="number" min="0" max="4294960000" value={config.seed ?? ''} onChange={e => setConfig(prev => ({ ...prev, seed: e.target.value === '' ? undefined : Number(e.target.value) }))} /><small>Controls training examples. Zero is a valid seed.</small></label>
          {config.mode === 'live' && <><label>Model override<input value={config.llm_model || ''} onChange={e => setConfig(prev => ({ ...prev, llm_model: e.target.value || undefined }))} placeholder="Use backend model" /></label><label>Temperature<input type="number" min="0" max="1" step="0.1" value={config.temperature ?? 0.7} onChange={e => setConfig(prev => ({ ...prev, temperature: Number(e.target.value) }))} /><small>Higher values ask the model for more varied candidates.</small></label></>}
        </div></details>
        <div><button className="button primary" type="submit">{running ? 'Experiment in progress' : 'Start experiment'}</button></div>
      </fieldset>
    </form>
    {evolution ? <EvolutionPanel evolution={evolution} onClose={() => { window.location.hash = hasInstance ? 'routes' : 'setup'; }} onApply={onApply} onCancel={onCancel} canApply={hasInstance && !busy} pollError={pollError} measurement={measurement} mode={mode} measuring={measuring} measurementError={measurementError} onMeasure={onMeasure} /> : null}
  </section>;
}
