import type { StrategyExperiment, StrategyRecord, MethodComparison } from '../types/api';
import { finiteSeries, sourceLabel } from '../services/presentation';
import { formatDistance } from '../services/distance';
import { methodNames, type Method } from '../services/workflow';
import { Icon, Tip } from './Design';

export function ComparisonBars({ rows, mode, onView, busy }: { rows: MethodComparison[]; mode: string; onView: (method: Method)=>void; busy: boolean }) {
  const values = rows.filter(r=>Number.isFinite(r.total_distance) && r.total_distance>=0);
  if (!values.length) return null;
  const max = Math.max(...values.map(r=>r.total_distance));
  return <section className="distance-landscape" aria-label="Measured fleet distance chart"><div><p className="eyebrow">A shorter line. A shorter route.</p><h2>See the distance.</h2><p>Same problem. Same matrix.<br/>Lower total distance is better.</p><span className="chart-key"><i/> Measured distance <Tip text="Bars start at zero. An incomplete search can have a feasible route, but has not finished its search."/></span></div><div className="distance-bars">{values.map(r=><button disabled={busy} className="distance-bar-row" key={r.method} onClick={()=>onView(r.method as Method)} aria-label={`Inspect ${methodNames[r.method as Method]}: ${formatDistance(r.total_distance,mode)}; ${r.execution?.status || 'measured'}`}><span>{methodNames[r.method as Method]}</span><strong>{formatDistance(r.total_distance,mode)}</strong><span className="distance-track"><span style={{width:`${max ? r.total_distance/max*100:0}%`}} className={r.execution?.status==='incomplete'?'incomplete':''}/></span>{r.execution?.status==='incomplete' && <small>Incomplete search</small>}</button>)}</div></section>;
}

export function FitnessPlot({ history }: { history: NonNullable<StrategyExperiment['history']> }) {
  const stats=finiteSeries(history.map(h=>h.best_so_far));
  if (!stats.count) return <div className="chart-empty"><Icon name="compare" size={30}/><p>No measured fitness yet.</p><small>Points appear after evaluated generations. Lower distance is better.</small></div>;
  const span=stats.max-stats.min || Math.max(stats.max*.1,1);
  const lower=Math.max(0,stats.min-span*.15), upper=stats.max+span*.15;
  const x=(i:number)=>65+(history.length>1?i/(history.length-1)*480:240);
  const y=(v:number)=>165-(v-lower)/(upper-lower)*135;
  let connected=false;
  const path=history.map((h,i)=>{if(h.best_so_far==null || !Number.isFinite(h.best_so_far) || h.best_so_far<0){connected=false;return '';}const command=connected?'L':'M';connected=true;return `${command}${x(i)},${y(h.best_so_far)}`;}).join(' ');
  return <svg viewBox="0 0 600 215" className="fitness-plot" role="img" aria-label="Best-so-far development mean distance by generation, lower is better">
    <title>Observed development fitness, map units. Missing observations are not interpolated.</title>
    {[lower,(lower+upper)/2,upper].map(v=><g key={v}><line x1="65" x2="545" y1={y(v)} y2={y(v)} stroke="#d6d9ce" strokeDasharray="3 5"/><text x="54" y={y(v)+4} textAnchor="end">{v.toFixed(1)}</text></g>)}
    <path d={path} fill="none" stroke="#287776" strokeWidth="2.5"/>
    {history.map((h,i)=>h.best_so_far!=null && Number.isFinite(h.best_so_far) && h.best_so_far>=0 ? <g key={h.generation}><circle cx={x(i)} cy={y(h.best_so_far)} r="5" fill="#f8f4e8" stroke="#287776" strokeWidth="2"><title>{`Generation ${h.generation+1}: ${h.best_so_far.toFixed(2)} map units`}</title></circle><text x={x(i)} y="195" textAnchor="middle">G{h.generation+1}</text></g>:null)}
  </svg>;
}

