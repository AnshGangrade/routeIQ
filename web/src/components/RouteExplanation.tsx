import type { InstanceResponse, RoutingResultResponse } from '../types/api';
import { routeInsights } from '../services/routeEvidence';

export function RouteExplanation({instance,result,baseline,onFocus}: {
  instance:InstanceResponse; result:RoutingResultResponse; baseline?:RoutingResultResponse;
  onFocus:(driverId:number|null)=>void;
}) {
  const insights=routeInsights(instance,result,baseline);
  if (!insights.length) return null;
  return <section className="route-explanation" aria-label="Why this route?">
    <h3>Why this route?</h3>
    <ul>{insights.map(insight=><li key={insight.id}><p>{insight.text}</p>
      <button className="text-button" onClick={()=>onFocus(insight.driverId)}>{insight.driverId === null ? 'View fleet routes' : `View driver ${insight.driverId+1} route`}</button>
    </li>)}</ul>
  </section>;
}
