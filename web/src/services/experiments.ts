import type { StrategyExperiment } from '../types/api';

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

export function experimentEvidence(state: StrategyExperiment) {
  const records = state.records || {};
  const counts = { completed: 0, incomplete: 0, failed: 0 };
  for (const record of Object.values(records)) {
    for (const key of ['completed', 'incomplete', 'failed'] as const) counts[key] += record.fitness[key] || 0;
  }
  const visited = new Set<string>();
  const fromLLM = (id: string): boolean => {
    if (visited.has(id)) return false;
    visited.add(id);
    const record = records[id];
    return !!record && ((record.creation_method === 'llm' && !!record.fitness.eligible) || record.parents.some(fromLLM));
  };
  const live = state.manifest?.provider_mode === 'ollama';
  return { ...counts, missing: Math.max(0, (state.reserved_evaluations || 0) - counts.completed - counts.incomplete - counts.failed),
    acceptedLLM: live ? Object.values(records).filter(r => r.creation_method === 'llm').length : 0,
    evaluatedLLM: live ? Object.values(records).filter(r => r.creation_method === 'llm' && r.fitness.eligible).length : 0,
    winnerLLM: live && !!state.best_id && fromLLM(state.best_id) };
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
  const best = state.best_id && state.records?.[state.best_id];
  if (!best || !best.fitness.eligible) return null;
  const random = saved.find(s => s.manifest?.arm === 'random' && ['completed', 'stopped'].includes(s.status) &&
    canonical(s.manifest.config) === canonical(state.manifest!.config) &&
    s.manifest.software != null && canonical(s.manifest.software) === canonical(state.manifest!.software) &&
    s.manifest.panel != null && canonical(s.manifest.panel) === canonical(state.manifest!.panel));
  const reference = random?.best_id && random.records?.[random.best_id];
  if (!reference || !reference.fitness.eligible || best.fitness.mean_distance == null || reference.fitness.mean_distance == null) return null;
  const a = best.fitness.mean_distance, b = reference.fitness.mean_distance;
  return { difference: b - a, percentage: b === 0 ? a === 0 ? 0 : null : (b - a) / b * 100,
    incomplete: best.fitness.incomplete + reference.fitness.incomplete,
    cases: state.manifest.config.case_ids.length };
}
