import type { InstanceResponse, RoutingResultResponse, OptimizationJob } from '../types/api';

export function validateCompletedResult(instance: InstanceResponse, result: RoutingResultResponse) {
  validateRouteResult(instance,result);
  const e=result.execution;
  if (result.method==='strategy' && (e?.independently_validated!==true || e.schedule_completed!==true || e.route_validity!=='validated'))
    throw new Error('Strategy application did not return independent completion evidence.');
  if (result.feasible!==true || !instance.problem_fingerprint || !instance.matrix_fingerprint ||
      result.distance_units!==instance.distance_units || !e || e.status!=='completed' ||
      !['local_search_complete','no_perturbation_available','ils_iteration_limit','historical_baseline_complete'].includes(e.termination||'') ||
      e.schedule_completed===false || e.budget_exhausted || e.neighborhoods_truncated || e.search_status && e.search_status!=='completed')
    throw new Error('No completed validated search was returned. Previous routes were retained.');
  const sum=result.drivers.reduce((n,d)=>n+d.distance,0), longest=Math.max(...result.drivers.map(d=>d.distance));
  if (!Number.isFinite(result.longest_route_distance) || result.longest_route_distance<0 || !Number.isFinite(sum) || Math.abs(sum-result.total_distance)>1e-8*Math.max(1,sum) || Math.abs(longest-result.longest_route_distance)>1e-8*Math.max(1,longest))
    throw new Error('Route metrics failed validation. Previous routes were retained.');
}

export function completedOptimizationResult(instance:InstanceResponse, job:OptimizationJob) {
  if (job.status!=='completed' || job.published===false || !job.result) return null;
  if (job.instance_id!==instance.instance_id || job.problem_fingerprint!==instance.problem_fingerprint ||
      job.matrix_fingerprint!==instance.matrix_fingerprint || job.result.method!==job.method)
    throw new Error('Optimization result identity mismatch.');
  validateCompletedResult(instance,job.result);
  return job.result;
}

export const activeStatus = (status?: string) => !!status && ['pending', 'running', 'cancelling'].includes(status);
export const statusText = (value?: string) => ({ils_iteration_limit:'configured ILS iterations finished',
  controller_stop:'controller requested stop',operation_budget:'operation budget reached',
  deadline:'time deadline reached',operator_call_limit:'operator-call limit reached',
  neighborhood_limit:'neighborhood scan truncated',operator_error:'operator execution failed'} as Record<string,string>)[value||''] || (value || 'unavailable').replace(/_/g, ' ');

export function validateRouteResult(instance: InstanceResponse, result: RoutingResultResponse) {
  if (result.instance_id !== instance.instance_id ||
      instance.problem_fingerprint && result.problem_fingerprint !== instance.problem_fingerprint ||
      instance.matrix_fingerprint && result.matrix_fingerprint !== instance.matrix_fingerprint)
    throw new Error('The result belongs to another problem or distance matrix. Recalculate this plan.');
  if (result.feasible === false || !Number.isFinite(result.total_distance) || result.total_distance < 0)
    throw new Error('The server did not return a feasible route result.');
  const stops = result.drivers.flatMap(driver => driver.route.slice(1, -1));
  const expected = instance.stops.map(stop => stop.stop_id).sort((a, b) => a - b);
  if (result.drivers.length !== instance.num_drivers || new Set(result.drivers.map(d => d.driver_id)).size !== instance.num_drivers ||
    stops.sort((a, b) => a - b).join(',') !== expected.join(',') ||
    result.drivers.some(d => d.driver_id < 0 || d.driver_id >= instance.num_drivers || !Number.isInteger(d.driver_id) ||
      d.route.length < 2 || d.route[0] !== 0 || d.route[d.route.length - 1] !== 0 || d.route.slice(1, -1).includes(0) ||
      !Number.isFinite(d.distance) || d.distance < 0 ||
      d.route.length - 2 < (instance.workload?.minimum_stops[d.driver_id] ?? Math.floor(instance.num_stops / instance.num_drivers)) ||
      d.route.length - 2 > (instance.workload?.maximum_stops[d.driver_id] ?? Math.ceil(instance.num_stops / instance.num_drivers))))
    throw new Error('Route validation failed: each stop must appear once within the driver workload limits.');
}

/** One request at a time; cleanup aborts and prevents all late updates. */
export function watchTask<T extends { job_id?: string; status: string }>(
  id: string, fetcher: (id: string, signal: AbortSignal) => Promise<T>,
  update: (state: T, signal: AbortSignal) => void | Promise<void>, error: (message: string, terminal?: boolean) => void,
) {
  const controller = new AbortController();
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const poll = async () => {
    try {
      const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]);
      const data = await fetcher(id, signal);
      if (stopped) return;
      if (data.job_id !== id) throw new Error('Unexpected job identity. Progress was not applied.');
      await update(data, signal);
      if (!stopped && activeStatus(data.status)) timer = setTimeout(poll, 1500);
    } catch (reason) {
      if (stopped) return;
      const status = (reason as { status?: number } | null)?.status;
      const terminal = status === 404 || status === 410;
      error(reason instanceof Error ? reason.message : 'Progress unavailable. Retrying.', terminal);
      if (!terminal) timer = setTimeout(poll, 4000);
    }
  };
  void poll();
  return () => { stopped = true; clearTimeout(timer); controller.abort(); };
}
