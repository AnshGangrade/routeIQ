import type { InstanceResponse, MethodComparison, RoutingResultResponse } from '../types/api';
import { formatDistance } from './distance';
import { differenceText } from './workflow';
import { validateRouteResult } from './product';

type Measured = MethodComparison | RoutingResultResponse;
export const baselineName = 'Nearest Neighbor (historical)';
const finiteDistance = (n: number) => Number.isFinite(n) && n >= 0;

/** No percentages from legacy rows with unknown identity or validation. */
export function verifiedMeasurement(instance: InstanceResponse, row?: Measured | null): row is Measured {
  return !!row && row.feasible === true && finiteDistance(row.total_distance) &&
    !!instance.problem_fingerprint && !!instance.matrix_fingerprint &&
    row.problem_fingerprint === instance.problem_fingerprint && row.matrix_fingerprint === instance.matrix_fingerprint &&
    (!('instance_id' in row) || row.instance_id === instance.instance_id) &&
    ['meters','map_units'].includes(instance.distance_units || '') && row.distance_units === instance.distance_units &&
    ['completed', 'incomplete'].includes(row.execution?.status || '');
}

export function savings(instance: InstanceResponse, result?: Measured | null, baseline?: Measured | null) {
  if (!verifiedMeasurement(instance, result) || !verifiedMeasurement(instance, baseline) || baseline.method !== 'nearest_neighbor' ||
      result.distance_units !== baseline.distance_units) return null;
  if (('instance_id' in result && !validFleet(instance,result)) ||
      ('instance_id' in baseline && !validFleet(instance,baseline))) return null;
  const absolute = baseline.total_distance - result.total_distance;
  return { absolute, percent: baseline.total_distance > 0 ? absolute / baseline.total_distance * 100 : null,
    baseline: baseline.total_distance, comparison: differenceText(result.total_distance, baseline.total_distance) };
}

export function savingsText(instance: InstanceResponse, result?: Measured | null, baseline?: Measured | null) {
  const value = savings(instance, result, baseline);
  if (!value) return 'Savings unavailable — a validated baseline on this same problem and matrix is required.';
  const amount = formatDistance(Math.abs(value.absolute), instance.mode);
  return `${amount} ${value.absolute < 0 ? 'longer' : 'saved'}${value.percent === null ? ' · percentage unavailable (zero baseline)' : ` · ${value.comparison}`}`;
}

export function completionText(row: Measured) {
  if (row.feasible !== true || row.execution?.status === 'failed') return 'Result not verified';
  if (row.execution?.status === 'incomplete') return row.execution.budget_exhausted
    ? 'Valid incumbent · search budget reached' : 'Valid incumbent · search stopped early';
  return row.execution?.status === 'completed' ? 'Calculation completed' : 'Validated route · completion not reported';
}

export function validFleet(instance: InstanceResponse, result: RoutingResultResponse) {
  if (!verifiedMeasurement(instance, result)) return false;
  try { validateRouteResult(instance, result); return true; } catch { return false; }
}

export interface RouteInsight { id: string; text: string; driverId: number | null; }
const operatorNames: Record<string, string> = { relocate:'Within-driver relocation', swap:'Within-driver swap',
  or_opt_2:'Two-stop relocation', two_opt:'2-Opt', cross_relocate:'Cross-driver relocation', cross_exchange:'Cross-driver exchange' };

/** Only measured events and route differences; never read a model rationale. */
export function routeInsights(instance: InstanceResponse, result: RoutingResultResponse, baseline?: RoutingResultResponse): RouteInsight[] {
  if (!validFleet(instance, result)) return [];
  const insights: RouteInsight[] = [];
  const events = result.execution?.raw_events || [];
  const gains = new Map<string, number>();
  let previous: number | null = null;
  for (const event of events) {
    if (!finiteDistance(event.retained_distance) || event.status === 'failed') { previous = null; continue; }
    if (previous !== null && event.stage === 'vnd' && operatorNames[event.method] &&
        event.raw_distance === event.retained_distance && event.retained_distance < previous && event.accepted) {
      gains.set(event.method, (gains.get(event.method) || 0) + previous - event.retained_distance);
    }
    previous = event.retained_distance;
  }
  // Retained-event gains must describe this published result, not an unrelated trace.
  if (previous === result.total_distance) {
    for (const [method, gain] of [...gains].sort((a,b)=>b[1]-a[1]).slice(0,2))
      insights.push({id:method, text:`${operatorNames[method]} reduced the best fleet distance by ${formatDistance(gain, instance.mode)} during this search.`, driverId:null});
    const last = events[events.length-1];
    const preceding = events[events.length-2];
    if (preceding && preceding.status !== 'failed' && preceding.retained_distance === last.retained_distance &&
        last?.stage === 'vnd' && !last.accepted && last.raw_distance != null && last.raw_distance >= last.retained_distance && operatorNames[last.method])
      insights.push({id:'last-pass',text:`The last recorded ${operatorNames[last.method]} pass did not improve the best validated route. This is not proof of optimality.`,driverId:null});
  }
  if (baseline && savings(instance,result,baseline) && validFleet(instance,baseline)) {
    const shorter = result.drivers.map(driver=>({driver, before:baseline.drivers.find(d=>d.driver_id===driver.driver_id)}))
      .filter(pair=>pair.before && pair.before.distance > pair.driver.distance)
      .sort((a,b)=>(b.before!.distance-b.driver.distance)-(a.before!.distance-a.driver.distance))[0];
    if (shorter) {
      const {driver,before}=shorter;
      const sameStops = [...driver.route].sort((a,b)=>a-b).join() === [...before!.route].sort((a,b)=>a-b).join();
      insights.push({id:`driver-${driver.driver_id}`,driverId:driver.driver_id,
        text:`Driver ${driver.driver_id+1} travels ${formatDistance(before!.distance-driver.distance,instance.mode)} less than ${baselineName}${sameStops ? ' with the same stops' : '; assigned stops differ'}. This is a route comparison, not attribution to an operator.`});
    }
  }
  return insights.slice(0,4);
}
