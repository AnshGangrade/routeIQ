import { formatDistance } from '../services/distance';
import type { RoutingResultResponse, InstanceResponse } from '../types/api';
import { completeDuration } from '../services/planning';
import { baselineName, completionText, savings, savingsText, validFleet } from '../services/routeEvidence';

interface Props { result: RoutingResultResponse; instance: InstanceResponse; results: Map<string, RoutingResultResponse>; }
export function CompactResults({ result, instance, results }: Props) {
  const baseline = results.get('nearest_neighbor');
  const saved = savings(instance, result, baseline);
  const feasible = validFleet(instance, result);
  const duration = instance.mode === 'road' ? completeDuration(result) : null;
  return <div><div className="route-summary" aria-label="Route summary">
    <div><span>Total distance</span><strong>{formatDistance(result.total_distance, instance.mode)}</strong></div>
    <div><span>Stops served</span><strong>{feasible ? `${instance.num_stops} / ${instance.num_stops}` : 'Not verified'}</strong></div>
    <div><span>Drivers</span><strong>{instance.num_drivers}</strong></div>
  </div><div className="route-outcome" aria-label="Measured route outcome">
    <p className="small"><strong>Baseline: {baselineName}</strong><br/>{saved ? formatDistance(saved.baseline,instance.mode) : 'Unavailable for a valid comparison'}</p>
    <p className="route-savings">{savingsText(instance,result,baseline)}</p>
    <p className="small">{feasible ? 'Feasible · every stop served exactly once' : 'Feasibility not verified'}<br/>{completionText(result)}</p>
    <p className="small muted">Calculation runtime: {Number.isFinite(result.computation_time) && result.computation_time >= 0 ? `${result.computation_time.toFixed(3)} s` : 'Unavailable'}. Road geometry retrieval is separate.</p>
    {duration != null && <p className="small">Driving time: {Math.round(duration/60)} min summed across drivers, not fleet finish time.</p>}
    <p className="small">Workload: {result.drivers.map(d=>`Driver ${d.driver_id+1}: ${Math.max(0,d.route.length-2)} stops`).join(' · ')}.</p>
  </div>{instance.mode === 'road' && result.drivers.some(driver => driver.route.length > 2 && (!driver.geometry?.length || driver.geometry_error)) && <p role="alert" className="notice">Road geometry unavailable for some drivers. Those paths are not drawn. Distances still use the road matrix; no straight-line road routes are substituted.</p>}</div>;
}
