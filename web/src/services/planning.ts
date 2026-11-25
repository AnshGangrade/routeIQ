import type { PlanDraft } from './workflow';
import type { RoutingResultResponse } from '../types/api';

/** UI draft identity only; the backend remains the authority for problem hashes. */
export function draftIdentity(draft: PlanDraft) {
  return JSON.stringify([draft.mode,draft.numStops,draft.numDrivers,draft.seed,draft.layout,
    draft.mode==='road' ? [draft.depotLon,draft.depotLat,draft.stops] : null,draft.workloadMode || 'balanced']);
}

export function completeDuration(result: RoutingResultResponse) {
  if(!result.drivers.some(d=>d.duration!=null))return null;
  return result.drivers.every(d=>d.route.length===2 || d.duration!=null && Number.isFinite(d.duration) && d.duration>=0)
    ? result.drivers.reduce((sum,d)=>sum+(d.route.length===2?0:d.duration ?? 0),0) : null;
}
