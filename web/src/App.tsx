import { Home } from './components/Home';
import { BrandMark, Icon, ConfirmationProvider } from './components/Design';
import { useEffect, useRef, useState } from 'react';
import { SetupWizard } from './components/SetupWizard';
import { RouteVisualization } from './components/RouteVisualization';
import { CompactResults } from './components/CompactResults';
import { DriverDetailsPanel } from './components/DriverDetailsPanel';
import { CompareScreen } from './components/CompareScreen';
import { EvolutionLab, initialEvolution } from './components/EvolutionLab';
import { StrategyLab } from './components/StrategyLab';
import { OptimizationControls, defaultBudget } from './components/OptimizationControls';
import { OptimizationDetails } from './components/OptimizationDetails';
import { activeStatus, validateRouteResult, watchTask } from './services/product';
import { api, watchEvolution } from './services/api';
import { generatePlan, initialPlan, methodNames, viewFromHash } from './services/workflow';
import type { Method, View } from './services/workflow';
import type { ComparisonResponse, EvolutionProgressResponse, InstanceResponse, RoutingResultResponse, HybridMethod, OptimizationJob } from './types/api';

function App() {
  const [view, setView] = useState<View>(() => viewFromHash(window.location.hash));
  const [legacyLab, setLegacyLab] = useState(false);
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
  const [evoConfig, setEvoConfig] = useState(initialEvolution);
  const [evolution, setEvolution] = useState<EvolutionProgressResponse | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [appliedRunId, setAppliedRunId] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<ComparisonResponse | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [measurement, setMeasurement] = useState<RoutingResultResponse | null>(null);
  const [measuring, setMeasuring] = useState(false);
  const [measurementError, setMeasurementError] = useState<string | null>(null);
  const [measureAttempt, setMeasureAttempt] = useState(0);
  const busyRef = useRef(false);
  const instanceRef = useRef<string | null>(null);
  const runRef = useRef<string | null>(null);
  const main = useRef<HTMLElement>(null);
  const currentResult = results.get(method) || null;
  const running = !!evolution && ['pending', 'running', 'cancelling'].includes(evolution.status);
  const optimizing = activeStatus(optimization?.status);
  const busyNow = !!busy || optimizing;
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
    if (!activeRunId) return;
    return watchEvolution(activeRunId, progress => { if (runRef.current === progress.run_id) { setPollError(null); setEvolution(progress); } }, message => { if (runRef.current === activeRunId) setPollError(message); });
  }, [activeRunId]);
  useEffect(() => {
    setMeasurement(null); setMeasurementError(null); setMeasuring(false);
    if (!instance || evolution?.status !== 'completed') return;
    let current = true;
    setMeasuring(true);
    api.previewWinner(evolution.run_id, instance.instance_id).then(result => {
      if (!current) return;
      if (result.instance_id !== instance.instance_id || result.run_id !== evolution.run_id || result.method !== 'evolved' || !result.optimization) throw new Error('The measurement does not match this plan and run.');
      setMeasurement(result);
    }).catch(reason => { if (current) setMeasurementError(reason instanceof Error ? reason.message : 'Plan measurement failed.'); })
      .finally(() => { if (current) setMeasuring(false); });
    return () => { current = false; };
  }, [instance, evolution?.run_id, evolution?.status, measureAttempt]);
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
  const create = () => perform('Creating your plan…', async () => {
    if (optimizing) throw new Error('Finish or cancel the current optimization first.');
    const plan = await generatePlan(draft, setBusy);
    optimizationRef.current = null; setOptimizationId(null); setOptimization(null); setOptimizationError(null);
    instanceRef.current = plan.instance.instance_id;
    setInstance(plan.instance); setResults(plan.results); setDriver(null); setAppliedRunId(null);
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
    if (selected === 'strategy') { navigate('lab'); setLegacyLab(false); return; }
    return perform(`Calculating ${methodNames[selected]} routes…`, async () => {
    if (!instance) throw new Error('Create a route plan first.');
    if (optimizing) throw new Error('Finish or cancel the current optimization first.');
    if (selected === 'evolved' && (evolution?.status !== 'completed' || pollError)) throw new Error('Wait for a completed, verified evolution run before applying its winner.');
    const result = selected === 'evolved' ? await api.applyWinner(evolution!.run_id, instance.instance_id) : await api.solveRouting({ instance_id: instance.instance_id, method: selected as 'nearest_neighbor' | '2opt' });
    validateRouteResult(instance, result);
    if (result.instance_id !== instanceRef.current || result.method !== selected) throw new Error('The returned route does not match the selected plan. Please retry.');
    if (selected === 'evolved' && (result.run_id !== evolution!.run_id || !result.optimization)) throw new Error('The server did not return a verified selection for this run.');
    setResults(previous => new Map(previous).set(selected, result)); setMethod(selected); setDriver(null);
    if (selected === 'evolved') setAppliedRunId(evolution!.run_id);
    navigate('routes');
  }); };
  const start = () => perform('Starting experiment…', async () => {
    if (running) throw new Error('Finish or cancel the current experiment first.');
    const fields = [[evoConfig.num_stops, 10, 100], [evoConfig.num_instances, 3, 50], [evoConfig.num_generations, 2, 20], [evoConfig.candidates_per_generation, 2, 10], [evoConfig.elites_kept, 1, 10]];
    if (fields.some(([v, min, max]) => !Number.isInteger(v) || v < min || v > max)) throw new Error('Check the ranges in advanced experiment settings.');
    const response = await api.startEvolution(evoConfig);
    runRef.current = response.run_id;
    setPollError(null); setEvolution({ run_id: response.run_id, status: 'pending', current_generation: 0, total_generations: evoConfig.num_generations, generations: [], best_heuristic_id: null, error: null });
    setActiveRunId(response.run_id);
  });
  const cancel = async () => {
    if (!activeRunId) return;
    const cancelledRun = activeRunId;
    try { const response = await api.cancelEvolution(cancelledRun); if (runRef.current !== cancelledRun) return; if (response.run_id !== cancelledRun) throw new Error('Unexpected cancellation response.');
      setEvolution(previous => previous?.run_id === response.run_id ? { ...previous, status: response.status as EvolutionProgressResponse['status'] } : previous);
    } catch (reason) { if (runRef.current === cancelledRun) setPollError(reason instanceof Error ? reason.message : 'Cancellation request failed. Retry cancellation.'); }
  };
  const emptyPlan = <div className="panel empty-state"><p className="eyebrow">Start with your deliveries</p><h1>No route plan yet</h1><p>Create a plan before viewing routes or comparing methods.</p><a className="button primary" href="#setup">Create route plan</a></div>;

  return <ConfirmationProvider><div className={`app-shell view-${view}`}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); main.current?.focus(); }}>Skip to content</a>
    <header className="app-header"><a href="#home" className="brand" aria-label="RouteIQ home"><BrandMark /><span>Route<span className="brand-iq">IQ</span></span></a><nav aria-label="Main navigation">
      {([['home', 'Home'], [instance ? 'routes' : 'setup', 'Route Plan'], ['compare', 'Compare'], ['lab', 'Evolution Lab']] as [View, string][]).map(([target, title]) => <a key={title} href={`#${target}`} aria-current={view === target || title === 'Route Plan' && view === 'setup' ? 'page' : undefined}><Icon name={title === "Home" ? "home" : title === "Route Plan" ? "map" : title === "Compare" ? "compare" : "lab"} size={17}/><span>{title}</span>{title === 'Evolution Lab' && running && <span className="live-dot" aria-label="Experiment running" />}</a>)}
    </nav><span className="header-note">Delivery planning, made clearer.</span></header>
    <div className="context-bar"><span>{instance ? `${instance.mode === 'road' ? 'Road' : 'Demo'} plan · ${instance.num_stops} stops · ${instance.num_drivers} drivers` : view === 'setup' ? `Draft plan · Step ${step + 1} of 4` : 'No plan selected'}</span>{instance && <span className="instance-id" title={instance.instance_id}>Plan {instance.instance_id.slice(-8)}</span>}{optimizing && <a href="#routes">Optimization · {optimization?.status}</a>}{strategyStatus && <a href="#lab">Strategy experiment · {strategyStatus}</a>}{running && <a href="#lab">Experiment {evolution?.current_generation}/{evolution?.total_generations} · {evolution?.status}</a>}</div>
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
        </div><div className="panel actions"><span className="muted">Historical starting routes:</span>{(['nearest_neighbor', '2opt'] as Method[]).map(value => <button key={value} className="button secondary" disabled={busyNow} onClick={() => solve(value)}>{methodNames[value]}</button>)}{evolution?.status === 'completed' && <button className="button secondary" disabled={busyNow || !!pollError} onClick={() => solve('evolved')}>Apply evolved winner</button>}</div>
        <OptimizationControls budget={budget} setBudget={setBudget} busy={busyNow} job={optimization} error={optimizationError} onRun={solve} onCancel={cancelOptimization} />
        {currentResult && <OptimizationDetails result={currentResult} mode={instance.mode} />}
      </section> : emptyPlan)}
      {view === 'compare' && (instance ? <CompareScreen instance={instance} comparison={comparison} loading={comparisonLoading} error={comparisonError} busy={busyNow} evolution={evolution} appliedRunId={appliedRunId} onRetry={() => setRefresh(value => value + 1)} onRun={solve} onView={value => { if (results.has(value)) { setMethod(value); setDriver(null); navigate('routes'); } else void solve(value); }} /> : emptyPlan)}
      {view === 'lab' && <div className="lab-tabs" aria-label="Research workflow"><button className="button secondary" aria-pressed={!legacyLab} onClick={() => setLegacyLab(false)}>Strategy evolution</button><button className="button secondary" aria-pressed={legacyLab} onClick={() => setLegacyLab(true)}>Legacy heuristic lab</button></div>}
      {view === 'lab' && legacyLab && <div className="legacy-lab"><p className="notice">Legacy code-generating workflow. Its synthetic training scores are separate from the Phase 6 fleet-strategy experiments.</p><EvolutionLab config={evoConfig} setConfig={setEvoConfig} evolution={evolution} busy={busyNow} pollError={pollError} hasInstance={!!instance} onStart={start} onCancel={cancel} onApply={() => solve('evolved')} measurement={measurement?.instance_id === instance?.instance_id && measurement?.run_id === evolution?.run_id ? measurement : null} mode={instance?.mode} measuring={measuring} measurementError={measurementError} onMeasure={() => setMeasureAttempt(value => value + 1)} /></div>}
      {labVisited && <div hidden={view !== 'lab' || legacyLab}><StrategyLab hasInstance={!!instance} applying={busyNow} onApply={(job, candidate) => optimize('strategy', job, candidate)} onStatus={setStrategyStatus} /></div>}
    </main><footer className="app-footer"><span>RouteIQ · Delivery route planning</span><span>Measured results. Clear comparisons.</span></footer>
  </div></ConfirmationProvider>;
}
export default App;
