import type { StrategyExperiment, StrategyRecord } from '../types/api';

export function completedCandidate(record: StrategyRecord) {
  const f=record.fitness;
  return f.eligible && f.expected_cases>0 && f.completed===f.expected_cases &&
    f.cases===f.expected_cases && f.incomplete===0 && f.failed===0 && !f.missing_cases && f.policy==='completed_panel/v1';
}
export function candidateRecommendation(state: StrategyExperiment) {
  const eligible=Object.values(state.records||{}).filter(r=>r.fitness.eligible &&
    r.fitness.mean_distance != null && Number.isFinite(r.fitness.mean_distance) && r.fitness.mean_distance>=0);
  const completed=eligible.filter(completedCandidate).filter(r=>state.manifest?.config.proposal_policy!=='llm_only' ||
    r.creation_method==='llm' && experimentEvidence(state,r.strategy_id).winnerLLM);
  return completed.sort((a,b)=>a.fitness.mean_distance!-b.fitness.mean_distance! || a.strategy_id.localeCompare(b.strategy_id))[0] || null;
}

export type ProviderCheck = {
  configured: boolean; reachable: boolean; available: boolean; model: string; message: string;
  status: 'available' | 'model_missing' | 'unreachable' | 'check_failed';
};

export function validProviderCheck(value: ProviderCheck, model: string) {
  return value?.model === model && typeof value.message === 'string' && value.configured === true &&
    ['available', 'model_missing', 'unreachable', 'check_failed'].includes(value.status) &&
    value.available === (value.status === 'available') &&
    value.reachable === ['available', 'model_missing'].includes(value.status);
}

export function experimentEvidence(state: StrategyExperiment, winnerId = state.best_id) {
  const records = state.records || {};
  const counts = { completed: 0, incomplete: 0, failed: 0 };
  for (const record of Object.values(records)) {
    for (const key of ['completed', 'incomplete', 'failed'] as const) counts[key] += record.fitness[key] || 0;
  }
  const visited = new Set<string>();
  const acceptedLive = (record: StrategyRecord) => record.creation_method==='llm' &&
    !!state.proposal_events?.some(e=>e.source==='llm' && e.outcome==='accepted' && e.strategy_id===record.strategy_id);
  const evaluatedLive = (record: StrategyRecord) => {
    const history=record.evaluation_history || [];
    const rows=history[history.length-1]?.rows || [];
    const expected=state.manifest?.config?.case_ids || [];
    return acceptedLive(record) && completedCandidate(record) && expected.length>0 &&
      rows.length===expected.length && new Set(rows.map(r=>r.case_id)).size===expected.length &&
      rows.every(r=>r.feasible && r.independently_validated===true && r.status==='completed' &&
        ['local_search_complete','no_perturbation_available','ils_iteration_limit'].includes(r.termination||'') && expected.includes(r.case_id));
  };
  const fromLLM = (id: string): boolean => {
    if (visited.has(id)) return false;
    visited.add(id);
    const record = records[id];
    return !!record && (evaluatedLive(record) || record.parents.some(fromLLM));
  };
  const live = state.manifest?.provider_mode === 'ollama';
  return { ...counts, missing: Math.max(0, (state.reserved_evaluations || 0) - counts.completed - counts.incomplete - counts.failed),
    acceptedLLM: live ? Object.values(records).filter(acceptedLive).length : 0,
    evaluatedLLM: live ? Object.values(records).filter(evaluatedLive).length : 0,
    winnerLLM: live && !!winnerId && fromLLM(winnerId) };
}

const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return JSON.stringify(Object.keys(value).sort().map(key => [key, canonical((value as Record<string, unknown>)[key])]));
  return JSON.stringify(value);
};

// Only compare terminal, identically configured development panels. Never borrow
// a training result as the distance of the user's plan or an unseen test case.
export function matchedRandom(state: StrategyExperiment, saved: StrategyExperiment[]) {
  if (state.manifest?.arm !== 'llm' || state.manifest.provider_mode !== 'ollama' || !['completed', 'stopped'].includes(state.status)) return null;
  const best = candidateRecommendation(state);
  if (!best || !best.fitness.eligible) return null;
  const random = saved.find(s => s.manifest?.arm === 'random' && ['completed', 'stopped'].includes(s.status) &&
    canonical(s.manifest.config) === canonical(state.manifest!.config) &&
    s.manifest.software != null && canonical(s.manifest.software) === canonical(state.manifest!.software) &&
    s.manifest.panel != null && canonical(s.manifest.panel) === canonical(state.manifest!.panel));
  const reference = random ? candidateRecommendation(random) : null;
  if (!reference || !reference.fitness.eligible || best.fitness.mean_distance == null || reference.fitness.mean_distance == null) return null;
  const a = best.fitness.mean_distance, b = reference.fitness.mean_distance;
  return { difference: b - a, percentage: b === 0 ? a === 0 ? 0 : null : (b - a) / b * 100,
    incomplete: best.fitness.incomplete + reference.fitness.incomplete,
    cases: state.manifest.config.case_ids.length };
}
