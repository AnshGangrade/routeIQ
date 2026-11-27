import { recommendedResult } from '../services/comparison';
import type { ComparisonProgress } from '../services/comparison';
import { ComparisonBars } from './ResearchVisuals';
import type { ComparisonResponse, EvolutionProgressResponse, InstanceResponse } from '../types/api';
import { methodNames, type Method } from '../services/workflow';
import { formatDistance } from '../services/distance';
import { baselineName, completedMeasurement, savingsText } from '../services/routeEvidence';
import { statusText } from '../services/product';
import { driverColor } from '../services/presentation';
import { PageHeading, EmptyState, Icon } from './Design';
import { EvaluationSummary } from './EvaluationSummary';
import { PlanSelection } from './PlanSelection';
interface Props { onCompare?:()=>void; onCancelComparison?:()=>void; progress?:ComparisonProgress|null; instance: InstanceResponse; comparison: ComparisonResponse | null; loading: boolean; error: string | null;
  busy: boolean; evolution: EvolutionProgressResponse | null; appliedRunId: string | null;
  onRetry: () => void; onRun: (method: Method) => void; onView: (method: Method) => void; }

export function CompareScreen({instance,comparison,loading,error,busy,evolution,onRetry,onRun,onView,onCompare,onCancelComparison,progress}:Props) {
  const same=comparison?.instance_id===instance.instance_id && comparison.problem_fingerprint===instance.problem_fingerprint && comparison.matrix_fingerprint===instance.matrix_fingerprint;
  const rows=comparison?.comparisons||[];
  const complete=same?rows.filter(r=>completedMeasurement(instance,r)):[];
  const best=recommendedResult(complete,instance);
  const baseline=complete.find(r=>r.method==='nearest_neighbor');
  const diagnosticGroups=[
    {title:'Completed and verified results',rows:complete},
    {title:'Feasible but incomplete measurements',rows:rows.filter(r=>same && r.server_verified && r.execution?.status==='incomplete')},
    {title:'Failed evaluations',rows:rows.filter(r=>['failed','cancelled','interrupted'].includes(r.execution?.status||''))},
    {title:'Unverified or mismatched records',rows:rows.filter(r=>!complete.includes(r) && !(same && r.server_verified && r.execution?.status==='incomplete') && !['failed','cancelled','interrupted'].includes(r.execution?.status||''))}
  ];
  const view=(method:Method)=>{if(complete.some(r=>r.method===method))onView(method);};
  return <section className="stack compare-screen">
    <PageHeading eyebrow="Route intelligence" title="Compare routes" description={`One plan. ${instance.num_stops} stops. ${instance.num_drivers} drivers. Compare completed routes on the same distance matrix.`} action={<a className="button secondary" href="#routes">Back to routes <Icon name="arrow" size={16}/></a>}/>
    <div className="panel comparison-action"><div><h2>Find your best completed route</h2><p>Compare Nearest Neighbor, 2-Opt and the trusted construction portfolio.</p></div><button className="button primary" disabled={busy||loading} onClick={onCompare}><Icon name="compare" size={18}/>Run route comparison</button></div>
    {progress && <div className="notice" role="status"><strong>{statusText(progress.status)}</strong><p>{progress.stage}</p>{progress.errors.map(e=><p key={e}>{e}</p>)}{['running','cancelling'].includes(progress.status)&&<button className="text-button" onClick={onCancelComparison}>Cancel comparison</button>}</div>}
    {loading && <div className="panel loading-state" role="status"><span className="spinner"/>Verifying comparison results...</div>}
    {error && <div className="notice error" role="alert"><p>{error}</p><button className="button secondary" onClick={onRetry}>Retry comparison</button></div>}
    {!best&&!loading&&<EmptyState title="No completed validated route is available yet." description="Run a comparison or complete a route search. Earlier incomplete measurements remain in Technical diagnostics."/>}
    {best&&<section className="best-measured" aria-label="Best completed validated result"><div><span className="badge success"><Icon name="check" size={14}/>Completed and verified</span><p className="eyebrow">Best completed route</p><h2>{methodNames[best.method as Method]||best.method}</h2><strong className="best-distance">{formatDistance(best.total_distance,instance.mode)}</strong><p className="small muted">Total fleet distance / {instance.mode==='road'?'road matrix':'synthetic coordinates'}</p></div><div className="best-context"><p className="eyebrow">Baseline: {baselineName}</p><p className="best-difference">{savingsText(instance,best,baseline)}</p><p className="small muted">Same stops, drivers and workload. A measured result, not proof of optimality.</p><button className="button primary" disabled={busy} onClick={()=>view(best.method as Method)}>Inspect recommended routes <Icon name="arrow" size={16}/></button></div></section>}
    {!!complete.length&&<><ComparisonBars rows={complete} mode={instance.mode} onView={view} busy={busy}/><section className="panel comparison-grid"><div className="section-heading"><h2>Completed methods</h2><span className="badge">{complete.length} verified</span></div><div className="method-options">{complete.map(r=><article className="method-option" key={r.method}><div><h3>{methodNames[r.method as Method]||r.method}</h3><p>{formatDistance(r.total_distance,instance.mode)}</p><small>{savingsText(instance,r,baseline)}</small></div><button className="text-button" disabled={busy} onClick={()=>view(r.method as Method)}>View {methodNames[r.method as Method]} routes</button></article>)}</div></section></>}
    {best&&<section className="panel driver-comparison"><div className="section-heading"><div><h2>Recommended driver routes</h2><p className="small muted">Workload and distance for the recommended completed plan.</p></div><span className="badge">Longest: {formatDistance(best.longest_route_distance,instance.mode)}</span></div><div className="driver-metrics">{best.drivers!.map(d=><div className="driver-metric" key={d.driver_id}><span className="driver-dot" style={{background:driverColor(d.driver_id)}}/><h3>Driver {d.driver_id+1}</h3><strong>{formatDistance(d.distance,instance.mode)}</strong><span>{d.route.length-2} stops</span><div className="balance-track"><span style={{background:driverColor(d.driver_id),width:`${best.longest_route_distance?d.distance/best.longest_route_distance*100:0}%`}}/></div></div>)}</div></section>}
    <details className="panel comparison-diagnostics"><summary>Technical diagnostics <span className="badge">{rows.length} records</span></summary><p className="small muted">Incomplete, failed and unverified measurements are not recommendations and cannot be selected as current routes. Raw figures below are retained for diagnosis.</p>
      {diagnosticGroups.map(group=><section key={group.title} className="diagnostic-group"><h3>{group.title}</h3>{!group.rows.length?<p className="small muted">No records.</p>:<div className="table-scroll"><table><caption>{group.title} / {instance.mode==='road'?'meters or kilometers':'map units'}</caption><thead><tr><th>Method</th><th>Distance</th><th>Longest route</th><th>Status / termination</th><th>Runtime / work</th></tr></thead><tbody>{group.rows.map((r,i)=><tr key={r.method+i}><th>{methodNames[r.method as Method]||r.method}</th><td>{formatDistance(r.total_distance,instance.mode)}</td><td>{formatDistance(r.longest_route_distance,instance.mode)}</td><td>{statusText(r.execution?.status)}<small className="cell-note">{statusText(r.execution?.termination)}{r.execution?.budget_exhausted?' / budget exhausted':''}</small></td><td>{r.computation_time.toFixed(3)} s<small className="cell-note">{r.execution?.operations??'Uninstrumented'} operations</small></td></tr>)}</tbody></table></div>}</section>)}
      <p className="small muted">Budgets differ from historical uninstrumented baselines. Runtime excludes road geometry retrieval.</p><p className="small mono">Problem {instance.problem_fingerprint} / matrix {instance.matrix_fingerprint}</p>
      <div className="actions">{(['nearest_neighbor','2opt','portfolio','vnd','vnd_ils'] as Method[]).map(method=><button className="button secondary" disabled={busy||loading} key={method} onClick={()=>onRun(method)}>Calculate {methodNames[method]}</button>)}</div>
      {rows.filter(r=>r.optimization).map(r=><PlanSelection key={r.method} selection={r.optimization!} distance={r.total_distance} mode={instance.mode}/>)}
      {evolution&&<EvaluationSummary evolution={evolution}/>}
    </details>
  </section>;
}
