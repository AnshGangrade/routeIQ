import { driverColor, mapRouteStyle } from '../services/presentation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { InteractiveMap } from './InteractiveMap';
import type { InstanceResponse, RoutingResultResponse } from '../types/api';
import { methodNames, type Method } from '../services/workflow';

interface RouteVisualizationProps {
  selectedStopId?: number | null;
  onStopSelect?: (id: number) => void;
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
  selectedStopId = null,
  onStopSelect,
}: RouteVisualizationProps) {
  const [localDriver, setLocalDriver] = useState<number | null>(null);
  const selectedDriverId = controlledDriver === undefined ? localDriver : controlledDriver;
  const setSelectedDriverId = onDriverSelect || setLocalDriver;

  // Keep labels and interactive targets readable when the map panel resizes.
  const svgRef = useRef<SVGSVGElement>(null);
  const [markerScale, setMarkerScale] = useState(1);
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const observer = new ResizeObserver(([entry]) => {
      const {width, height} = entry.contentRect;
      if (width > 0 && height > 0) setMarkerScale(1 / Math.min(width / 800, height / 600));
    });
    observer.observe(svg);
    return () => observer.disconnect();
  }, [instance?.instance_id, instance?.mode]);
  const markerTransform = (x:number,y:number) => `translate(${x} ${y}) scale(${markerScale}) translate(${-x} ${-y})`;

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
        <div className="flex flex-col items-center justify-center min-h-[500px] bg-[var(--color-surface-secondary)] rounded-lg border-2 border-dashed border-[var(--color-border)]">
          <div className="text-center space-y-4 max-w-md px-6">
            <p className="text-lg font-semibold text-[var(--color-text-muted)]">No instance generated</p>
            <p className="text-sm text-[var(--color-text-muted)] leading-relaxed">
              Use the configuration panel to generate an instance. Choose synthetic coordinates
              or real road network mode, specify stops and drivers, then generate.
            </p>
            <div className="pt-4">
              <p className="mono-label text-[10px] text-[var(--color-text-muted)]">
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
          <p className="text-sm text-[var(--color-text-muted)] mt-1">
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
            className="px-3 py-2 text-sm border border-[var(--color-border)] rounded-md focus:ring-2 focus:ring-[var(--color-text)] focus:border-transparent bg-white"
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
          selectedStopId={selectedStopId}
          onStopSelect={onStopSelect}
        />
      ) : (
        /* SVG Coordinate Plot for Synthetic Mode */
        <div className="bg-[var(--color-surface-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          {!routingResult && (
            <div className="mb-3 p-3 bg-[var(--color-surface-secondary)] border border-[var(--color-primary)]/30 rounded-md">
              <p className="text-xs text-[var(--color-text)] font-medium">
                Routes not yet calculated. Run a routing algorithm to see optimized paths.
              </p>
            </div>
          )}

          <svg
            ref={svgRef}
            role="img"
            aria-label="Synthetic route map showing the depot, numbered delivery stops, and driver routes"
            viewBox="0 0 800 600"
            className="w-full h-auto bg-white rounded border border-[var(--color-border)]"
            style={{ maxHeight: '600px' }}
          >
            {/* Background grid */}
            <defs>
              <pattern id="smallGrid" width="20" height="20" patternUnits="userSpaceOnUse">
                <path d="M 20 0 L 0 0 0 20" fill="none" stroke="var(--color-border)" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#smallGrid)" />

            {/* Routes (if solved) */}
            {routingResult && routingResult.drivers.map(driver => {
              const isSelected = selectedDriverId === null || selectedDriverId === driver.driver_id;
              const style = mapRouteStyle(routingResult.method,isSelected,driver.driver_id);

              return (
                <g key={driver.driver_id}>
                  {/* Draw route segments */}
                  {driver.route.map((stopId, idx) => {
                    if (idx === driver.route.length - 1) return null; // Skip last point (no segment after it)

                    const nextStopId = driver.route[idx + 1];
                    if (stopId === nextStopId) return null; // Idle depot-to-depot route has no visible segment.

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
                      <g key={`${stopId}-${nextStopId}`}>
                      {style.casing && <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--color-text)" strokeWidth="7" strokeLinecap="round"/>}
                      <line
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        stroke={style.color}
                        strokeWidth={style.weight}
                        strokeDasharray={style.dashArray}
                        strokeLinecap="round"
                        opacity={style.opacity}
                      />
                      </g>
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
                <g transform={markerTransform(dx,dy)}>
                  <rect
                    x={dx - 10}
                    y={dy - 10}
                    width="20"
                    height="20"
                    fill="var(--color-text)"
                    stroke="var(--color-text)"
                    strokeWidth="2"
                    rx="2"
                  />
                  <circle cx={dx} cy={dy} r="5" fill="var(--color-primary)"/>
                  <text
                    x={dx}
                    y={dy - 16}
                    textAnchor="middle"
                    fontSize="11"
                    fontWeight="bold"
                    fontFamily="IBM Plex Mono"
                    fill="var(--color-text)"
                  >
                    DEPOT
                  </text>
                </g>
              );
            })()}

            {/* Stops */}
            {instance.stops.map(stop => {
              const [sx, sy] = toSVG(stop.x, stop.y);

              const focused = selectedStopId === stop.stop_id;
              const owner = routingResult?.drivers.find(d=>d.route.includes(stop.stop_id));
              const color = owner ? driverColor(owner.driver_id) : "var(--color-primary-deep)";

              return (
                <g key={stop.stop_id} transform={markerTransform(sx,sy)} role="button" tabIndex={0} aria-label={`Delivery stop ${stop.stop_id}`} aria-pressed={selectedStopId === stop.stop_id}
                  onClick={() => onStopSelect?.(stop.stop_id)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onStopSelect?.(stop.stop_id);}}}>
                  <circle cx={sx} cy={sy} r="18" fill="transparent"/>
                  {focused && <circle cx={sx} cy={sy} r="18" fill="none" stroke="var(--color-text)" strokeWidth="2"/>}
                  {/* Stop marker circle */}
                  <circle
                    cx={sx}
                    cy={sy}
                    r="12"
                    fill={color}
                    stroke="var(--color-text)"
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

          <p className="mt-3 text-xs text-[var(--color-text-muted)] italic">
            Synthetic coordinates with Euclidean (straight-line) distances. Not actual road distances.
          </p>
        </div>
      )}

      {/* Unified Legend */}
      <div className="mt-4 flex flex-wrap gap-4 items-center">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 depot-key border-2 rounded-sm"></div>
          <span className="text-sm text-[var(--color-text-muted)] font-medium">Depot</span>
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
                  : 'border-[var(--color-border)] opacity-40'
              }`}
              style={{ backgroundColor: mapRouteStyle(selectedMethod,selectedDriverId === null || selectedDriverId === driver.driver_id,driver.driver_id).color }}
            ></div>
            <span className={`text-sm ${
              selectedDriverId === null || selectedDriverId === driver.driver_id
                ? 'text-[var(--color-text-muted)] font-medium'
                : 'text-[var(--color-text-muted)]/40'
            }`}>
              {driver.name}
            </span>
          </button>
        ))}
        {selectedDriverId !== null && (
          <button
            onClick={() => setSelectedDriverId(null)}
            className="text-xs text-[var(--color-text)] hover:underline ml-2 font-semibold"
          >
            Show All
          </button>
        )}
      </div>
    </div>
  );
}
