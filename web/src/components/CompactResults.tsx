import { formatDistance } from '../services/distance';
import type { RoutingResultResponse, InstanceResponse } from '../types/api';

interface Props { result: RoutingResultResponse; instance: InstanceResponse; results: Map<string, RoutingResultResponse>; }
export function CompactResults({ result, instance }: Props) {
  return <div><div className="route-summary" aria-label="Route summary">
    <div><span>Total distance</span><strong>{formatDistance(result.total_distance, instance.mode)}</strong></div>
    <div><span>Delivery stops</span><strong>{instance.num_stops}</strong></div>
    <div><span>Drivers</span><strong>{instance.num_drivers}</strong></div>
  </div>{instance.mode === 'road' && result.drivers.some(driver => driver.route.length > 2 && (!driver.geometry?.length || driver.geometry_error)) && <p role="alert" className="notice">Road geometry unavailable for some drivers. Those paths are not drawn. Distances still use the road matrix; no straight-line road routes are substituted.</p>}</div>;
}
