import { recommendedResult, comparisonMethods, type ComparisonProgress } from '../services/comparison';
import { ComparisonBars } from './ResearchVisuals';
import type { ComparisonResponse, EvolutionProgressResponse, InstanceResponse } from '../types/api';
import { differenceText, methodNames, type Method } from '../services/workflow';
import { formatDistance } from '../services/distance';
import { statusText } from '../services/product';
import { EvaluationSummary } from './EvaluationSummary';
import { PlanSelection } from './PlanSelection';

interface Props { onCompare?:()=>void; onCancelComparison?:()=>void; progress?:ComparisonProgress|null; instance: InstanceResponse; comparison: ComparisonResponse | null; loading: boolean; error: string | null;
  busy: boolean; evolution: EvolutionProgressResponse | null; appliedRunId: string | null;
  onRetry: () => void; onRun: (method: Method) => void; onView: (method: Method) => void; }
export function CompareScreen({ instance, comparison, loading, error, busy, evolution, appliedRunId, onRetry, onRun, onView, onCompare, onCancelComparison, progress }: Props) {
  const sameProblem = comparison?.instance_id === instance.instance_id &&
    (!instance.problem_fingerprint || comparison?.problem_fingerprint === instance.problem_fingerprint) &&
    (!instance.matrix_fingerprint || comparison?.matrix_fingerprint === instance.matrix_fingerprint);
  const measured = sameProblem ? comparison!.comparisons.filter(r => Number.isFinite(r.total_distance) && r.total_distance >= 0 && r.feasible !== false && r.execution?.status !== 'failed' &&
    (!instance.problem_fingerprint || r.problem_fingerprint === instance.problem_fingerprint) &&
    (!instance.matrix_fingerprint || r.matrix_fingerprint === instance.matrix_fingerprint)) : [];
  const mismatch = !!comparison && (!sameProblem || measured.length !== comparison.comparisons.length);
  const defaults=measured.filter(r=>comparisonMethods.includes(r.method as typeof comparisonMethods[number]));
  const best = recommendedResult(defaults);
  const nn = measured.find(r => r.method === 'nearest_neighbor');
  const final = measured.find(r => r.method === 'evolved');
  const methods: Method[] = ['nearest_neighbor', '2opt', 'portfolio', 'vnd', 'vnd_ils', 'strategy', ...(evolution || final ? ['evolved' as Method] : [])];
  return <section className="stack compare-screen"><div className="page-heading"><div><p className="eyebrow">Evidence, side by side</p><h1>Compare routes</h1><p>Measured on the same {instance.num_stops} stops and {instance.num_drivers} drivers. Lower distance is better.</p></div><a className="button secondary" href="#routes">Back to routes</a></div>
    <div className="panel comparison-action"><div><h2>Find a dependable route</h2><p>Compare a starting plan, a refined plan, and a trusted construction portfolio on these same stops.</p></div><button className="button primary" disabled={busy || loading} onClick={onCompare}>Run route comparison</button></div>
    {progress && <div className="notice" role="status"><strong>{progress.status}</strong><p>{progress.stage}</p>{progress.errors.map(e=><p key={e}>{e}</p>)}{['running','cancelling'].includes(progress.status)&&<button className="text-button" onClick={onCancelComparison}>Cancel comparison</button>}</div>}
    {!best && !loading && <p className="notice">No validated comparison result is available. Run or retry the comparison; diagnostics retain failed and unverified measurements.</p>}
    {loading && <p role="status">Loading comparisons...</p>}
    {error && <div className="notice error" role="alert"><p>{error}</p><button className="button secondary" onClick={onRetry}>Retry comparison</button></div>}
    {mismatch && <p className="notice error" role="alert">Unverified or mismatched results were excluded. Recalculate routes for this problem and matrix.</p>}
    {best && <section className="best-measured" aria-label="Best valid measured result"><div><p className="eyebrow">Recommended validated route</p><h2>{methodNames[best.method as Method]}</h2><strong className="best-distance">{formatDistance(best.total_distance,instance.mode)}</strong><span className={`badge ${best.execution?.status==='incomplete'?'warning':''}`}>{statusText(best.execution?.status || 'measured')}</span><p className="small muted">{best.execution?.status==='incomplete'?'Valid incumbent retained. The search stopped before completion.':'Measured on the selected problem and distance matrix.'} Completed alternatives take priority over incomplete searches. Equal distances may be shared by other methods.</p></div><div className="best-context"><p className="eyebrow">Relative to Nearest Neighbor</p><p className="best-difference">{differenceText(best.total_distance,nn?.total_distance)}</p><p className="small muted">A measured recommendation, not a claim of global optimality.</p><button className="button secondary" disabled={busy} onClick={()=>onView(best.method as Method)}>Inspect recommended routes</button></div></section>}
    <ComparisonBars rows={defaults} mode={instance.mode} onView={onView} busy={busy} />
    <div className="panel stack comparison-grid" style={{ display: 'block' }}>
      <div className="section-heading"><h2>Fleet performance</h2><span className="badge">{instance.mode === 'road' ? 'Road distances' : 'Synthetic map units'}</span></div>
      <p className="small muted">Historical Nearest Neighbor and NN + 2-Opt keep their original definitions. An incomplete search returned a validated plan within its limits; it did not complete the full search.</p>
      <div className="method-options">{comparisonMethods.map(method=>{const row=measured.find(r=>r.method===method);const rejected=sameProblem?comparison?.comparisons.find(r=>r.method===method):undefined;return <article className="method-option" key={method}><div><h3>{methodNames[method]}</h3><p>{row?formatDistance(row.total_distance,instance.mode):'No measured result'}</p><small>{row?`${statusText(row.execution?.status || 'measured')} / ${row.feasible?'Validated':'Feasibility not reported'}`:rejected?rejected.execution?.status==='failed'?'Failed evaluation':'Unverified result':'Not run'}</small></div>{row?<button className="text-button" disabled={busy} onClick={()=>onView(method)}>View {methodNames[method]} routes</button>:<a className="text-button" href="#routes">Open route controls</a>}</article>;})}</div>
      <details className="comparison-diagnostics"><summary>Advanced / Experimental methods &amp; technical diagnostics</summary>
      <div className="table-scroll"><table className="comparison-table"><caption>{instance.mode === 'road' ? 'Road distances from the selected matrix' : 'Synthetic distances in map units'} - percentages are relative to Nearest Neighbor</caption><thead><tr><th>Method</th><th>Total distance</th><th>Vs Nearest Neighbor</th><th>Longest driver</th><th>Runtime</th><th>Work</th><th>Status / feasibility</th><th>Routes</th></tr></thead><tbody>
        {methods.map(method => {
          const result = measured.find(r => r.method === method);
          const rejected=sameProblem?comparison?.comparisons.find(r=>r.method===method):undefined;
          return <tr key={method}><th scope="row">{methodNames[method]}</th><td>{result ? formatDistance(result.total_distance, instance.mode) : 'No measured result for this plan yet.'}</td>
            <td>{result ? differenceText(result.total_distance, nn?.total_distance) : 'Unavailable'}</td>
            <td>{result ? formatDistance(result.longest_route_distance, instance.mode) : 'Unavailable'}</td><td>{result ? `${result.computation_time.toFixed(3)} s` : 'Unavailable'}</td>
            <td>{result?.execution?.operations == null ? result ? 'Not instrumented' : 'Unavailable' : result.execution.operations.toLocaleString()}</td>
            <td>{result ? <><span className={`badge ${result.execution?.status === 'incomplete' ? 'warning' : ''}`}>{statusText(result.execution?.status || 'measured')}</span><small className="cell-note">{result.feasible ? 'Validated' : 'Feasibility not reported'}{result.execution?.budget_exhausted ? ' - budget exhausted' : ''}</small><small className="cell-note">{result.execution ? statusText(result.execution.termination) : ''}</small></> : rejected ? rejected.execution?.status==='failed'?'Failed evaluation':'Unverified result' : 'Not run'}</td>
            <td>{result ? <button className="text-button" disabled={busy} onClick={() => onView(method)}>View {methodNames[method]} routes</button> : method === 'strategy' || method === 'evolved' && evolution?.status !== 'completed'
              ? <a className="text-button" href="#lab">Open Strategy Experiments</a>
              : <button className="text-button" disabled={busy || loading} onClick={() => onRun(method)}>{method === 'evolved' ? 'Apply final route to this plan' : `Calculate ${methodNames[method]}`}</button>}</td></tr>;
        })}
      </tbody></table></div>
      <p className="small muted">Compute budgets differ from historical uninstrumented baselines. Runtime measures solver work; road geometry retrieval is separate. No completed-only improvement is inferred from an incomplete result.</p>
      {instance.matrix_fingerprint && <p className="small mono">Matrix {instance.matrix_fingerprint.slice(0, 16)} / problem {instance.problem_fingerprint?.slice(0, 16)}</p>}
      </details>
      {final?.optimization && <details open><summary>Legacy heuristic non-regression selection</summary><PlanSelection selection={final.optimization} distance={final.total_distance} mode={instance.mode} /></details>}
      {appliedRunId && final && <p className="small muted">Applied legacy run: {appliedRunId}</p>}
    </div>
    {best?.drivers?.length ? <section className="panel"><h2>Recommended driver routes</h2><p>{instance.num_drivers} drivers / {instance.num_stops} stops</p>{best.drivers.map(d=><div className="balance-row" key={d.driver_id}><span>Driver {d.driver_id+1} / {d.route.length-2} stops</span><strong>{formatDistance(d.distance,instance.mode)}</strong></div>)}</section>:null}
    {measured.some(r => r.drivers?.length) && <details className="panel"><summary>Advanced driver distances & workloads</summary><p className="small muted">Balanced stop counts do not guarantee equal driving distances. Compare individual routes as well as the fleet total.</p><div className="balance-grid">{measured.filter(r => r.drivers?.length).map(result => <div key={result.method}><h3>{methodNames[result.method as Method]}</h3>{result.drivers!.map(driver => <div className="balance-row" key={driver.driver_id}><span>Driver {driver.driver_id + 1} / {driver.route.length - 2} stops</span><strong>{formatDistance(driver.distance, instance.mode)}</strong><div className="balance-track" aria-hidden="true"><span style={{ width: `${result.longest_route_distance > 0 ? driver.distance / result.longest_route_distance * 100 : 0}%` }} /></div></div>)}</div>)}</div></details>}
    {evolution && <details className="panel"><summary>Legacy held-out research evaluation</summary><EvaluationSummary evolution={evolution} /></details>}
  </section>;
}
