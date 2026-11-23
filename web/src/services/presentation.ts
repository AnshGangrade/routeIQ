/** Presentation only: never changes API data, assignments, objectives or distances. */
export const routePalette = ['#287776', '#B95E42', '#806A9C', '#587B56', '#376D96', '#A37B33', '#9C5975', '#4E8288', '#68794C', '#646DAD'];
export const driverColor = (id: number) => routePalette[((id % routePalette.length) + routePalette.length) % routePalette.length];
export const sourceLabel = (source: string, offline = false) => source === 'llm' && offline ? 'Offline fixture (not an LLM)' : ({seed:'Hand-authored',random:'Random',llm:'LLM proposal',mutation:'Mutation',crossover:'Crossover'}[source] || source);

export function finiteSeries(values: Array<number | null | undefined>) {
  const finite = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0);
  return { min: finite.length ? Math.min(...finite) : 0, max: finite.length ? Math.max(...finite) : 0, count: finite.length };
}
