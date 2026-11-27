import { candidateRecommendation, experimentEvidence, validProviderCheck, type ProviderCheck } from '../services/experiments';
import { useEffect, useRef, useState } from 'react';
import { api } from '../services/api';
import { activeStatus, statusText, watchTask } from '../services/product';
import type { StartStrategyRequest, StrategyExperiment } from '../types/api';

export const aiStrategyRequest: StartStrategyRequest = {
  workflow:'ai_product', arm:'llm', mode:'ollama',
  provider:{model:'qwen3:1.7b',temperature:.3,timeout:20,retries:1,max_tokens:2048},
  config:{case_ids:['development-n20-k2-uniform-symmetric-r0','development-n20-k3-clustered-directed-r1'],
    seed:0,search_seed:0,population_size:4,generations:2,elites:2,max_evaluations:8,
    operations_per_evaluation:100000,seconds_per_evaluation:20,max_total_operations:800000,
    max_seconds:180,max_proposals:8,max_llm_calls:6}
};


export function StrategyLab({ hasInstance, applying, onApply, onStatus }: {
  hasInstance: boolean; applying: boolean; onApply: (job: string, strategy: string) => void;
  onStatus: (status: string | null) => void;
}) {
  const sendingRef=useRef(false);
  const [providerStatus,setProviderStatus]=useState<ProviderCheck | null>(null);
  const [checkAttempt,setCheckAttempt]=useState(0);
  const request = aiStrategyRequest;
  const [jobId, setJobId] = useState<string | null>(null);
  const [state, setState] = useState<StrategyExperiment | null>(null);
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
          status: 'check_failed', message: 'Provider check failed or returned invalid data. Check the backend and local Ollama service, then retry.' });
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
  const best=state && ['completed','stopped'].includes(state.status) ? candidateRecommendation(state) : null;
  const evidence=state ? experimentEvidence(state,best?.strategy_id) : null;
  const failureMessage = state?.termination==='llm_unavailable' ? 'Ollama could not provide a valid strategy within the retry limit.'
    : state?.termination==='llm_proposal_limit' ? 'Ollama did not produce enough distinct supported proposals within the request limit.'
    : state?.termination==='time_limit' ? 'Evolution reached its time limit.'
    : state?.status==='cancelled' ? 'Evolution was cancelled.'
    : 'One or more searches reached a solver limit, failed, or were not evaluated.';
  const exportRun=async()=>{
    if(!jobId)return;
    try {const data=await api.strategyExport(jobId);const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
      const link=document.createElement('a');link.href=url;link.download=`routeiq-${jobId}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch {setError('Export unavailable. Retry when the backend is reachable.');}
  };
  return <section className="stack strategy-lab" aria-label="Evolution">
    <div className="page-heading"><h1>AI-guided strategy</h1><a href="#routes" className="button secondary">Back to route plan</a></div>
    <p>The LLM proposes strategy configurations. The trusted routing engine evaluates them. It does not guarantee an optimal solution.</p>
    <form className="panel stack strategy-config" onSubmit={e=>{e.preventDefault();void start();}}>
      <p><strong>Local Ollama / {request.provider.model}</strong></p>
      <p role="status">{providerStatus?.message || 'Checking local Ollama...'}</p>
      <p className="small muted">Two trusted starting strategies, then bounded LLM proposals. A strategy must complete both development cases before it can be applied. Applying runs it again on your current plan.</p>
      <div className="actions"><button type="button" className="button secondary" disabled={sending||running} onClick={()=>setCheckAttempt(n=>n+1)}>Check Ollama</button>
        <button className="button primary" type="submit" disabled={!providerReady||sending||running}>{sending?'Starting...':'Run evolution'}</button></div>
    </form>
    {error && <p className="notice error" role="alert">{error}</p>}
    {state && <section className="panel stack strategy-progress" aria-label="Evolution progress">
      <div className="section-heading"><h2>{running?'Evaluating strategies':best?'Strategy ready':'No fully evaluated strategy was produced'}</h2>
        {running && <button className="button secondary" disabled={state.status==='cancelling'} onClick={cancel}>Cancel evolution</button>}</div>
      {running && <p role="status">Round {Math.min((state.generation||0)+1,2)} of 2 / {evidence?.completed||0} case searches completed. {statusText(state.status)}</p>}
      {!running && !best && <p className="notice">{failureMessage} No strategy is available to apply. Your current routes are unchanged.</p>}
      {best && <div className="winner-card"><p className="eyebrow">Completed evaluation</p><h3>Strategy {best.strategy_id.slice(-12)}</h3>
        <p>{best.fitness.mean_distance?.toFixed(2)} map units / mean development-case distance</p>
        <p>{best.fitness.completed} of {best.fitness.expected_cases} cases completed and independently validated.</p>
        <p>Construction: {statusText(String(best.config.construction))}. Operators: {(best.config.operators as string[]).map(statusText).join(', ')}.</p>
        <p className="small muted">This score is not the distance for your current plan or evidence of AI superiority. Applying uses a size-aware allowance of up to 500,000 operations / 30 seconds. Only a completed validated result replaces your current route.</p>
        <button className="button primary" disabled={!hasInstance||applying||!!error} onClick={()=>jobId&&onApply(jobId,best.strategy_id)}>Apply to current plan</button>
        {!hasInstance && <p>Create or generate a route plan before applying.</p>}</div>}
      <details className="research-details"><summary>Technical details and export</summary>
        <p>Job {jobId} / {statusText(state.status)} / {statusText(state.termination||'evaluating')}</p>
        <p>{evidence?.acceptedLLM||0} accepted live LLM proposals; {evidence?.evaluatedLLM||0} completed full-panel evaluations.</p>
        <p>{evidence?.completed||0} completed / {evidence?.incomplete||0} incomplete / {evidence?.failed||0} failed / {evidence?.missing||0} missing reserved evaluations.</p>
        <p>Development only. No validation or held-out evaluation is run here. Historical research and its limitations remain in the saved reports.</p>
        <pre>{JSON.stringify({termination:state.termination,rejections:state.rejections,provider_usage:state.provider_usage,records:state.records},null,2)}</pre>
        <button className="button secondary" onClick={exportRun}>Export experiment JSON</button>
      </details>
    </section>}
  </section>;
}
