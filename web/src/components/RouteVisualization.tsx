import { driverColor } from '../services/presentation';
import { useMemo, useState } from 'react';
import { InteractiveMap } from './InteractiveMap';
import type { InstanceResponse, RoutingResultResponse } from '../types/api';
import { methodNames, type Method } from '../services/workflow';

interface RouteVisualizationProps {
  instance: InstanceResponse | null;
  routingResult: RoutingResultResponse | null;
  onMethodSelect: (method: string) => void;
  selectedMethod: string;
  availableMethods: string[];
  configVisible?: boolean; // Pass down to InteractiveMap
  selectedDriverId?: number | null;
  onDriverSelect?: (id: number | null) => void;
}

export function RouteVisualization({
  instance,
  routingResult,
  onMethodSelect,
  selectedMethod,
  availableMethods,
  configVisible,
  selectedDriverId: controlledDriver,
  onDriverSelect,
}: RouteVisualizationProps) {
  const [localDriver, setLocalDriver] = useState<number | null>(null);
  const selectedDriverId = controlledDriver === undefined ? localDriver : controlledDriver;
  const setSelectedDriverId = onDriverSelect || setLocalDriver;

  // Calculate view bounds (for SVG mode)
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
    const paddingX = (maxX - minX) * 0.15 || 5;
    const paddingY = (maxY - minY) * 0.15 || 5;

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

  // Empty state - no instance generated yet
  if (!instance) {
    return (
      <div className="card-elevated content-padding">
        <h2 className="editorial-heading mb-6">Route Visualization</h2>
        <div className="flex flex-col items-center justify-center min-h-[500px] bg-[#fafaf9] rounded-lg border-2 border-dashed border-[#eceae4]">
          <div className="text-center space-y-4 max-w-md px-6">
            <p className="text-lg font-semibold text-[#5f5f5d]">No instance generated</p>
            <p className="text-sm text-[#5f5f5d] leading-relaxed">
              Use the configuration panel to generate an instance. Choose synthetic coordinates
              or real road network mode, specify stops and drivers, then generate.
            </p>
            <div className="pt-4">
              <p className="mono-label text-[10px] text-[#5f5f5d]">
                Configure → Generate → Solve → Visualize
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const isRoadMode = instance.mode === 'road';

  return (
    <div className="panel map-panel">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2>Your route map</h2>
          <p className="text-sm text-[#5f5f5d] mt-1">
            {isRoadMode ? (
              <>Real road network · OSRM routing</>
            ) : (
              <>Synthetic demo · straight-line distances</>
            )}
          </p>
        </div>

        {availableMethods.length > 0 && (
          <select
            aria-label="Displayed route method"
            value={selectedMethod}
            onChange={(e) => onMethodSelect(e.target.value)}
            className="px-3 py-2 text-sm border border-[#eceae4] rounded-md focus:ring-2 focus:ring-[#0d9488] focus:border-transparent bg-white"
          >
            {availableMethods.map(method => (
              <option key={method} value={method}>
                {methodNames[method as Method] || method}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Map or SVG Visualization */}
      {isRoadMode ? (
        /* Interactive Leaflet Map for Road Mode */
        <InteractiveMap
          instance={instance}
          routingResult={routingResult}
          selectedDriverId={selectedDriverId}
          onDriverSelect={setSelectedDriverId}
          configVisible={configVisible}
        />
      ) : (
        /* SVG Coordinate Plot for Synthetic Mode */
        <div className="bg-[#fafaf9] rounded-lg p-4 border border-[#eceae4]">
          {!routingResult && (
            <div className="mb-3 p-3 bg-[#fffbeb] border border-[#fbbf24]/30 rounded-md">
              <p className="text-xs text-[#92400e] font-medium">
                Routes not yet calculated. Run a routing algorithm to see optimized paths.
              </p>
            </div>
          )}

          <svg
            role="img"
            aria-label="Synthetic route map showing the depot, numbered delivery stops, and driver routes"
            viewBox="0 0 800 600"
            className="w-full h-auto bg-white rounded border border-[#eceae4]"
            style={{ maxHeight: '600px' }}
          >
            {/* Background grid */}
            <defs>
              <pattern id="smallGrid" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#eceae4" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#smallGrid)" />

            {/* Routes (if solved) */}
            {routingResult && routingResult.drivers.map(driver => {
              const color = driverColor(driver.driver_id);
              const isSelected = selectedDriverId === null || selectedDriverId === driver.driver_id;

              if (!isSelected) return null;

              return (
                <g key={driver.driver_id} opacity="0.8">
                  {/* Draw route segments */}
                  {driver.route.map((stopId, idx) => {
                    if (idx === driver.route.length - 1) return null; // Skip last point (no segment after it)

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
                        strokeWidth="3"
                        strokeLinecap="round"
                        opacity="0.7"
                      />
                    );
                  })}
                </g>
              );
            })}

            {/* Depot */}
            {(() => {
              const [dx, dy] = toSVG(
                instance.depot.x ?? instance.depot.lon ?? 0,
                instance.depot.y ?? instance.depot.lat ?? 0
              );
              return (
                <g>
                  <rect
                    x={dx - 10}
                    y={dy - 10}
                    width="20"
                    height="20"
                    fill="#B95E42"
                    stroke="#8d432d"
                    strokeWidth="2"
                    rx="2"
                  />
                  <text
                    x={dx}
                    y={dy - 16}
                    textAnchor="middle"
                    fontSize="11"
                    fontWeight="bold"
                    fontFamily="IBM Plex Mono"
                    fill="#B95E42"
                  >
                    DEPOT
                  </text>
                </g>
              );
            })()}

            {/* Stops */}
            {instance.stops.map(stop => {
              const [sx, sy] = toSVG(stop.x, stop.y);

              // Find which driver is assigned to this stop
              let assignedColor = '#94a3b8'; // Default gray
              if (routingResult) {
                const driver = instance.drivers.find(d =>
                  routingResult.drivers.find(dr =>
                    dr.driver_id === d.driver_id &&
                    dr.route.includes(stop.stop_id)
                  )
                );
                if (driver) {
                  const isSelected = selectedDriverId === null || selectedDriverId === driver.driver_id;
                  assignedColor = isSelected ? driverColor(driver.driver_id) : '#cbd5e1';
                }
              }

              return (
                <g key={stop.stop_id}>
                  {/* Stop marker circle */}
                  <circle
                    cx={sx}
                    cy={sy}
                    r="12"
                    fill={assignedColor}
                    stroke="white"
                    strokeWidth="2.5"
                  />
                  {/* Stop number */}
                  <text
                    x={sx}
                    y={sy}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize="11"
                    fontWeight="bold"
                    fontFamily="IBM Plex Mono"
                    fill="white"
                  >
                    {stop.stop_id}
                  </text>
                </g>
              );
            })}
          </svg>

          <p className="mt-3 text-xs text-[#5f5f5d] italic">
            Synthetic coordinates with Euclidean (straight-line) distances. Not actual road distances.
          </p>
        </div>
      )}

      {/* Unified Legend */}
      <div className="mt-4 flex flex-wrap gap-4 items-center">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-red-600 border-2 border-red-800 rounded-sm"></div>
          <span className="text-sm text-[#5f5f5d] font-medium">Depot</span>
        </div>
        {instance.drivers.map(driver => (
          <button
            key={driver.driver_id}
            aria-pressed={selectedDriverId === driver.driver_id}
            className="flex items-center gap-2 hover:opacity-70 transition-opacity"
            onClick={() => setSelectedDriverId(
              selectedDriverId === driver.driver_id ? null : driver.driver_id
            )}
          >
            <div
              className={`w-4 h-4 rounded-full border-2 ${
                selectedDriverId === null || selectedDriverId === driver.driver_id
                  ? 'border-white shadow-sm'
                  : 'border-[#eceae4] opacity-40'
              }`}
              style={{ backgroundColor: driverColor(driver.driver_id) }}
            ></div>
            <span className={`text-sm ${
              selectedDriverId === null || selectedDriverId === driver.driver_id
                ? 'text-[#5f5f5d] font-medium'
                : 'text-[#5f5f5d]/40'
            }`}>
              {driver.name}
            </span>
          </button>
        ))}
        {selectedDriverId !== null && (
          <button
            onClick={() => setSelectedDriverId(null)}
            className="text-xs text-[#0d9488] hover:text-[#0f766e] ml-2 font-semibold"
          >
            Show All
          </button>
        )}
      </div>
    </div>
  );
}
