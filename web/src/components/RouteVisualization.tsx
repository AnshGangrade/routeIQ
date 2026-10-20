import { useMemo } from 'react';
import type { InstanceResponse, RoutingResultResponse } from '../types/api';

interface RouteVisualizationProps {
  instance: InstanceResponse | null;
  routingResult: RoutingResultResponse | null;
  onMethodSelect: (method: string) => void;
  selectedMethod: string;
  availableMethods: string[];
}

export function RouteVisualization({
  instance,
  routingResult,
  onMethodSelect,
  selectedMethod,
  availableMethods,
}: RouteVisualizationProps) {
  // Calculate view bounds
  const bounds = useMemo(() => {
    if (!instance) return { minX: 0, maxX: 100, minY: 0, maxY: 100 };

    const allPoints = [
      { x: instance.depot.x ?? instance.depot.lon ?? 0, y: instance.depot.y ?? instance.depot.lat ?? 0 },
      ...instance.stops.map(s => ({ x: s.x ?? 0, y: s.y ?? 0 })),
    ];

    const xs = allPoints.map(p => p.x);
    const ys = allPoints.map(p => p.y);

    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    // Add padding
    const paddingX = (maxX - minX) * 0.1 || 1;
    const paddingY = (maxY - minY) * 0.1 || 1;

    return {
      minX: minX - paddingX,
      maxX: maxX + paddingX,
      minY: minY - paddingY,
      maxY: maxY + paddingY,
    };
  }, [instance]);

  // Transform coordinate to SVG space
  const toSVG = (x: number, y: number): [number, number] => {
    const width = 800;
    const height = 600;
    const svgX = ((x - bounds.minX) / (bounds.maxX - bounds.minX)) * width;
    // Flip Y axis (SVG Y increases downward)
    const svgY = height - ((y - bounds.minY) / (bounds.maxY - bounds.minY)) * height;
    return [svgX, svgY];
  };

  if (!instance) {
    return (
      <div className="bg-white rounded-lg border border-warm-border shadow-sm p-6">
        <h2 className="text-2xl font-bold text-navy mb-4">Route Visualization</h2>
        <div className="flex items-center justify-center h-96 bg-slate-50 rounded-lg border-2 border-dashed border-slate-300">
          <p className="text-slate-500 text-center">
            Generate an instance to visualize routes
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-warm-border shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold text-navy">Route Visualization</h2>
        
        {availableMethods.length > 0 && (
          <select
            value={selectedMethod}
            onChange={(e) => onMethodSelect(e.target.value)}
            className="px-3 py-1 text-sm border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500"
          >
            {availableMethods.map(method => (
              <option key={method} value={method}>
                {method === 'nearest_neighbor' ? 'Nearest Neighbor' : 
                 method === '2opt' ? '2-Opt' : 
                 'Evolved'}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="bg-slate-50 rounded-lg p-4">
        <svg 
          viewBox="0 0 800 600" 
          className="w-full h-auto border border-slate-200 rounded bg-white"
          style={{ maxHeight: '500px' }}
        >
          {/* Routes */}
          {routingResult && routingResult.drivers.map(driver => {
            const driverInfo = instance.drivers.find(d => d.driver_id === driver.driver_id);
            const color = driverInfo?.color || '#666';

            return (
              <g key={driver.driver_id}>
                {/* Draw route segments */}
                {driver.route.slice(0, -1).map((stopId, idx) => {
                  const nextStopId = driver.route[idx + 1];
                  
                  const currentPoint = stopId === 0 
                    ? instance.depot 
                    : instance.stops.find(s => s.stop_id === stopId);
                  const nextPoint = nextStopId === 0 
                    ? instance.depot 
                    : instance.stops.find(s => s.stop_id === nextStopId);

                  if (!currentPoint || !nextPoint) return null;

                  const [x1, y1] = toSVG(currentPoint.x ?? 0, currentPoint.y ?? 0);
                  const [x2, y2] = toSVG(nextPoint.x ?? 0, nextPoint.y ?? 0);

                  return (
                    <line
                      key={`${stopId}-${nextStopId}`}
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      stroke={color}
                      strokeWidth="2"
                      opacity="0.6"
                    />
                  );
                })}
              </g>
            );
          })}

          {/* Depot */}
          {(() => {
            const [dx, dy] = toSVG(instance.depot.x ?? instance.depot.lon ?? 0, instance.depot.y ?? instance.depot.lat ?? 0);
            return (
              <g>
                <rect
                  x={dx - 8}
                  y={dy - 8}
                  width="16"
                  height="16"
                  fill="#dc2626"
                  stroke="#991b1b"
                  strokeWidth="2"
                />
                <text
                  x={dx}
                  y={dy - 14}
                  textAnchor="middle"
                  fontSize="12"
                  fontWeight="bold"
                  fill="#dc2626"
                >
                  DEPOT
                </text>
              </g>
            );
          })()}

          {/* Stops */}
          {instance.stops.map(stop => {
            const [sx, sy] = toSVG(stop.x, stop.y);
            const driver = instance.drivers.find(d => 
              routingResult?.drivers.find(dr => 
                dr.driver_id === d.driver_id && 
                dr.route.includes(stop.stop_id)
              )
            );
            const color = driver?.color || '#64748b';

            return (
              <g key={stop.stop_id}>
                <circle
                  cx={sx}
                  cy={sy}
                  r="6"
                  fill={color}
                  stroke="white"
                  strokeWidth="2"
                />
                <text
                  x={sx}
                  y={sy + 18}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#475569"
                >
                  {stop.stop_id}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Legend */}
        <div className="mt-4 flex flex-wrap gap-4">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-red-600 border-2 border-red-800"></div>
            <span className="text-sm text-slate-700">Depot</span>
          </div>
          {instance.drivers.map(driver => (
            <div key={driver.driver_id} className="flex items-center gap-2">
              <div 
                className="w-4 h-4 rounded-full border-2 border-white"
                style={{ backgroundColor: driver.color }}
              ></div>
              <span className="text-sm text-slate-700">{driver.name}</span>
            </div>
          ))}
        </div>

        <p className="mt-4 text-xs text-slate-500 italic">
          Note: Coordinates are synthetic. Distances are Euclidean (straight-line), not road distances.
        </p>
      </div>
    </div>
  );
}
