import { useState, useEffect } from 'react';
import { ConfigPanel } from './components/ConfigPanel';
import { RouteVisualization } from './components/RouteVisualization';
import { AlgorithmComparison } from './components/AlgorithmComparison';
import { DriverMetrics } from './components/DriverMetrics';
import { EvolutionProgress } from './components/EvolutionProgress';
import { api, ApiError } from './services/api';
import type {
  InstanceResponse,
  RoutingResultResponse,
  EvolutionProgressResponse,
  ComparisonResponse,
} from './types/api';

interface AppState {
  instance: InstanceResponse | null;
  routingResults: Map<string, RoutingResultResponse>;
  evolutionRun: EvolutionProgressResponse | null;
  comparison: ComparisonResponse | null;
  loading: boolean;
  error: string | null;
}

function App() {
  const [state, setState] = useState<AppState>({
    instance: null,
    routingResults: new Map(),
    evolutionRun: null,
    comparison: null,
    loading: false,
    error: null,
  });

  const [selectedMethod, setSelectedMethod] = useState<string>('nearest_neighbor');

  // Get current routing result
  const currentResult = state.instance && selectedMethod
    ? state.routingResults.get(selectedMethod) || null
    : null;

  // Handle instance generation
  const handleGenerateInstance = async (
    numStops: number,
    numDrivers: number,
    layout: 'uniform' | 'clustered',
    seed?: number,
    mode: 'synthetic' | 'road' = 'synthetic',
    depotCoords?: number[],
    stopCoords?: number[][]
  ) => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const requestBody: any = {
        num_stops: numStops,
        num_drivers: numDrivers,
        layout,
        seed,
        mode,
      };

      if (mode === 'road' && depotCoords && stopCoords) {
        requestBody.depot_coords = depotCoords;
        requestBody.stop_coords = stopCoords;
      }

      const instance = await api.createInstance(requestBody);
      setState(prev => ({
        ...prev,
        instance,
        routingResults: new Map(),
        comparison: null,
        loading: false,
      }));
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Failed to generate instance';
      setState(prev => ({ ...prev, error: message, loading: false }));
    }
  };

  // Handle routing
  const handleSolveRouting = async (method: 'nearest_neighbor' | '2opt') => {
    if (!state.instance) return;

    setState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const result = await api.solveRouting({
        instance_id: state.instance.instance_id,
        method,
      });

      setState(prev => {
        const newResults = new Map(prev.routingResults);
        newResults.set(method, result);
        return {
          ...prev,
          routingResults: newResults,
          loading: false,
        };
      });

      setSelectedMethod(method);

      // Update comparison if we have results
      if (state.routingResults.size > 0 || method) {
        loadComparison();
      }
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Failed to solve routing';
      setState(prev => ({ ...prev, error: message, loading: false }));
    }
  };

  // Load comparison
  const loadComparison = async () => {
    if (!state.instance) return;

    try {
      const comparison = await api.getComparison(state.instance.instance_id);
      setState(prev => ({ ...prev, comparison }));
    } catch (error) {
      // Comparison may not exist yet, ignore error
      console.log('Comparison not available yet');
    }
  };

  // Handle evolution start
  const handleStartEvolution = async (
    numStops: number,
    numInstances: number,
    numGenerations: number,
    candidatesPerGen: number,
    elitesKept: number,
    mode: 'mock' | 'live',
    seed?: number
  ) => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    try {
      const response = await api.startEvolution({
        num_stops: numStops,
        num_instances: numInstances,
        num_generations: numGenerations,
        candidates_per_generation: candidatesPerGen,
        elites_kept: elitesKept,
        seed,
        mode,
      });

      // Start polling for progress
      pollEvolutionProgress(response.run_id);
      setState(prev => ({ ...prev, loading: false }));
    } catch (error) {
      const message = error instanceof ApiError ? error.message : 'Failed to start evolution';
      setState(prev => ({ ...prev, error: message, loading: false }));
    }
  };

  // Poll evolution progress
  const pollEvolutionProgress = async (runId: string) => {
    const poll = async () => {
      try {
        const progress = await api.getEvolutionProgress(runId);
        setState(prev => ({ ...prev, evolutionRun: progress }));

        // Continue polling if still running
        if (progress.status === 'running' || progress.status === 'pending') {
          setTimeout(poll, 2000);
        }
      } catch (error) {
        console.error('Failed to poll evolution progress:', error);
      }
    };

    poll();
  };

  // Clear error after 5 seconds
  useEffect(() => {
    if (state.error) {
      const timer = setTimeout(() => {
        setState(prev => ({ ...prev, error: null }));
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [state.error]);

  return (
    <div className="min-h-screen bg-warm-white">
      {/* Header */}
      <header className="bg-navy text-white shadow-lg">
        <div className="container mx-auto px-6 py-4">
          <h1 className="text-3xl font-bold tracking-tight">
            RouteIQ
          </h1>
          <p className="text-sm text-slate-300 mt-1">
            LLM-Guided Evolutionary Heuristic Discovery for Route Optimization
          </p>
        </div>
      </header>

      {/* Error banner */}
      {state.error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 mx-6 mt-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700">{state.error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Main content */}
      <main className="container mx-auto px-6 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column - Configuration */}
          <div className="lg:col-span-1 space-y-6">
            <ConfigPanel
              onGenerateInstance={handleGenerateInstance}
              onSolveRouting={handleSolveRouting}
              onStartEvolution={handleStartEvolution}
              hasInstance={!!state.instance}
              loading={state.loading}
            />

            {state.comparison && (
              <AlgorithmComparison comparison={state.comparison} />
            )}
          </div>

          {/* Middle column - Visualization */}
          <div className="lg:col-span-2 space-y-6">
            <RouteVisualization
              instance={state.instance}
              routingResult={currentResult}
              onMethodSelect={setSelectedMethod}
              selectedMethod={selectedMethod}
              availableMethods={Array.from(state.routingResults.keys())}
            />

            {currentResult && (
              <DriverMetrics result={currentResult} />
            )}

            {state.evolutionRun && (
              <EvolutionProgress evolution={state.evolutionRun} />
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-warm-border mt-12 py-6">
        <div className="container mx-auto px-6 text-center text-sm text-slate-600">
          <p>
            <strong>Note:</strong> All coordinates are synthetic. Distances are Euclidean (straight-line), not road distances.
          </p>
          <p className="mt-2">
            RouteIQ Capstone Project • Data Science & AI • 2026
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
