import type { RoutingResultResponse } from '../types/api';
import { formatDistance } from '../services/distance';
import { statusText } from '../services/product';

export function OptimizationDetails({ result, mode }: { result: RoutingResultResponse; mode: string }) {
  const e = result.execution;
  if (!e) return null;
  return <section className="panel stack optimization-details" aria-label="Optimization measurements">
    <div className="section-heading"><div><p className="eyebrow">Measured on this plan</p><h2>Optimization details</h2></div><span className={`badge ${e.status !== 'completed' ? 'warning' : ''}`}>{statusText(e.status)}</span></div>
    <p className="small muted">{statusText(e.termination)}. {e.budget_exhausted ? 'A search limit was reached. This is a feasible result within the budget, not proof of optimality.' : 'Every route was checked against the selected problem.'}</p>
    <dl className="execution-grid">
      {e.initial_distance != null && <div><dt>Initial construction</dt><dd>{formatDistance(e.initial_distance, mode)}</dd></div>}
      <div><dt>Final fleet distance</dt><dd>{formatDistance(result.total_distance, mode)}</dd></div>
      <div><dt>Longest driver route</dt><dd>{formatDistance(result.longest_route_distance, mode)}</dd></div>
      {e.improvement_percent != null && <div><dt>Reduction from construction</dt><dd>{e.improvement_percent.toFixed(2)}%</dd></div>}
      <div><dt>Solver runtime</dt><dd>{result.computation_time.toFixed(3)} s</dd></div>
      <div><dt>Work consumed</dt><dd>{e.operations == null ? 'Not instrumented (historical baseline)' : `${e.operations.toLocaleString()} / ${e.operation_limit?.toLocaleString()}`}</dd></div>
      <div><dt>Feasibility</dt><dd>{result.feasible ? 'Validated' : 'Not reported'}</dd></div>
      {e.accepted_moves != null && <div><dt>Accepted moves</dt><dd>{e.accepted_moves}</dd></div>}
    </dl>
    {e.initial_distance != null && <p className="small muted">Initial means the best validated constructor reached in this run. It is not a training score or a comparison with every historical baseline. Geometry retrieval time is separate from solver runtime.</p>}
    {!!e.raw_events?.length && <details><summary>Raw candidates and retained results</summary><p className="small muted">Raw proposals can be worse. The retained result tracks the best validated fleet seen so far.</p><div className="table-scroll"><table><thead><tr><th>Stage / operator</th><th>Raw distance</th><th>Retained distance</th><th>Status</th></tr></thead><tbody>{e.raw_events.map((event, index) => <tr key={index}><th>{statusText(event.stage)} / {statusText(event.method)}</th><td>{event.raw_distance == null ? 'Unavailable' : formatDistance(event.raw_distance, mode)}</td><td>{formatDistance(event.retained_distance, mode)}</td><td>{statusText(event.status)}</td></tr>)}</tbody></table></div></details>}
    {!!e.constructors?.length && <details><summary>Constructor attempts</summary><div className="table-scroll"><table><thead><tr><th>Constructor</th><th>Distance</th><th>Status</th></tr></thead><tbody>{e.constructors.map(c => <tr key={c.method}><th>{statusText(c.method)}</th><td>{c.distance == null ? 'Not measured' : formatDistance(c.distance, mode)}</td><td>{statusText(c.status)}</td></tr>)}</tbody></table></div></details>}
  </section>;
}
