import { PlanningWorkspace } from './components/PlanningWorkspace';
import { draftIdentity } from './services/planning';
import { ComparisonRun, type ComparisonProgress } from './services/comparison';
import { Home } from './components/Home';
import { BrandMark, Icon, ConfirmationProvider } from './components/Design';
import { useEffect, useRef, useState } from 'react';
import { CompareScreen } from './components/CompareScreen';
import { StrategyLab } from './components/StrategyLab';
import { defaultBudget } from './components/OptimizationControls';
import { activeStatus, watchTask, completedOptimizationResult, validateCompletedResult } from './services/product';
import { api } from './services/api';
import { generatePlan, initialPlan, methodNames, viewFromHash } from './services/workflow';
import type { Method, View } from './services/workflow';
import type { ComparisonResponse, InstanceResponse, RoutingResultResponse, HybridMethod, OptimizationJob } from './types/api';

function App() {
  const [comparisonProgress,setComparisonProgress]=useState<ComparisonProgress|null>(null);
  const comparisonTask=useRef<ComparisonRun|null>(null);
  const [view, setView] = useState<View>(() => viewFromHash(window.location.hash));
  const [labVisited, setLabVisited] = useState(() => viewFromHash(window.location.hash) === 'lab');
  const [strategyStatus, setStrategyStatus] = useState<string | null>(null);
  const [budget, setBudget] = useState(defaultBudget);
  const [optimization, setOptimization] = useState<OptimizationJob | null>(null);
  const [optimizationId, setOptimizationId] = useState<string | null>(null);
  const [optimizationError, setOptimizationError] = useState<string | null>(null);
  const [submittedDraft, setSubmittedDraft] = useState<string | null>(null);
  const optimizationRef = useRef<string | null>(null);
  const [draft, setDraft] = useState(initialPlan);
  const [planVisited,setPlanVisited]=useState(()=>['setup','routes'].includes(viewFromHash(window.location.hash)));
  const [instance, setInstance] = useState<InstanceResponse | null>(null);
  const [results, setResults] = useState(new Map<string, RoutingResultResponse>());
  const [method, setMethod] = useState<Method>('nearest_neighbor');
  const [driver, setDriver] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const busyRef = useRef(false);
  const instanceRef = useRef<string | null>(null);
  const main = useRef<HTMLElement>(null);
  const currentResult = results.get(method) || null;
  const optimizing = activeStatus(optimization?.status);
  const comparing=!!comparisonProgress && ['running','cancelling'].includes(comparisonProgress.status);
  const busyNow = !!busy || optimizing || comparing;
  const draftSignature = draftIdentity(draft);
  const draftChanged = !!instance && submittedDraft !== draftSignature;
  const navigate = (next: View) => { window.location.hash = next; setView(next); };
  useEffect(() => { const changed = () => setView(viewFromHash(window.location.hash)); window.addEventListener('hashchange', changed); return () => window.removeEventListener('hashchange', changed); }, []);
  useEffect(() => { main.current?.focus(); }, [view]);
  useEffect(()=>{if(view==='setup'||view==='routes')setPlanVisited(true);},[view]);
  useEffect(() => { if (view === 'lab') setLabVisited(true); }, [view]);
  useEffect(() => {
    if (!optimizationId || !instance) return;
    return watchTask(optimizationId, api.optimizationStatus, progress => {
      if (optimizationRef.current !== progress.job_id || instanceRef.current !== progress.instance_id) return;
      if (instance.problem_fingerprint && progress.problem_fingerprint !== instance.problem_fingerprint ||
          instance.matrix_fingerprint && progress.matrix_fingerprint !== instance.matrix_fingerprint)
        throw new Error('Optimization result uses another problem matrix.');
      setOptimizationError(null); setOptimization(progress);
      if (progress.status === 'failed') setOptimizationError(progress.error || 'Optimization failed. Your earlier routes were retained.');
      if (progress.status==='incomplete') setOptimizationError('No new completed result was produced. Your previous completed routes were retained.');
      const published=completedOptimizationResult(instance,progress);
      if (published) {
        setResults(previous => new Map(previous).set(progress.method, published)); setMethod(progress.method); setDriver(null);
      }
    }, (message, terminal) => {
      if (optimizationRef.current !== optimizationId) return;
      setOptimizationError(`Progress unavailable: ${message} ${terminal ? 'The job is no longer available. Create a new plan if the server restarted.' : 'Retrying automatically.'}`);
      if (terminal) setOptimization(previous => previous ? { ...previous, status: 'failed', stage: 'finished', error: message } : previous);
    });
  }, [optimizationId, instance]);
  useEffect(() => {
    if (view !== 'compare' || !instance) return;
    let current = true;
    setComparison(null); setComparisonError(null); setComparisonLoading(true);
    api.getComparison(instance.instance_id).then(response => {
      if (!current) return;
      if (response.instance_id !== instance.instance_id) throw new Error('The server returned a comparison for another plan.');
      setComparison(response);
    }).catch(reason => { if (current) setComparisonError(reason instanceof Error ? reason.message : 'Comparison unavailable. Calculate a route and retry.'); })
      .finally(() => { if (current) setComparisonLoading(false); });
    return () => { current = false; };
  }, [view, instance, results, refresh]);

  const perform = async (message: string, action: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(message); setError(null);
    try { await action(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'This action could not be completed. Please retry.'); }
    finally { busyRef.current = false; setBusy(null); }
  };
  const runComparison = async () => {
    if (!instance || draftChanged || busyNow || comparisonTask.current) return;
    const selected=instance.instance_id;
    const task=new ComparisonRun(instance,p=>{if(instanceRef.current===selected)setComparisonProgress(p);},row=>{
      if(instanceRef.current!==selected)return;
      setResults(previous=>new Map(previous).set(row.method,row));
    });
    comparisonTask.current=task;
    try { await task.run(); } finally { if(comparisonTask.current===task)comparisonTask.current=null; }
  };
  const cancelComparison=()=>{void comparisonTask.current?.cancel().catch(e=>setComparisonError(e instanceof Error?e.message:'Cancellation failed; retry.'));};
  const create = () => perform('Creating your plan…', async () => {
    if (optimizing) throw new Error('Finish or cancel the current optimization first.');
    const plan = await generatePlan(draft, setBusy);
    optimizationRef.current = null; setOptimizationId(null); setOptimization(null); setOptimizationError(null);
    instanceRef.current = plan.instance.instance_id;
    setComparisonProgress(null); setInstance(plan.instance); setResults(plan.results); setDriver(null);
    setSubmittedDraft(draftSignature);
    const shortest = [...plan.results.values()].sort((a, b) => a.total_distance - b.total_distance)[0];
    setMethod((shortest?.method || 'nearest_neighbor') as Method);
    setError(plan.errors.length ? `Your plan was created, but some routes could not be calculated. ${plan.errors.join(' ')}` : null);
    navigate('routes');
  });
  const optimize = (selected: HybridMethod, strategyJob?: string, strategyId?: string) => perform('Starting bounded optimization…', async () => {
    if (!instance || draftChanged || optimizing) throw new Error('Select a plan and finish any active optimization first.');
    if (!Number.isInteger(budget.operations) || budget.operations < 0 || budget.operations > 500000 || !Number.isFinite(budget.seconds) || budget.seconds < 0 || budget.seconds > 30 || !Number.isInteger(budget.search_seed) || budget.search_seed < 0 || budget.search_seed > 4294967295)
      throw new Error('Use 0–500,000 operations, 0–30 seconds, and a whole-number search seed.');
    const response = await api.startOptimization({ instance_id: instance.instance_id, method: selected, search_seed:budget.search_seed,
      ...(selected==='strategy' ? {} : {operations:budget.operations,seconds:budget.seconds}),
      ...(selected === 'adaptive' ? {adaptive:{provider:{model:budget.adaptiveModel || 'qwen3:1.7b',temperature:.3,timeout:5,retries:0,max_tokens:768},experience_job_ids:(budget.experienceJobs || '').split(',').map(s=>s.trim()).filter(Boolean)}} : {}),
      ...(selected === 'strategy' ? { strategy_job_id: strategyJob, strategy_id: strategyId } : {}) });
    if (response.instance_id !== instanceRef.current || response.method !== selected) throw new Error('Optimization started for an unexpected plan.');
    optimizationRef.current = response.job_id; setOptimization(response); setOptimizationError(null); setOptimizationId(response.job_id);
    if (selected === 'strategy') navigate('routes');
  });
  const cancelOptimization = async () => {
    if (!optimizationId) return;
    try {
      const response = await api.cancelOptimization(optimizationId);
      if (optimizationRef.current !== optimizationId) return;
      if (response.job_id !== optimizationId || response.instance_id !== instanceRef.current) throw new Error('Unexpected cancellation identity.');
      setOptimization(previous => previous ? { ...previous, status: response.status } : previous);
    } catch (reason) { setOptimizationError(reason instanceof Error ? reason.message : 'Cancellation failed. Retry.'); }
  };
  const solve = (selected: Method) => {
    if (['portfolio', 'vnd', 'vnd_ils', 'adaptive'].includes(selected)) return optimize(selected as HybridMethod);
    if (selected === 'strategy' || selected === 'evolved') { navigate('lab'); return; }
    return perform(`Calculating ${methodNames[selected]} routes…`, async () => {
    if (!instance || draftChanged) throw new Error('Generate the current draft before calculating routes.');
    if (optimizing) throw new Error('Finish or cancel the current optimization first.');
    const result = await api.solveRouting({ instance_id: instance.instance_id, method: selected as 'nearest_neighbor' | '2opt' });
    validateCompletedResult(instance, result);
    if (result.instance_id !== instanceRef.current || result.method !== selected) throw new Error('The returned route does not match the selected plan. Please retry.');
    setResults(previous => new Map(previous).set(selected, result)); setMethod(selected); setDriver(null);
    navigate('routes');
  }); };
  const emptyPlan = draftChanged ? <div className="panel empty-state"><h1>Draft changes need a new plan</h1><p>Generate the edited plan before comparing routes.</p><a className="button primary" href="#routes">Review Route Plan</a></div> : <div className="panel empty-state"><p className="eyebrow">Start with your deliveries</p><h1>No route plan yet</h1><p>Create a plan before viewing routes or comparing methods.</p><a className="button primary" href="#setup">Create route plan</a></div>;

  return <ConfirmationProvider><div className={`app-shell workspace-shell view-${view}`}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); main.current?.focus(); }}>Skip to content</a>
    <header className="app-header"><a href="#home" className="brand" aria-label="RouteIQ home"><BrandMark /><span>Route<span className="brand-iq">IQ</span></span></a><nav aria-label="Main navigation">
      {([['home', 'Home'], ['routes', 'Route Plan'], ['compare', 'Compare'], ['lab', 'Evolution']] as [View, string][]).map(([target, title]) => <a key={title} title={title} href={`#${target}`} aria-current={view === target || title === 'Route Plan' && view === 'setup' ? 'page' : undefined}><Icon name={title === "Home" ? "home" : title === "Route Plan" ? "map" : title === "Compare" ? "compare" : "lab"} size={17}/><span>{title}</span>{title === 'Evolution' && strategyStatus && <span className="live-dot" aria-label="Experiment running" />}</a>)}
    </nav>
    <div className="context-bar"><span>{instance ? `${draftChanged ? 'Saved ' : ''}${instance.mode === 'road' ? 'Road' : 'Demo'} plan · ${instance.num_stops} stops · ${instance.num_drivers} drivers` : (view === 'setup' || view === 'routes') ? 'Draft plan' : 'No plan selected'}</span>{instance && <span className="instance-id" title={instance.instance_id}>Plan {instance.instance_id.slice(-8)}</span>}{comparing && <a href="#compare">Route comparison / {comparisonProgress?.status}</a>}{optimizing && <a href="#routes">Optimization · {optimization?.status}</a>}{strategyStatus && <a href="#lab">Strategy experiment · {strategyStatus}</a>}</div></header>
    <main id="main-content" ref={main} tabIndex={-1} className="app-main">
      {busy && <p role="status" className="notice busy">{busy} Your settings are preserved.</p>}
      {error && <div className="notice error" role="alert"><p>{error}</p><button className="text-button" onClick={() => setError(null)}>Dismiss message</button></div>}
      {draftChanged && view !== 'routes' && view !== 'setup' && <p className="notice" role="status">You have unapplied setup changes. Displayed results still belong to the saved plan. <a className="text-button" href="#setup">Review and generate a new plan</a></p>}
      {view === 'home' && <Home hasInstance={!!instance} instance={instance} stale={draftChanged} />}
      {planVisited && <div className="planning-host" hidden={view!=='setup'&&view!=='routes'}><PlanningWorkspace draft={draft} setDraft={setDraft} instance={instance} result={currentResult} results={results} stale={draftChanged} busy={busyNow} method={method} onMethod={value=>{setMethod(value);setDriver(null);}} driver={driver} onDriver={setDriver} onGenerate={create} onRun={solve} budget={budget} setBudget={setBudget} job={optimization} optimizationError={optimizationError} onCancel={cancelOptimization}/></div>}
      {view === 'compare' && (instance && !draftChanged ? <CompareScreen onCompare={runComparison} onCancelComparison={cancelComparison} progress={comparisonProgress} instance={instance} comparison={comparison} loading={comparisonLoading} error={comparisonError} busy={busyNow} evolution={null} appliedRunId={null} onRetry={() => setRefresh(value => value + 1)} onRun={solve} onView={value => { if (results.has(value)) { setMethod(value); setDriver(null); navigate('routes'); } else void solve(value); }} /> : emptyPlan)}
      {labVisited && <div hidden={view !== 'lab'}><StrategyLab hasInstance={!!instance && !draftChanged} applying={busyNow} onApply={(job, candidate) => optimize('strategy', job, candidate)} onStatus={setStrategyStatus} /></div>}
    </main><footer className="app-footer"><span>RouteIQ · Delivery route planning</span></footer>
  </div></ConfirmationProvider>;
}
export default App;
