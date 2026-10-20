/**
 * TypeScript types matching the backend API models
 */

// Instance Models
export interface GenerateInstanceRequest {
  num_stops: number;
  num_drivers: number;
  seed?: number;
  layout: 'uniform' | 'clustered';
  mode?: 'synthetic' | 'road';
  depot_coords?: number[];
  stop_coords?: number[][];
}

export interface StopResponse {
  stop_id: number;
  x: number;
  y: number;
  assigned_driver: number | null;
  visit_sequence: number | null;
  distance_from_previous: number | null;
}

export interface DriverResponse {
  driver_id: number;
  name: string;
  color: string;
  assigned_stops: number[];
}

export interface InstanceResponse {
  instance_id: string;
  seed: number;
  num_stops: number;
  num_drivers: number;
  layout: string;
  mode: string;
  depot: { x?: number; y?: number; lon?: number; lat?: number };
  stops: StopResponse[];
  drivers: DriverResponse[];
  road_routing_info?: {
    provider: string;
    cache_hit: boolean;
    metadata: Record<string, any>;
  };
}

// Routing Models
export interface SolveRoutingRequest {
  instance_id: string;
  method: 'nearest_neighbor' | '2opt' | 'evolved';
  heuristic_code?: string;
}

export interface DriverRouteResponse {
  driver_id: number;
  route: number[];
  distance: number;
}

export interface RoutingResultResponse {
  instance_id: string;
  method: string;
  drivers: DriverRouteResponse[];
  total_distance: number;
  longest_route_distance: number;
  computation_time: number;
}

// Evolution Models
export interface StartEvolutionRequest {
  num_stops: number;
  num_instances: number;
  num_generations: number;
  candidates_per_generation: number;
  elites_kept: number;
  seed?: number;
  mode: 'mock' | 'replay' | 'live';
  llm_model?: string;
  temperature?: number;
}

export interface HeuristicInfo {
  heuristic_id: string;
  generation: number;
  parent_id: string | null;
  code: string;
  rationale: string;
  is_valid: boolean;
  rejection_reason: string | null;
  fitness: number | null;
}

export interface GenerationResult {
  generation: number;
  candidates: HeuristicInfo[];
  best_fitness: number | null;
  valid_count: number;
  invalid_count: number;
}

export interface EvolutionProgressResponse {
  run_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  current_generation: number;
  total_generations: number;
  generations: GenerationResult[];
  best_heuristic_id: string | null;
  error: string | null;
}

export interface EvolutionRunResponse {
  run_id: string;
  status: string;
  message: string;
}

export interface BestHeuristicResponse {
  run_id: string;
  heuristic: HeuristicInfo;
  validation_fitness: number | null;
  test_results: Record<string, number> | null;
}

// Comparison Models
export interface MethodComparison {
  method: string;
  total_distance: number;
  longest_route_distance: number;
  computation_time: number;
  improvement_vs_nn: number | null;
}

export interface ComparisonResponse {
  instance_id: string;
  num_stops: number;
  num_drivers: number;
  comparisons: MethodComparison[];
}
