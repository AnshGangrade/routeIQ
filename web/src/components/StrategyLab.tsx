import { FitnessPlot, CandidateComparison, Lineage } from './ResearchVisuals';
import { experimentEvidence, matchedRandom, validProviderCheck, type ProviderCheck } from '../services/experiments';
import { sourceLabel, experimentStatus } from '../services/presentation';
import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import { activeStatus, statusText, watchTask } from '../services/product';
import type { StartStrategyRequest, StrategyExperiment, StrategyRecord } from '../types/api';

const initial: StartStrategyRequest = {
  arm: 'random', mode: 'offline', provider: { model: 'qwen3:1.7b', temperature: .3, timeout: 20, retries: 1, max_tokens: 2048 },
  config: { case_ids: ['development-n20-k2-uniform-symmetric-r0', 'development-n20-k3-clustered-directed-r1'], seed: 2026, search_seed: 0,
    population_size: 6, generations: 3, elites: 2, max_evaluations: 36, operations_per_evaluation: 20000,
    seconds_per_evaluation: 10, max_total_operations: 720000, max_seconds: 180, max_proposals: 120, max_llm_calls: 6 },
};


export function StrategyLab({ hasInstance, applying, onApply, onStatus }: {
  hasInstance: boolean; applying: boolean; onApply: (job: string, strategy: string) => void;
  onStatus: (status: string | null) => void;
}) {
  const sendingRef=useRef(false);
  const [providerStatus,setProviderStatus]=useState<ProviderCheck | null>(null);
  const [checkAttempt,setCheckAttempt]=useState(0);
  const [request, setRequest] = useState(initial);
  const [jobId, setJobId] = useState<string | null>(null);
  const [state, setState] = useState<StrategyExperiment | null>(null);
  const [saved, setSaved] = useState<Array<{ id: string; state: StrategyExperiment }>>([]);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const latest = useRef<string | null>(null);
  const stateRef = useRef(state); stateRef.current = state;
  const running = activeStatus(state?.status);
  const live = request.arm === 'llm' && request.mode === 'ollama';
  const providerKey = JSON.stringify(request.provider);
  useEffect(() => {
    setProviderStatus(null);
    if (!live) return;
    const controller = new AbortController();
    const model = request.provider.model;
    const timer = setTimeout(() => {
      api.checkStrategyProvider(request.provider, controller.signal).then(checked => {
        if (!validProviderCheck(checked, model)) throw new Error('Invalid provider response');
        if (!controller.signal.aborted) setProviderStatus(checked);
      }).catch(() => {
        if (!controller.signal.aborted) setProviderStatus({ configured: true, reachable: false, available: false, model,
          status: 'check_failed', message: 'Provider check failed or returned invalid data. Check the backend and local Ollama service, then retry. Random baseline remains available.' });
      });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [live, providerKey, checkAttempt]);
  const providerReady = !live || !!providerStatus && providerStatus.model === request.provider.model && providerStatus.available;

  useEffect(() => { onStatus(running ? state?.status || null : null); }, [running, state?.status, onStatus]);
  useEffect(() => {
    if (!jobId) return;
    let stamp = '';
    return watchTask(jobId, api.strategyStatus, async (progress, signal) => {
      const nextStamp = JSON.stringify([progress.status, progress.generation, progress.best_id, progress.reserved_evaluations]);
      let value = { ...stateRef.current, ...progress } as StrategyExperiment;
      if (nextStamp !== stamp) {
        const exported = await api.strategyExport(jobId, signal);
        if (signal.aborted || latest.current !== jobId) return;
        value = { ...exported, ...progress };
        stamp = nextStamp;
      }
      if (signal.aborted || latest.current !== jobId) return;
      setError(null); setState(value);
      if (!activeStatus(value.status)) setSaved(previous => [...previous.filter(s => s.id !== jobId), { id: jobId, state: value }]);
    }, (message, terminal) => {
      if (latest.current !== jobId) return;
      setError(`Progress unavailable: ${message} ${terminal ? 'The experiment is no longer available.' : 'Retrying automatically.'}`);
      if (terminal) setState(previous => previous ? { ...previous, status: 'failed', termination: 'experiment_unavailable' } : previous);
    });
  }, [jobId]);
  const start = async () => {
    if (sendingRef.current || running || !providerReady) return;
    sendingRef.current=true;
    setSending(true); setError(null);
    try {
      if(request.arm==='llm' && request.mode==='ollama') {

        let checked: ProviderCheck;
        try {
          checked=await api.checkStrategyProvider(request.provider);
          if (!validProviderCheck(checked, request.provider.model)) throw new Error('Invalid provider response');
        } catch {
          setProviderStatus({ configured: true, reachable: false, available: false, model: request.provider.model,
            status: 'check_failed', message: 'Provider check failed. Check local Ollama and retry.' });
          throw new Error('Provider check failed. No experiment was started. Retry the provider check.');
        }
        setProviderStatus(checked);
        if(!checked.available) throw new Error(checked.message);
      }
      const response = await api.startStrategy(request);
      latest.current = response.job_id; setState({ status: response.status, job_id: response.job_id }); setJobId(response.job_id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Experiment could not start.'); }
    finally { sendingRef.current=false;setSending(false); }
  };
  const cancel = async () => {
    if (!jobId) return;
    try {
      const result = await api.cancelStrategy(jobId);
      if (latest.current !== jobId) return;
      if (result.job_id !== jobId) throw new Error('Cancellation belongs to another experiment.');
      setState(s => s ? { ...s, status: result.status } : s);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Cancellation failed. Retry.'); }
  };
  const candidate = state?.best_id ? state.records?.[state.best_id] : null;
  const best=candidate?.fitness.eligible?candidate:null;
  const records = Object.values(state?.records || {});
  const evidence = state ? experimentEvidence(state) : null;
  const paired = state ? matchedRandom(state, saved.map(item => item.state)) : null;
  const apply = (record: StrategyRecord) => { if (jobId) onApply(jobId, record.strategy_id); };
  const currentOrigin = (record: StrategyRecord) => sourceLabel(record.creation_method, state?.manifest?.provider_mode === 'offline');
  return <section className="stack strategy-lab" aria-label="Strategy Experiments">
    <div className="page-heading"><div><p className="eyebrow">Optional research workspace</p><h1>Strategy Experiments</h1><p>Test routing configurations and inspect what the measurements support.</p></div><a href="#routes" className="button secondary">Back to route plan</a></div>
    <div className="panel experiment-explanation"><p>Strategies configure existing routing constructors and search operators. Authored seeds, random proposals, mutation, crossover and optionally an LLM supply candidates. The deterministic engine runs each configuration, validates routes and measures distance. Lower mean development-case distance ranks higher.</p><p><strong>The LLM proposes strategy configurations. It does not calculate routes or guarantee an optimal solution.</strong></p><p className="small muted">Development scores guide the search; they do not prove performance on unseen cases. Validation supports controlled selection. Held-out evidence requires a separate frozen protocol.</p></div>
    <div className="notice">The Phase 6B experiment is incomplete: 88 held-out LLM-arm measurements are missing. It does not establish that LLM evolution beats random search. New experiments here use development data only.</div>
    <form className="panel stack strategy-config" onSubmit={e => { e.preventDefault(); void start(); }}>
      <fieldset disabled={sending || running} className="stack"><legend className="sr-only">Strategy experiment configuration</legend>
        <div className="mode-options experiment-choices">
          <label className={`choice-card ${request.arm==='random'?'chosen':''}`}><input type="radio" name="experiment-choice" checked={request.arm==='random'} onChange={()=>setRequest(r=>({...r,arm:'random',mode:'offline'}))}/><span><strong>Random baseline</strong><small>Try routing strategies automatically. Non-LLM; no model setup required.</small></span></label>
          <label className={`choice-card ${request.arm==='llm'&&request.mode==='ollama'?'chosen':''}`}><input type="radio" name="experiment-choice" checked={request.arm==='llm'&&request.mode==='ollama'} onChange={()=>setRequest(r=>({...r,arm:'llm',mode:'ollama'}))}/><span><strong>AI-guided</strong><small>Ask local Ollama for strategy proposals. Model availability is checked before starting.</small></span></label>
        </div>
        <p className="small muted">Training uses the same two fixed development benchmark cases. Applying the winner independently evaluates your selected route plan.</p>
        {live && <div className="notice"><p role="status"><strong>{request.provider.model}</strong> / {providerStatus?.model === request.provider.model ? providerStatus.message : 'Checking local Ollama...'}</p><button type="button" className="text-button" onClick={()=>setCheckAttempt(n=>n+1)}>Retry provider check</button><p className="small">Authored seeds, mutations, crossover and random fallback remain separately attributed. Random baseline works without Ollama.</p></div>}
        <details><summary>Advanced experiment settings</summary>
        <div className="form-grid"><label>Search control<select value={request.arm} onChange={e => setRequest(r => ({ ...r, arm: e.target.value as StartStrategyRequest['arm'] }))}><option value="random">Random strategy search</option><option value="hand">Hand-authored portfolio</option><option value="llm">AI-guided proposals</option></select></label>
          {request.arm === 'llm' && <label>Proposal provider<select value={request.mode} onChange={e => setRequest(r => ({ ...r, mode: e.target.value as StartStrategyRequest['mode'] }))}><option value="offline">Offline fixture demo (no live LLM)</option><option value="ollama">Local Ollama (live proposals)</option></select></label>}</div>
        <p className="small muted">{request.arm==='hand'?'Hand-authored control.':request.arm==='random'?'Random non-LLM search.':request.mode==='offline'?'Offline fixture demo, not AI-generated proposals.':'Live Ollama requested.'}</p><div className="form-grid">
          <label>Generations<input type="number" min="1" max="3" value={request.config.generations} onChange={e => setRequest(r => ({ ...r, config: { ...r.config, generations: Number(e.target.value) } }))} /></label>
          <label>Proposal seed<input type="number" min="0" max="4294967295" value={request.config.seed} onChange={e => setRequest(r => ({ ...r, config: { ...r.config, seed: Number(e.target.value) } }))} /></label>
          {request.arm === 'llm' && request.mode === 'ollama' && <><label>Ollama model<input required value={request.provider.model} onChange={e => setRequest(r => ({ ...r, provider: { ...r.provider, model: e.target.value } }))} /></label><label>Temperature<input type="number" min="0" max="2" step="0.1" value={request.provider.temperature} onChange={e => setRequest(r => ({ ...r, provider: { ...r.provider, temperature: Number(e.target.value) } }))} /></label></>}
        </div><p className="small muted">Population 6 · 36 case evaluations maximum · 20,000 operations / 10 seconds per evaluation · 180 seconds per arm · solver seed 0. Generation means a round of candidates; diversity counts distinct configurations and route behaviors. The same proposal seed does not guarantee deterministic live model outputs.</p></details>
        <button className={`button ${best?'secondary':'primary'} fit`} type="submit" disabled={!providerReady}>{sending ? 'Starting…' : 'Run experiment'}</button>
      </fieldset>
    </form>

    {error && <p className="notice error" role="alert">{error}</p>}
    {state && <section className="panel stack strategy-progress" aria-label="Strategy experiment progress"><div className="section-heading"><h2>{experimentStatus(state)}</h2>{running && <button className="button secondary" onClick={cancel} disabled={state.status === 'cancelling'}>Cancel strategy experiment</button>}</div>
      <p className="small">Accepted configurations: {(['seed','random','mutation','crossover','llm'] as const).map(source => `${sourceLabel(source,state.manifest?.provider_mode==='offline')}: ${records.filter(r=>r.creation_method===source).length}`).join(' / ')}.</p>
      {evidence && <p className="notice">Evaluation details: {evidence.completed} completed / {evidence.incomplete} incomplete / {evidence.failed} failed / {evidence.missing} missing reserved evaluations. {evidence.acceptedLLM} accepted live LLM proposals; {evidence.evaluatedLLM} evaluated on the full panel. {evidence.winnerLLM ? 'The best result has an evaluated LLM proposal in its recorded ancestry; this does not establish a causal benefit.' : 'No evaluated live LLM proposal is recorded in the ancestry of the best result.'}</p>}
      {best && <div className="winner-card"><p className="eyebrow">Best result / development cases</p><p className="small">Mean route distance / strategy {best.strategy_id.slice(-12)}</p><h3>{best.fitness.mean_distance?.toFixed(2) ?? 'Unavailable'} map units</h3><p>{currentOrigin(best)} · {best.fitness.completed} completed / {best.fitness.incomplete} incomplete / {best.fitness.failed} failed case evaluations.</p><p className="small muted">Training fitness is not a route distance for your selected plan. Applying recalculates routes on that plan’s matrix.</p><button className="button primary" disabled={!hasInstance || applying || !!error || !['completed','stopped'].includes(state.status) || !best.fitness.eligible} onClick={() => apply(best)}>Apply strategy to current plan</button>{!hasInstance && <p className="small">Create a route plan before applying a strategy.</p>}</div>}
      <p className="notice">Difference versus random baseline: {paired ? `${Math.abs(paired.difference).toFixed(2)} map units ${paired.difference < 0 ? 'longer' : paired.difference > 0 ? 'shorter' : 'different'} (${paired.percentage == null ? 'percentage undefined for zero reference' : paired.percentage.toFixed(2)+'%'}); ${paired.cases} matched development cases, ${paired.incomplete} incomplete solver runs across both winners. This is a difference of selected development means, not unseen-case or causal AI evidence.` : 'Not measured in a matching completed experiment pair in this tab. Run both arms with identical settings; unrelated runs are not compared.'} {state.manifest?.provider_mode==='offline' && 'Offline fixture responses are not live LLM evidence.'}</p>
      <section className="research-observatory" aria-label="Experiment visual evidence"><h3>Development route distance by generation</h3><p className="small muted">Lower is better. Bounded, feasible results may include incomplete searches.</p><FitnessPlot history={state.history || []}/></section>
      <details className="research-details"><summary>Technical details</summary><p className="small muted">Job {jobId} / loop status {state.status} · {statusText(state.termination || 'development evaluation')}</p>
      <dl className="execution-grid"><div><dt>Generation</dt><dd>{state.generation ?? 0} / {state.manifest?.config.generations ?? request.config.generations}</dd></div><div><dt>Current population</dt><dd>{state.population?.length ?? 0} / {state.manifest?.config.population_size ?? 6}</dd></div><div><dt>Case evaluations reserved</dt><dd>{state.reserved_evaluations ?? 0}</dd></div><div><dt>Measured work</dt><dd>{(state.actual_operations ?? 0).toLocaleString()}</dd></div><div><dt>Provider requests</dt><dd>{state.provider_usage?.reduce((n, u) => n + u.calls, 0) ?? 0}</dd></div><div><dt>Tokens</dt><dd>{state.llm_tokens == null ? 'Unavailable' : state.llm_tokens}</dd></div></dl>
      {!!Object.keys(state.rejections || {}).length && <p className="notice">Rejected proposals: {Object.entries(state.rejections || {}).map(([key, value]) => `${statusText(key)}: ${value}`).join(' · ')}. Provider failures may trigger separately recorded random fallback under the existing engine policy.</p>}

      <CandidateComparison records={records} offline={state.manifest?.provider_mode==='offline'}/>
      <details className="lineage-panel"><summary>Strategy lineage</summary><Lineage records={records} bestId={state.best_id} offline={state.manifest?.provider_mode==='offline'}/></details>
      {!!state.history?.length && <div className="table-scroll"><table><caption>Best-so-far training fitness and diversity</caption><thead><tr><th>Round</th><th>Best mean distance</th><th>Configurations</th><th>Route behaviors</th></tr></thead><tbody>{state.history.map(h => <tr key={h.generation}><th>{h.generation + 1}</th><td>{h.best_so_far?.toFixed(2) ?? 'Unavailable'} map units</td><td>{h.unique_configurations}</td><td>{h.behavioral_diversity}</td></tr>)}</tbody></table></div>}
      <details><summary>Candidate configurations and lineage ({records.length})</summary>{records.map(record => <article key={record.strategy_id} className="candidate-record"><h3>{currentOrigin(record)} · generation {record.generation}</h3><p className="small mono">{record.strategy_id}</p><p className="small">Parents: {record.parents.join(', ') || 'None (initial or independent proposal)'}</p><p>{record.rationale}</p><p className="small">Mean distance: {record.fitness.mean_distance?.toFixed(2) ?? 'Not measured'} · completed {record.fitness.completed ?? 0}, incomplete {record.fitness.incomplete ?? 0}, failed {record.fitness.failed ?? 0}</p><pre>{JSON.stringify(record.config, null, 2)}</pre></article>)}</details>
      <button className="button secondary fit" onClick={async () => { if (!jobId) return; try { const data = await api.strategyExport(jobId); const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = `routeiq-${jobId}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); } catch { setError('Export unavailable. Retry when the backend is reachable.'); } }}>Export experiment JSON</button></details>
    </section>}
    {!!saved.length && <details className="panel"><summary>Previous experiments</summary><p className="small muted">Recorded development runs in this tab. Selected training results are not held-out evidence; differing seeds and budgets are not paired comparisons.</p><div className="table-scroll"><table><thead><tr><th>Control</th><th>Status</th><th>Development mean</th><th>Work</th><th>Inspect</th></tr></thead><tbody>{saved.map(item => <tr key={item.id}><th>{statusText(item.state.manifest?.arm)} · {item.state.manifest?.provider_mode}</th><td>{statusText(item.state.status)}</td><td>{item.state.best_id ? item.state.records?.[item.state.best_id]?.fitness.mean_distance?.toFixed(2) : 'Unavailable'}</td><td>{item.state.actual_operations?.toLocaleString()}</td><td><button className="text-button" disabled={running} onClick={() => { latest.current = item.id; setJobId(item.id); setState(item.state); }}>Inspect run</button></td></tr>)}</tbody></table></div></details>}
  </section>;
}
