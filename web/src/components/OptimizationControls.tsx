import type { Dispatch, SetStateAction } from 'react';
import type { OptimizationJob } from '../types/api';
import { methodNames, type Method } from '../services/workflow';
import { activeStatus, statusText } from '../services/product';

export interface Budget { operations: number; seconds: number; search_seed: number; }
export const defaultBudget: Budget = { operations: 100000, seconds: 10, search_seed: 0 };
export function OptimizationControls({ budget, setBudget, busy, job, error, onRun, onCancel }: {
  budget: Budget; setBudget: Dispatch<SetStateAction<Budget>>; busy: boolean; job: OptimizationJob | null;
  error: string | null; onRun: (method: Method) => void; onCancel: () => void;
}) {
  return <section className="panel stack optimizer" aria-label="Route optimization controls">
    <div className="section-heading"><div><p className="eyebrow">Go beyond a starting route</p><h2>Choose how to optimize</h2></div><span className="badge">Same stops. Same matrix.</span></div>
    <div className="optimizer-options">{([
      ['portfolio', 'Try trusted starting routes and keep the shortest measured construction.'],
      ['vnd', 'Improve routes with several trusted local moves.'],
      ['vnd_ils', 'Explore alternative plans after local improvements, within the same budget.'],
    ] as [Method, string][]).map(([method, description]) => <div key={method}><h3>{methodNames[method]}</h3><p>{description}</p><button className="button secondary" disabled={busy} onClick={() => onRun(method)}>Run {methodNames[method]}</button></div>)}</div>
    <details><summary>Search budget and reproducibility</summary><p className="small muted">Limits bound computation; reaching a limit is reported as incomplete. Cancellation is cooperative. Road geometry requests may take up to their network timeout to stop.</p><div className="form-grid">
      <label>Operation limit<input disabled={busy} type="number" min="0" max="500000" value={budget.operations} onChange={e => setBudget(b => ({ ...b, operations: Number(e.target.value) }))} /></label>
      <label>Solver time limit (seconds)<input disabled={busy} type="number" min="0" max="30" value={budget.seconds} onChange={e => setBudget(b => ({ ...b, seconds: Number(e.target.value) }))} /></label>
      <label>Search seed<input disabled={busy} type="number" min="0" max="4294967295" value={budget.search_seed} onChange={e => setBudget(b => ({ ...b, search_seed: Number(e.target.value) }))} /></label>
    </div></details>
    {activeStatus(job?.status) && <div className="notice busy" role="status"><span className="spinner" aria-hidden="true" />{statusText(job?.stage)} · {job?.status}. Your current routes stay visible.<button className="text-button" onClick={onCancel} disabled={job?.status === 'cancelling'}>Cancel optimization</button></div>}
    {job?.status === 'cancelled' && <p role="status" className="notice">Optimization cancelled. Previously calculated routes were retained.</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
  </section>;
}
