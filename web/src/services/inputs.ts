export function parseCoordinatePair(lon: string, lat: string): [number, number] | null {
  if (!lon.trim() || !lat.trim()) return null;
  const pair: [number, number] = [Number(lon), Number(lat)];
  return pair.every(Number.isFinite) && Math.abs(pair[0]) <= 180 && Math.abs(pair[1]) <= 90 ? pair : null;
}

export function parseSeed(value: string): number | null {
  const seed = Number(value);
  return value.trim() && Number.isInteger(seed) && seed >= 0 && seed <= 4294960000 ? seed : null;
}