export function Lineage({ records, bestId, offline }: { records: StrategyRecord[]; bestId?: string | null; offline: boolean }) {
  if (!records.length) return <p className="muted">Lineage appears when the experiment records candidates.</p>;
  const generations=[...new Set(records.map(r=>r.generation))].sort((a,b)=>a-b);
  const positions=new Map<string,[number,number]>();
  generations.forEach((g,col)=>records.filter(r=>r.generation===g).forEach((r,row)=>positions.set(r.strategy_id,[col*210+30,row*57+45])));
  const height=Math.max(...[...positions.values()].map(p=>p[1]))+65;
  const width=Math.max(600,generations.length*210+30);
  return <div className="lineage-scroll" tabIndex={0} role="region" aria-label="Strategy lineage diagram, scroll to explore"><svg width={width} height={height} role="img" aria-label="Candidate lineage from recorded parent identifiers">
    {generations.map((g,i)=><text className="lineage-generation" key={g} x={i*210+30} y="18">GENERATION {g + 1}</text>)}
    {records.flatMap(r=>r.parents.map(parent=>{const from=positions.get(parent),to=positions.get(r.strategy_id);return from && to ? <path key={parent+r.strategy_id} d={`M${from[0]+160},${from[1]+16}C${from[0]+185},${from[1]+16} ${to[0]-25},${to[1]+16} ${to[0]},${to[1]+16}`} fill="none" stroke="#aab4ab" strokeWidth="1.2"/>:null;}))}
    {records.map(r=>{const [x,y]=positions.get(r.strategy_id)!;return <g key={r.strategy_id} transform={`translate(${x} ${y})`}><title>{`${r.strategy_id}; ${sourceLabel(r.creation_method,offline)}; parents: ${r.parents.join(', ')||'none'}`}</title><rect width="160" height="35" rx="5" fill={r.strategy_id===bestId?'#e1ebe0':'#fffdf6'} stroke={r.strategy_id===bestId?'#287776':'#d5cebe'}/><circle cx="12" cy="17" r="3" fill={r.creation_method==='llm'?'#806a9c':r.creation_method==='seed'?'#b95e42':'#287776'}/><text x="23" y="14">{sourceLabel(r.creation_method,offline).replace('Offline fixture (not an LLM)','Offline fixture')}</text><text className="node-id" x="23" y="27">{r.strategy_id.slice(-12)}</text></g>;})}
  </svg></div>;
}

export function CandidateComparison({ records, offline }: { records: StrategyRecord[]; offline: boolean }) {
  if (!records.length) return null;
  return <details className="candidate-comparison"><summary>Compare measured candidates <span className="badge">{records.length}</span></summary><p className="small muted">Development evaluations only. Ineligible candidates cannot be selected as improvements. Work and runtime are reported separately.</p><div className="table-scroll" tabIndex={0} role="region" aria-label="Candidate measurements"><table><thead><tr><th>Candidate / source</th><th>Mean distance</th><th>Eligibility</th><th>Completed / incomplete / failed</th><th>Work</th><th>Runtime</th></tr></thead><tbody>{records.map(r=><tr key={r.strategy_id}><th><span className="mono" title={r.strategy_id}>{r.strategy_id.slice(-12)}</span><small>{sourceLabel(r.creation_method,offline)}</small></th><td>{r.fitness.mean_distance!=null && Number.isFinite(r.fitness.mean_distance) ? `${r.fitness.mean_distance.toFixed(2)} map units` : 'Unavailable'}</td><td><span className={`badge ${r.fitness.eligible?'':'warning'}`}>{r.fitness.eligible==null?'Pending evaluation':r.fitness.eligible?'Eligible':'Ineligible'}</span></td><td>{r.fitness.completed ?? '?'} / {r.fitness.incomplete ?? '?'} / {r.fitness.failed ?? '?'}</td><td>{Number.isFinite(r.fitness.operations)?r.fitness.operations.toLocaleString():'Unavailable'}</td><td>{Number.isFinite(r.fitness.seconds)?`${r.fitness.seconds.toFixed(3)} s`:'Unavailable'}</td></tr>)}</tbody></table></div></details>;
}

export function ResearchVisuals({ state }: { state: StrategyExperiment | null }) {
  const records=Object.values(state?.records || {}), history=state?.history || [];
  return <section className="research-observatory" aria-label="Experiment visual evidence"><div className="section-heading"><div><p className="eyebrow">The research notebook</p><h2>Follow the search.</h2></div><span className="badge">Development data</span></div>
    <div className="research-grid"><div className="fitness-card"><div className="section-heading"><h3>Fitness progression</h3><Tip text="Fitness is mean fleet distance across the configured development cases. It is not the distance of your delivery plan."/></div><FitnessPlot history={history}/></div><div className="generation-card"><h3>Generation timeline</h3>{history.length ? <ol className="generation-timeline">{history.map(h=><li key={h.generation}><span>G{h.generation+1}</span><div><strong>{h.unique_configurations} configurations</strong><small>{h.behavioral_diversity} distinct route behaviors</small><small>{h.best_so_far==null?'No eligible fitness':`${h.best_so_far.toFixed(2)} map units`}</small></div></li>)}</ol>:<p className="muted small">No evaluated generations. Start an experiment to see how configurations and routing behavior change.</p>}</div></div>
    <CandidateComparison records={records} offline={state?.manifest?.provider_mode==='offline'}/>
    <details className="lineage-panel"><summary>Strategy lineage <span className="badge">{records.length} candidates</span></summary><p className="small muted">Links show recorded parents. Independent proposals have no parent link; source labels identify how each configuration was created.</p><Lineage records={records} bestId={state?.best_id} offline={state?.manifest?.provider_mode==='offline'}/></details>
    <div className="evaluation-stages"><div><span>01 / DEVELOPMENT</span><strong>{state ? 'Training evidence above' : 'Awaiting an experiment'}</strong><small>Used to guide this search.</small></div><div><span>02 / VALIDATION</span><strong>Not supplied by this API</strong><small>Controlled selection remains in the research CLI.</small></div><div><span>03 / HELD-OUT</span><strong>No new held-out evaluation</strong><small>Historical LLM evidence is incomplete. No superiority claim.</small></div></div>
  </section>;
}
