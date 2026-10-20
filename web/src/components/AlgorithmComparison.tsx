import type { ComparisonResponse } from '../types/api';

interface AlgorithmComparisonProps {
  comparison: ComparisonResponse;
}

export function AlgorithmComparison({ comparison }: AlgorithmComparisonProps) {
  // Find best performing algorithm
  const bestMethod = comparison.comparisons.reduce((best, current) => 
    current.total_distance < best.total_distance ? current : best
  );

  return (
    <div className="bg-white rounded-lg border border-warm-border shadow-sm p-6">
      <h2 className="text-xl font-bold text-navy mb-4">Algorithm Comparison</h2>

      <div className="space-y-3">
        {comparison.comparisons.map(method => {
          const isBest = method.method === bestMethod.method;
          const isNegativeImprovement = method.improvement_vs_nn !== null && method.improvement_vs_nn < 0;

          return (
            <div 
              key={method.method}
              className={`p-4 rounded-lg border-2 ${
                isBest 
                  ? 'bg-green-50 border-green-500' 
                  : 'bg-slate-50 border-slate-200'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-slate-900">
                  {method.method === 'nearest_neighbor' ? 'Nearest Neighbor' :
                   method.method === '2opt' ? '2-Opt' :
                   'Evolved Heuristic'}
                </h3>
                {isBest && (
                  <span className="text-xs bg-green-600 text-white px-2 py-1 rounded-full font-medium">
                    BEST
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-slate-600">Total Distance:</span>
                  <p className="font-medium text-slate-900">
                    {method.total_distance.toFixed(2)}
                  </p>
                </div>
                <div>
                  <span className="text-slate-600">Max Route:</span>
                  <p className="font-medium text-slate-900">
                    {method.longest_route_distance.toFixed(2)}
                  </p>
                </div>
              </div>

              {method.improvement_vs_nn !== null && (
                <div className="mt-2 pt-2 border-t border-slate-200">
                  <span className="text-xs text-slate-600">vs Nearest Neighbor: </span>
                  <span className={`text-xs font-medium ${
                    isNegativeImprovement ? 'text-red-600' : 'text-green-600'
                  }`}>
                    {isNegativeImprovement ? '↓' : '↑'} {Math.abs(method.improvement_vs_nn).toFixed(1)}%
                  </span>
                </div>
              )}

              <div className="mt-1 text-xs text-slate-500">
                Computed in {(method.computation_time * 1000).toFixed(1)}ms
              </div>
            </div>
          );
        })}
      </div>

      {comparison.comparisons.length > 0 && (
        <div className="mt-4 p-3 bg-blue-50 rounded-lg text-xs text-slate-700 leading-relaxed">
          <strong>Note:</strong> Results show genuine measured performance. 
          The evolved heuristic may perform better or worse than baselines - both outcomes are valid research results.
        </div>
      )}
    </div>
  );
}
