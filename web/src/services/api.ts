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
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(
      errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
      response.status,
      errorData
    );
  }

  return response.json();
}

export const api = {
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

  async getEvolutionProgress(runId: string): Promise<EvolutionProgressResponse> {
    return fetchJSON(`${API_BASE}/evolution/runs/${runId}`);
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
