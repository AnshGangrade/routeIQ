/** Presentation only: never changes API data, assignments, objectives or distances. */
export const routePalette = ['#151515', '#303030', '#484848', '#606060', '#242424', '#3c3c3c', '#545454', '#686868', '#1e1e1e', '#424242'];
export const driverColor = (id: number) => routePalette[((id % routePalette.length) + routePalette.length) % routePalette.length];
/** Shared SVG/Leaflet styling; route coordinates and measurement data stay untouched. */
export function mapRouteStyle(method: string, selected: boolean) {
  const baseline = method === 'nearest_neighbor' || method === '2opt';
  return { color: selected && !baseline ? '#F3C63B' : '#151515',
    weight: selected ? 4 : 3, opacity: selected ? 1 : .35,
    dashArray: baseline ? '8 6' : selected ? undefined : '3 7',
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
