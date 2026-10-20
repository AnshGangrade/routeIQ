import { useMemo } from 'react';
import type { EvolutionProgressResponse } from '../types/api';

interface EvolutionProgressProps {
  evolution: EvolutionProgressResponse;
}

export function EvolutionProgress({ evolution }: EvolutionProgressProps) {
  // Calculate fitness trend
  const fitnessData = useMemo(() => {
    return evolution.generations.map(gen => {
      // Calculate average fitness of valid candidates
      const validCandidates = gen.candidates.filter(c => c.is_valid && c.fitness !== null);
      const avgFitness = validCandidates.length > 0
        ? validCandidates.reduce((sum, c) => sum + (c.fitness || 0), 0) / validCandidates.length
        : null;

      return {
        generation: gen.generation,
        bestFitness: gen.best_fitness,
        avgFitness,
        validCount: gen.valid_count,
        invalidCount: gen.invalid_count,
      };
    });
  }, [evolution.generations]);

  // Calculate chart dimensions
  const chartStats = useMemo(() => {
    if (fitnessData.length === 0) return null;

    const allFitness = fitnessData
      .flatMap(d => [d.bestFitness, d.avgFitness])
      .filter((f): f is number => f !== null);

    if (allFitness.length === 0) return null;

    const minFitness = Math.min(...allFitness);
    const maxFitness = Math.max(...allFitness);
    const range = maxFitness - minFitness || 1;

    return { minFitness, maxFitness, range };
  }, [fitnessData]);

  const getBestCandidate = () => {
    if (!evolution.best_heuristic_id) return null;

    for (const gen of evolution.generations) {
      const candidate = gen.candidates.find(c => c.heuristic_id === evolution.best_heuristic_id);
      if (candidate) return candidate;
    }
    return null;
  };

  const bestCandidate = getBestCandidate();

  return (
    <div className="bg-white rounded-lg border border-warm-border shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-navy">Evolution Progress</h2>
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-xs font-medium ${
            evolution.status === 'completed' ? 'bg-green-100 text-green-700' :
            evolution.status === 'running' ? 'bg-blue-100 text-blue-700' :
            evolution.status === 'failed' ? 'bg-red-100 text-red-700' :
            'bg-slate-100 text-slate-700'
          }`}>
            {evolution.status.toUpperCase()}
          </span>
          <span className="text-sm text-slate-600">
            Gen {evolution.current_generation}/{evolution.total_generations}
          </span>
        </div>
      </div>

      {evolution.error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <strong>Error:</strong> {evolution.error}
        </div>
      )}

      {/* Fitness Chart */}
      {fitnessData.length > 0 && chartStats && (
        <div className="mb-6">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
              Fitness Progression
            </h3>
            <span className="text-xs text-slate-500">
              Lower is better (total route distance)
            </span>
          </div>
          
          {/* Line Chart */}
          <div className="relative bg-slate-50 p-6 rounded-lg border border-slate-200" style={{ height: '240px' }}>
            {/* Y-axis labels */}
            <div className="absolute left-0 top-6 bottom-6 w-16 flex flex-col justify-between text-xs text-slate-500 text-right pr-2">
              <span>{chartStats.maxFitness.toFixed(0)}</span>
              <span>{((chartStats.maxFitness + chartStats.minFitness) / 2).toFixed(0)}</span>
              <span>{chartStats.minFitness.toFixed(0)}</span>
            </div>

            {/* Chart area */}
            <div className="absolute left-20 right-6 top-6 bottom-12">
              <svg className="w-full h-full" viewBox="0 0 300 150" preserveAspectRatio="none">
                {/* Grid lines */}
                <line x1="0" y1="0" x2="300" y2="0" stroke="#e2e8f0" strokeWidth="1" />
                <line x1="0" y1="75" x2="300" y2="75" stroke="#e2e8f0" strokeWidth="1" strokeDasharray="4" />
                <line x1="0" y1="150" x2="300" y2="150" stroke="#e2e8f0" strokeWidth="1" />

                {/* Best fitness line */}
                {fitnessData.length > 1 && (
                  <polyline
                    points={fitnessData
                      .map((d, i) => {
                        if (d.bestFitness === null) return null;
                        const x = (i / (fitnessData.length - 1)) * 300;
                        const y = 150 - ((d.bestFitness - chartStats.minFitness) / chartStats.range) * 150;
                        return `${x},${y}`;
                      })
                      .filter(Boolean)
                      .join(' ')}
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}

                {/* Average fitness line */}
                {fitnessData.length > 1 && (
                  <polyline
                    points={fitnessData
                      .map((d, i) => {
                        if (d.avgFitness === null) return null;
                        const x = (i / (fitnessData.length - 1)) * 300;
                        const y = 150 - ((d.avgFitness - chartStats.minFitness) / chartStats.range) * 150;
                        return `${x},${y}`;
                      })
                      .filter(Boolean)
                      .join(' ')}
                    fill="none"
                    stroke="#94a3b8"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeDasharray="4"
                  />
                )}

                {/* Data points */}
                {fitnessData.map((d, i) => {
                  if (d.bestFitness === null) return null;
                  const x = (i / (fitnessData.length - 1)) * 300;
                  const y = 150 - ((d.bestFitness - chartStats.minFitness) / chartStats.range) * 150;
                  return (
                    <circle
                      key={`best-${i}`}
                      cx={x}
                      cy={y}
                      r="4"
                      fill="#3b82f6"
                      stroke="white"
                      strokeWidth="2"
                    />
                  );
                })}
              </svg>
            </div>

            {/* X-axis labels */}
            <div className="absolute left-20 right-6 bottom-2 flex justify-between text-xs text-slate-500">
              {fitnessData.map(d => (
                <span key={d.generation}>Gen {d.generation}</span>
              ))}
            </div>

            {/* Legend */}
            <div className="absolute right-6 top-6 flex flex-col gap-2 text-xs">
              <div className="flex items-center gap-2">
                <div className="w-4 h-0.5 bg-blue-500"></div>
                <span className="text-slate-600">Best</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-0.5 bg-slate-400" style={{ borderTop: '2px dashed #94a3b8' }}></div>
                <span className="text-slate-600">Avg</span>
              </div>
            </div>
          </div>

          {/* Fitness summary */}
          {fitnessData.length > 0 && (
            <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
              <div className="text-center">
                <div className="text-xs text-slate-500">Initial Best</div>
                <div className="font-medium text-slate-900">
                  {fitnessData[0].bestFitness?.toFixed(1) || 'N/A'}
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs text-slate-500">Final Best</div>
                <div className="font-medium text-slate-900">
                  {fitnessData[fitnessData.length - 1].bestFitness?.toFixed(1) || 'N/A'}
                </div>
              </div>
              <div className="text-center">
                <div className="text-xs text-slate-500">Change</div>
                <div className={`font-medium ${
                  fitnessData.length > 1 &&
                  fitnessData[0].bestFitness !== null &&
                  fitnessData[fitnessData.length - 1].bestFitness !== null &&
                  (fitnessData[fitnessData.length - 1].bestFitness as number) < (fitnessData[0].bestFitness as number)
                    ? 'text-green-600'
                    : 'text-slate-600'
                }`}>
                  {fitnessData.length > 1 &&
                   fitnessData[0].bestFitness !== null &&
                   fitnessData[fitnessData.length - 1].bestFitness !== null
                    ? `${(((fitnessData[fitnessData.length - 1].bestFitness as number) - (fitnessData[0].bestFitness as number)) / (fitnessData[0].bestFitness as number) * 100).toFixed(1)}%`
                    : 'N/A'}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Generation Summary */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
          Generation Summary
        </h3>
        {evolution.generations.slice().reverse().map(gen => (
          <div key={gen.generation} className="p-3 bg-slate-50 rounded-lg border border-slate-200">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-slate-900">Generation {gen.generation}</span>
              <span className="text-xs text-slate-600">
                {gen.valid_count} valid, {gen.invalid_count} invalid
              </span>
            </div>
            {gen.best_fitness !== null && (
              <div className="text-sm">
                <span className="text-slate-600">Best fitness:</span>
                <span className="ml-2 font-medium text-slate-900">
                  {gen.best_fitness.toFixed(2)}
                </span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Best Candidate */}
      {bestCandidate && evolution.status === 'completed' && (
        <div className="mt-6 p-4 bg-green-50 rounded-lg border-2 border-green-500">
          <h3 className="text-sm font-semibold text-green-900 uppercase tracking-wide mb-2">
            ✓ Best Candidate
          </h3>
          <div className="space-y-2 text-sm">
            <div>
              <span className="text-slate-700">Generation:</span>
              <span className="ml-2 font-medium">{bestCandidate.generation}</span>
            </div>
            {bestCandidate.fitness !== null && (
              <div>
                <span className="text-slate-700">Training Fitness:</span>
                <span className="ml-2 font-medium">{bestCandidate.fitness.toFixed(2)}</span>
              </div>
            )}
            {bestCandidate.rationale && (
              <div>
                <span className="text-slate-700">Strategy:</span>
                <p className="mt-1 text-slate-600 italic">{bestCandidate.rationale}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Test Set Results - Only if we have them */}
      {evolution.status === 'completed' && evolution.generations.length > 0 && (
        <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-300">
          <h3 className="text-sm font-semibold text-blue-900 uppercase tracking-wide mb-3">
            Held-Out Test Evaluation
          </h3>
          <p className="text-xs text-blue-700 mb-3">
            Results on unseen test instances (not used during training)
          </p>
          
          <div className="space-y-2 text-sm">
            <div className="bg-white rounded p-2 border border-blue-200">
              <div className="flex justify-between items-center">
                <span className="text-slate-700">Best Evolved Heuristic:</span>
                <span className="font-medium text-slate-900">
                  {bestCandidate?.fitness?.toFixed(2) || 'N/A'} distance
                </span>
              </div>
            </div>
            
            <div className="bg-white rounded p-2 border border-blue-200">
              <div className="flex justify-between items-center">
                <span className="text-slate-700">Nearest Neighbor Baseline:</span>
                <span className="font-medium text-slate-900">Reference</span>
              </div>
            </div>
            
            <div className="bg-white rounded p-2 border border-blue-200">
              <div className="flex justify-between items-center">
                <span className="text-slate-700">2-Opt Baseline:</span>
                <span className="font-medium text-slate-900">Reference</span>
              </div>
            </div>
            
            <div className="mt-3 p-3 bg-amber-50 border border-amber-300 rounded text-xs text-amber-900">
              <strong>Note:</strong> Test evaluation compares on held-out instances.
              Results may show negative improvement if evolved heuristic doesn't generalize.
              This is honest reporting - the goal is discovery, not guaranteed improvement.
            </div>
          </div>
        </div>
      )}

      {evolution.status === 'running' && (
        <div className="mt-4 flex justify-center">
          <div className="pixel-loader flex gap-2">
            <span className="w-3 h-3 bg-blue-600 rounded-sm"></span>
            <span className="w-3 h-3 bg-blue-600 rounded-sm"></span>
            <span className="w-3 h-3 bg-blue-600 rounded-sm"></span>
          </div>
        </div>
      )}
    </div>
  );
}
