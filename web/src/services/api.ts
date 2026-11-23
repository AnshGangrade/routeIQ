/**
 * API service for RouteIQ backend
 */
import type {
  GenerateInstanceRequest,
  InstanceResponse,
  SolveRoutingRequest,
  RoutingResultResponse,
  StartEvolutionRequest,
  EvolutionRunResponse,
  EvolutionProgressResponse,
  BestHeuristicResponse,
  ComparisonResponse,
  OptimizeRequest, OptimizationJob, StartStrategyRequest, StrategyExperiment,
} from '../types/api';

const API_BASE = '/api';

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: any
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
    ...options,
    signal: options?.signal ?? AbortSignal.timeout(120000),
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  } catch (error) {
    if (options?.signal?.aborted) throw error;
    throw new ApiError('Cannot reach the backend or request timed out. Check the server and retry.', 0);
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(
      Array.isArray(errorData.detail)
        ? errorData.detail.map((item: { msg: string }) => item.msg).join('; ')
        : errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
      response.status,
      errorData
    );
  }

  try { return await response.json(); }
  catch { throw new ApiError('The backend returned an unreadable response. Retry when the server is ready.', response.status); }
}

export const api = {
  async checkStrategyProvider(provider: StartStrategyRequest['provider'], signal?:AbortSignal):Promise<{configured:boolean;reachable:boolean;available:boolean;model:string;message:string}> {
    return fetchJSON(`${API_BASE}/strategy-experiments/provider/check`,{method:'POST',body:JSON.stringify(provider),signal});
  },
  async startOptimization(request: OptimizeRequest): Promise<OptimizationJob> {
    return fetchJSON(`${API_BASE}/optimization/jobs`, { method: 'POST', body: JSON.stringify(request) });
  },
  async optimizationStatus(jobId: string, signal?: AbortSignal): Promise<OptimizationJob> {
    return fetchJSON(`${API_BASE}/optimization/jobs/${encodeURIComponent(jobId)}`, { signal });
  },
  async cancelOptimization(jobId: string): Promise<{ job_id: string; instance_id: string; status: OptimizationJob['status'] }> {
    return fetchJSON(`${API_BASE}/optimization/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
  },
  async startStrategy(request: StartStrategyRequest): Promise<{ job_id: string; status: string }> {
    return fetchJSON(`${API_BASE}/strategy-experiments`, { method: 'POST', body: JSON.stringify(request) });
  },
  async strategyStatus(jobId: string, signal?: AbortSignal): Promise<StrategyExperiment> {
    return fetchJSON(`${API_BASE}/strategy-experiments/${encodeURIComponent(jobId)}`, { signal });
  },
  async strategyExport(jobId: string, signal?: AbortSignal): Promise<StrategyExperiment> {
    return fetchJSON(`${API_BASE}/strategy-experiments/${encodeURIComponent(jobId)}/export`, { signal });
  },
  async cancelStrategy(jobId: string): Promise<{ job_id: string; status: string }> {
    return fetchJSON(`${API_BASE}/strategy-experiments/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' });
  },
  async resumeStrategy(jobId: string): Promise<{ job_id: string; status: string }> {
    return fetchJSON(`${API_BASE}/strategy-experiments/${encodeURIComponent(jobId)}/resume`, { method: 'POST' });
  },
  // Health check
  async healthCheck(): Promise<{ status: string; message: string }> {
    return fetchJSON(`${API_BASE}/health`);
  },

  // Instance management
  async createInstance(request: GenerateInstanceRequest): Promise<InstanceResponse> {
    return fetchJSON(`${API_BASE}/instances`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  async getInstance(instanceId: string): Promise<InstanceResponse> {
    return fetchJSON(`${API_BASE}/instances/${instanceId}`);
  },

  // Routing
  async solveRouting(request: SolveRoutingRequest): Promise<RoutingResultResponse> {
    return fetchJSON(`${API_BASE}/routing/solve`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  // Evolution
  async startEvolution(request: StartEvolutionRequest): Promise<EvolutionRunResponse> {
    return fetchJSON(`${API_BASE}/evolution/runs`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  async getEvolutionProgress(runId: string, signal?: AbortSignal): Promise<EvolutionProgressResponse> {
    return fetchJSON(`${API_BASE}/evolution/runs/${runId}`, { signal });
  },

  async applyWinner(runId: string, instanceId: string): Promise<RoutingResultResponse> {
    return this.solveRouting({ instance_id: instanceId, method: 'evolved', run_id: runId });
  },

  async previewWinner(runId: string, instanceId: string): Promise<RoutingResultResponse> {
    return this.solveRouting({ instance_id: instanceId, method: 'evolved', run_id: runId, preview: true });
  },

  async cancelEvolution(runId: string): Promise<{ run_id: string; status: string }> {
    return fetchJSON(`${API_BASE}/evolution/runs/${runId}/cancel`, { method: 'POST' });
  },

  async getBestHeuristic(runId: string): Promise<BestHeuristicResponse> {
    return fetchJSON(`${API_BASE}/evolution/runs/${runId}/best`);
  },

  // Comparison
  async getComparison(instanceId: string): Promise<ComparisonResponse> {
    return fetchJSON(`${API_BASE}/results/${instanceId}/comparison`);
  },
};

export { ApiError };

export function watchEvolution(
  runId: string,
  onProgress: (progress: EvolutionProgressResponse) => void,
  onError: (message: string) => void,
): () => void {
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const controller = new AbortController();
  const poll = async () => {
    try {
      const progress = await api.getEvolutionProgress(runId, AbortSignal.any([controller.signal, AbortSignal.timeout(15000)]));
      if (stopped) return;
      if (progress.run_id !== runId) throw new Error('Unexpected evolution run response');
      onProgress(progress);
      if (['pending', 'running', 'cancelling'].includes(progress.status)) timer = setTimeout(poll, 2000);
    } catch (error) {
      if (stopped) return;
      onError(error instanceof Error ? error.message : 'Progress unavailable');
      timer = setTimeout(poll, 4000);
    }
  };
  void poll();
  return () => { stopped = true; clearTimeout(timer); controller.abort(); };
}
