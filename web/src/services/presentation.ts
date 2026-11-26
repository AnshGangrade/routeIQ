/** Presentation only: never changes API data, assignments, objectives or distances. */
export const routePalette = ['#426582', '#39736d', '#65774b', '#a5634d', '#78648c', '#94712d', '#47579a', '#8f536b', '#477d8b', '#766148',
  '#51426d', '#28615b', '#547131', '#865140', '#936582', '#786223', '#304f78', '#7a3e58', '#356273', '#625442'];
export const driverColor = (id: number) => routePalette[((id % routePalette.length) + routePalette.length) % routePalette.length];
/** Shared SVG/Leaflet styling; route coordinates and measurement data stay untouched. */
export function mapRouteStyle(method: string, selected: boolean, driverId = 0) {
  const baseline = method === 'nearest_neighbor' || method === '2opt';
  return { color: driverColor(driverId),
    weight: selected ? 4 : 2.5, opacity: selected ? 1 : .65,
    dashArray: baseline ? '8 6' : [undefined, '10 3', '3 4'][Math.abs(driverId) % 3],
    casing: selected && !baseline };
}
export const sourceLabel = (source: string, offline = false) => source === 'llm' && offline ? 'Offline fixture (not an LLM)' : ({seed:'Hand-authored',random:'Random',llm:'LLM proposal',mutation:'Mutation',crossover:'Crossover'}[source] || source);

export function finiteSeries(values: Array<number | null | undefined>) {
  const finite = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0);
  return { min: finite.length ? Math.min(...finite) : 0, max: finite.length ? Math.max(...finite) : 0, count: finite.length };
}

/** A completed generation loop does not mean every bounded evaluation completed. */
export function experimentStatus(state: import('../types/api').StrategyExperiment) {
  const records=Object.values(state.records||{});
  if(state.status==='completed' && records.some(r=>r.fitness.failed>0)) return 'Finished with evaluation failures';
  if(state.status==='completed' && records.some(r=>r.fitness.incomplete>0)) return 'Finished with incomplete evaluations';
  return state.status.replace(/_/g,' ');
}
