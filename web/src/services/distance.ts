export function formatDistance(distance: number, mode: string): string {
  if (mode !== 'road') return `${distance.toFixed(2)} map units`;
  return distance >= 1000 ? `${(distance / 1000).toFixed(2)} km` : `${distance.toFixed(0)} m`;
}
