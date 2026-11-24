import { ComparisonRun, type ComparisonProgress } from './services/comparison';
import { Home } from './components/Home';
import { BrandMark, Icon, ConfirmationProvider } from './components/Design';
import { useEffect, useRef, useState } from 'react';
import { SetupWizard } from './components/SetupWizard';
import { RouteVisualization } from './components/RouteVisualization';
import { CompactResults } from './components/CompactResults';
import { DriverDetailsPanel } from './components/DriverDetailsPanel';
import { CompareScreen } from './components/CompareScreen';
import { StrategyLab } from './components/StrategyLab';
import { OptimizationControls, defaultBudget } from './components/OptimizationControls';
import { OptimizationDetails } from './components/OptimizationDetails';
import { activeStatus, validateRouteResult, watchTask } from './services/product';
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
  const [step, setStep] = useState(0);
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
  const draftSignature = JSON.stringify([draft.mode, draft.numStops, draft.numDrivers, draft.seed, draft.layout,
    draft.mode === 'road' ? [draft.depotLon, draft.depotLat, draft.stops] : null, draft.workloadMode || 'balanced']);
  const draftChanged = !!instance && submittedDraft !== draftSignature;
  const navigate = (next: View) => { window.location.hash = next; setView(next); };
  useEffect(() => { const changed = () => setView(viewFromHash(window.location.hash)); window.addEventListener('hashchange', changed); return () => window.removeEventListener('hashchange', changed); }, []);
  useEffect(() => { main.current?.focus(); }, [view, step]);
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
      if (progress.result && ['completed', 'incomplete'].includes(progress.status)) {
        validateRouteResult(instance, progress.result);
        if (progress.result.method !== progress.method) throw new Error('Unexpected optimization method.');
        setResults(previous => new Map(previous).set(progress.method, progress.result!)); setMethod(progress.method); setDriver(null);
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
    if (!instance || busyNow || comparisonTask.current) return;
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
    if (!instance || optimizing) throw new Error('Select a plan and finish any active optimization first.');
    if (!Number.isInteger(budget.operations) || budget.operations < 0 || budget.operations > 500000 || !Number.isFinite(budget.seconds) || budget.seconds < 0 || budget.seconds > 30 || !Number.isInteger(budget.search_seed) || budget.search_seed < 0 || budget.search_seed > 4294967295)
      throw new Error('Use 0–500,000 operations, 0–30 seconds, and a whole-number search seed.');
    const response = await api.startOptimization({ instance_id: instance.instance_id, method: selected, ...budget,
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
    if (['portfolio', 'vnd', 'vnd_ils'].includes(selected)) return optimize(selected as HybridMethod);
    if (selected === 'strategy' || selected === 'evolved') { navigate('lab'); return; }
    return perform(`Calculating ${methodNames[selected]} routes…`, async () => {
    if (!instance) throw new Error('Create a route plan first.');
    if (optimizing) throw new Error('Finish or cancel the current optimization first.');
    const result = await api.solveRouting({ instance_id: instance.instance_id, method: selected as 'nearest_neighbor' | '2opt' });
    validateRouteResult(instance, result);
    if (result.instance_id !== instanceRef.current || result.method !== selected) throw new Error('The returned route does not match the selected plan. Please retry.');
    setResults(previous => new Map(previous).set(selected, result)); setMethod(selected); setDriver(null);
    navigate('routes');
  }); };
  const emptyPlan = <div className="panel empty-state"><p className="eyebrow">Start with your deliveries</p><h1>No route plan yet</h1><p>Create a plan before viewing routes or comparing methods.</p><a className="button primary" href="#setup">Create route plan</a></div>;

  return <ConfirmationProvider><div className={`app-shell view-${view}`}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); main.current?.focus(); }}>Skip to content</a>
    <header className="app-header"><a href="#home" className="brand" aria-label="RouteIQ home"><BrandMark /><span>Route<span className="brand-iq">IQ</span></span></a><nav aria-label="Main navigation">
      {([['home', 'Home'], [instance ? 'routes' : 'setup', 'Route Plan'], ['compare', 'Compare'], ['lab', 'Strategy Experiments']] as [View, string][]).map(([target, title]) => <a key={title} href={`#${target}`} aria-current={view === target || title === 'Route Plan' && view === 'setup' ? 'page' : undefined}><Icon name={title === "Home" ? "home" : title === "Route Plan" ? "map" : title === "Compare" ? "compare" : "lab"} size={17}/><span>{title}</span>{title === 'Strategy Experiments' && strategyStatus && <span className="live-dot" aria-label="Experiment running" />}</a>)}
    </nav><span className="header-note">Delivery planning, made clearer.</span></header>
    <div className="context-bar"><span>{instance ? `${instance.mode === 'road' ? 'Road' : 'Demo'} plan · ${instance.num_stops} stops · ${instance.num_drivers} drivers` : view === 'setup' ? `Draft plan · Step ${step + 1} of 4` : 'No plan selected'}</span>{instance && <span className="instance-id" title={instance.instance_id}>Plan {instance.instance_id.slice(-8)}</span>}{comparing && <a href="#compare">Route comparison / {comparisonProgress?.status}</a>}{optimizing && <a href="#routes">Optimization · {optimization?.status}</a>}{strategyStatus && <a href="#lab">Strategy experiment · {strategyStatus}</a>}</div>
    <main id="main-content" ref={main} tabIndex={-1} className="app-main">
      {busy && <p role="status" className="notice busy">{busy} Your settings are preserved.</p>}
      {error && <div className="notice error" role="alert"><p>{error}</p><button className="text-button" onClick={() => setError(null)}>Dismiss message</button></div>}
      {draftChanged && <p className="notice" role="status">You have unapplied setup changes. Displayed results still belong to the saved plan. <a className="text-button" href="#setup">Review and generate a new plan</a></p>}
      {view === 'home' && <Home hasInstance={!!instance} />}
      {view === 'setup' && <SetupWizard draft={draft} setDraft={setDraft} step={step} setStep={setStep} onGenerate={create} busy={busyNow} hasInstance={!!instance} />}
      {view === 'routes' && (instance ? <section className="stack routes-workspace"><div className="page-heading"><div><p className="eyebrow">Your delivery plan</p><h1>Routes, ready to explore.</h1><p>Select a driver to see their stops and route.</p></div><div className="actions"><button className="button secondary" onClick={() => { setStep(0); navigate('setup'); }}>Edit plan</button><a className="button primary" href="#compare">Compare routes</a></div></div>
        {currentResult && <CompactResults instance={instance} result={currentResult} results={results} />}
        <div className="route-layout"><RouteVisualization instance={instance} routingResult={currentResult} selectedMethod={method} onMethodSelect={value => { setMethod(value as Method); setDriver(null); }} availableMethods={[...results.keys()]} selectedDriverId={driver} onDriverSelect={setDriver} />
          {currentResult ? <DriverDetailsPanel instance={instance} result={currentResult} selectedDriverId={driver} onDriverSelect={setDriver} /> : <div className="panel empty-state"><h2>Routes not calculated</h2><p>Your plan is saved. Retry a calculation below.</p></div>}
        </div><div className="panel actions"><span className="muted">Historical starting routes:</span>{(['nearest_neighbor', '2opt'] as Method[]).map(value => <button key={value} className="button secondary" disabled={busyNow} onClick={() => solve(value)}>{methodNames[value]}</button>)}</div>
        <OptimizationControls budget={budget} setBudget={setBudget} busy={busyNow} job={optimization} error={optimizationError} onRun={solve} onCancel={cancelOptimization} />
        {currentResult && <OptimizationDetails result={currentResult} mode={instance.mode} />}
      </section> : emptyPlan)}
      {view === 'compare' && (instance ? <CompareScreen onCompare={runComparison} onCancelComparison={cancelComparison} progress={comparisonProgress} instance={instance} comparison={comparison} loading={comparisonLoading} error={comparisonError} busy={busyNow} evolution={null} appliedRunId={null} onRetry={() => setRefresh(value => value + 1)} onRun={solve} onView={value => { if (results.has(value)) { setMethod(value); setDriver(null); navigate('routes'); } else void solve(value); }} /> : emptyPlan)}
      {labVisited && <div hidden={view !== 'lab'}><StrategyLab hasInstance={!!instance} applying={busyNow} onApply={(job, candidate) => optimize('strategy', job, candidate)} onStatus={setStrategyStatus} /></div>}
    </main><footer className="app-footer"><span>RouteIQ · Delivery route planning</span><span>Measured results. Clear comparisons.</span></footer>
  </div></ConfirmationProvider>;
}
export default App;
