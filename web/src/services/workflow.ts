import { api } from './api';
import { validateCompletedResult } from './product';
import { parseCoordinatePair, parseSeed } from './inputs';
import type { GenerateInstanceRequest, RoutingResultResponse } from '../types/api';

export type View = 'home' | 'setup' | 'routes' | 'compare' | 'lab';
export type Method = 'nearest_neighbor' | '2opt' | 'evolved' | 'portfolio' | 'vnd' | 'vnd_ils' | 'strategy' | 'adaptive';
export const methodNames: Record<Method, string> = { nearest_neighbor: 'Nearest Neighbor', '2opt': '2-Opt', evolved: 'Final selected route',
  portfolio: 'Constructor portfolio', vnd: 'Hybrid VND', vnd_ils: 'Hybrid VND + ILS', strategy: 'Validated strategy', adaptive:'Adaptive LLM search' };
export interface PlanDraft {
  mode: 'synthetic' | 'road'; numStops: number; numDrivers: number;
  layout: 'uniform' | 'clustered'; seed: string;
  depotLon: string; depotLat: string; stops: Array<{ lon: string; lat: string }>;
  stopEntry: 'map' | 'manual' | 'nearby'; radius: number;
  workloadMode?: 'balanced' | 'fixed';
}
export const initialPlan: PlanDraft = { mode: 'synthetic', numStops: 10, numDrivers: 2,
  layout: 'uniform', seed: '42', depotLon: '', depotLat: '', stops: [], stopEntry: 'map', radius: 5 };

export function validatePlan(plan: PlanDraft, step = 3): string | null {
  if (step === 0) return null;
  if (!Number.isInteger(plan.numStops) || plan.numStops < 5 || plan.numStops > (plan.mode === 'road' ? 99 : 200))
    return `Choose 5–${plan.mode === 'road' ? 99 : 200} delivery stops.`;
  if (plan.seed.trim() && parseSeed(plan.seed) === null) return 'Use a whole-number seed from 0 to 4294960000, or leave it blank for random locations.';
  if (plan.mode === 'road') {
    if (!parseCoordinatePair(plan.depotLon, plan.depotLat)) return 'Set a valid depot longitude (−180 to 180) and latitude (−90 to 90).';
    if (plan.stops.length !== plan.numStops) return `Place exactly ${plan.numStops} stops. You currently have ${plan.stops.length}.`;
    if (plan.stops.some(stop => !parseCoordinatePair(stop.lon, stop.lat))) return 'Every stop needs a valid longitude and latitude.';
  }
  if (step >= 2 && (!Number.isInteger(plan.numDrivers) || plan.numDrivers < 1 || plan.numDrivers > 20)) return 'Choose 1–20 drivers.';
  return null;
}

export function planRequest(plan: PlanDraft): GenerateInstanceRequest {
  const error = validatePlan(plan);
  if (error) throw new Error(error);
  return { mode: plan.mode, num_stops: plan.numStops, num_drivers: plan.numDrivers, layout: plan.layout,
    seed: plan.seed.trim() ? parseSeed(plan.seed)! : undefined,
    ...(plan.mode === 'road' ? { depot_coords: parseCoordinatePair(plan.depotLon, plan.depotLat)!,
      stop_coords: plan.stops.map(stop => parseCoordinatePair(stop.lon, stop.lat)!) } : {}),
    ...(plan.workloadMode === 'fixed' ? { workload: { policy: 'balanced_stop_count' as const,
      minimum_stops: Array.from({ length: plan.numDrivers }, (_, i) => Math.floor(plan.numStops / plan.numDrivers) + (i < plan.numStops % plan.numDrivers ? 1 : 0)),
      maximum_stops: Array.from({ length: plan.numDrivers }, (_, i) => Math.floor(plan.numStops / plan.numDrivers) + (i < plan.numStops % plan.numDrivers ? 1 : 0)) } } : {}) };
}

export async function generatePlan(plan: PlanDraft, progress: (message: string) => void) {
  progress('Creating your delivery plan…');
  const instance = await api.createInstance(planRequest(plan));
  progress('Calculating routes for your drivers…');
  const methods = ['nearest_neighbor', '2opt'] as const;
  const outcomes = await Promise.allSettled(methods.map(method => api.solveRouting({ instance_id: instance.instance_id, method })));
  const results = new Map<string, RoutingResultResponse>();
  const errors: string[] = [];
  outcomes.forEach((outcome, i) => {
    if (outcome.status === 'fulfilled' && outcome.value.instance_id === instance.instance_id && outcome.value.method === methods[i]
      && (!instance.problem_fingerprint || outcome.value.problem_fingerprint === instance.problem_fingerprint)
      && (!instance.matrix_fingerprint || outcome.value.matrix_fingerprint === instance.matrix_fingerprint)) {
      try {validateCompletedResult(instance,outcome.value);results.set(methods[i],outcome.value);}
      catch {errors.push(`${methodNames[methods[i]]}: No completed independently validated result was returned.`);}
    }
    else errors.push(`${methodNames[methods[i]]}: ${outcome.status === 'rejected' && outcome.reason instanceof Error ? outcome.reason.message : 'The server returned an unexpected route result.'}`);
  });
  return { instance, results, errors };
}

export function differenceText(distance: number, baseline?: number): string {
  if (baseline === undefined || !Number.isFinite(distance) || !Number.isFinite(baseline)) return 'Comparison unavailable';
  if (distance === baseline) return 'Same distance';
  if (baseline <= 0) return 'Percentage comparison unavailable';
  const percent = Math.abs(distance - baseline) / baseline * 100;
  return `${percent < 0.1 ? '<0.1' : percent.toFixed(1)}% ${distance < baseline ? 'shorter' : 'longer'}`;
}

export function viewFromHash(hash: string): View {
  const view = hash.replace('#', '');
  return ['home', 'setup', 'routes', 'compare', 'lab'].includes(view) ? view as View : 'home';
}
