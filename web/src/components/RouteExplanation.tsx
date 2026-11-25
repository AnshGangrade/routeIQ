import type { InstanceResponse, RoutingResultResponse } from '../types/api';
import { routeInsights } from '../services/routeEvidence';

export function RouteExplanation({instance,result,baseline,onFocus}: {
  instance:InstanceResponse; result:RoutingResultResponse; baseline?:RoutingResultResponse;
  onFocus:(driverId:number|null)=>void;
}) {
  const insights=routeInsights(instance,result,baseline);
  return <section className="route-explanation" aria-label="Why this route?">
    <h3>Why this route?</h3>
    {insights.length ? <ul>{insights.map(insight=><li key={insight.id}><p>{insight.text}</p>
      <button className="text-button" onClick={()=>onFocus(insight.driverId)}>{insight.driverId === null ? 'View fleet routes' : `View driver ${insight.driverId+1} route`}</button>
    </li>)}</ul> : <p className="small muted">No measured move-level explanation is available for this result. No improvement is inferred from a model rationale.</p>}
  </section>;
}
