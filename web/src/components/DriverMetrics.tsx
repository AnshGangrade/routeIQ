import type { RoutingResultResponse } from '../types/api';

interface DriverMetricsProps {
  result: RoutingResultResponse;
}

export function DriverMetrics({ result }: DriverMetricsProps) {
  const longestDriver = result.drivers.reduce((longest, current) =>
    current.distance > longest.distance ? current : longest
  );

  return (
    <div className="bg-white rounded-lg border border-warm-border shadow-sm p-6">
      <h2 className="text-xl font-bold text-navy mb-4">Driver Metrics</h2>

      <div className="grid gap-4">
        {/* Summary cards */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <div className="text-xs text-slate-600 mb-1">Total Fleet Distance</div>
            <div className="text-2xl font-bold text-navy">
              {result.total_distance.toFixed(2)}
            </div>
          </div>
          <div className="p-4 bg-orange-50 rounded-lg border border-orange-200">
            <div className="text-xs text-slate-600 mb-1">Longest Driver Route</div>
            <div className="text-2xl font-bold text-navy">
              {result.longest_route_distance.toFixed(2)}
            </div>
          </div>
        </div>

        {/* Per-driver breakdown */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
            Per-Driver Routes
          </h3>
          {result.drivers.map(driver => {
            const isLongest = driver.driver_id === longestDriver.driver_id;
            const stopCount = driver.route.filter(id => id !== 0).length;

            return (
              <div 
                key={driver.driver_id}
                className={`p-3 rounded-lg border ${
                  isLongest 
                    ? 'bg-orange-50 border-orange-300' 
                    : 'bg-slate-50 border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-slate-900">
                    Driver {driver.driver_id + 1}
                  </span>
                  {isLongest && (
                    <span className="text-xs bg-orange-600 text-white px-2 py-0.5 rounded-full">
                      LONGEST
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div>
                    <span className="text-slate-600">Distance:</span>
                    <p className="font-medium">{driver.distance.toFixed(2)}</p>
                  </div>
                  <div>
                    <span className="text-slate-600">Stops:</span>
                    <p className="font-medium">{stopCount}</p>
                  </div>
                  <div>
                    <span className="text-slate-600">% of Total:</span>
                    <p className="font-medium">
                      {((driver.distance / result.total_distance) * 100).toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
