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
  workload?: Workload;
}

export interface Workload { policy: 'balanced_stop_count'; minimum_stops: number[]; maximum_stops: number[]; }

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
  problem_fingerprint?: string | null;
  matrix_fingerprint?: string | null;
  distance_units?: string | null;
  workload?: Workload | null;
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
  run_id?: string;
  preview?: boolean;
}

export interface DriverRouteResponse {
  driver_id: number;
  route: number[];
  distance: number;
  duration?: number | null;
  geometry?: number[][] | null;  // [[lat, lon], ...]
  geometry_error?: string | null;  // Error message if geometry fetch failed
}

export interface RoutingResultResponse {
  instance_id: string;
  method: string;
  drivers: DriverRouteResponse[];
  total_distance: number;
  longest_route_distance: number;
  computation_time: number;
  optimization?: OptimizationSelection | null;
  run_id?: string | null;
  problem_fingerprint?: string | null;
  matrix_fingerprint?: string | null;
  distance_units?: string | null;
  feasible?: boolean | null;
  execution?: Execution | null;
}

export interface OptimizationSelection {
  nearest_neighbor_distance: number | null;
  two_opt_distance: number | null;
  best_baseline_distance: number;
  raw_evolved_distance: number | null;
  refined_evolved_distance: number | null;
  selected_source: string;
  baseline_retained: boolean;
  improvement_percent: number;
  errors: Record<string, string>;
}

// Evolution Models
export interface StartEvolutionRequest {
  num_stops: number;
  num_instances: number;
  num_generations: number;
  candidates_per_generation: number;
  elites_kept: number;
  seed?: number;
  mode: 'mock' | 'live';
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
  status: 'pending' | 'running' | 'cancelling' | 'cancelled' | 'completed' | 'failed';
  current_generation: number;
  total_generations: number;
  generations: GenerationResult[];
  best_heuristic_id: string | null;
  error: string | null;
  stage?: string;
  candidates_done?: number;
  candidates_per_generation?: number;
  test_evaluation?: HeldOutEvaluation | null;
}

export interface HeldOutEvaluation {
  candidate_id: string;
  test_instances_count: number;
  evolved_avg_distance: number;
  baselines: Array<{ algorithm: string; avg_route_distance: number }>;
  improvement_vs_nn_percent: number;
  improvement_vs_2opt_percent: number;
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
  training_fitness: number | null;
  test_evaluation: HeldOutEvaluation | null;
}

// Comparison Models
export interface MethodComparison {
  server_verified?: boolean;
  method: string;
  total_distance: number;
  longest_route_distance: number;
  computation_time: number;
  improvement_vs_nn: number | null;
  optimization?: OptimizationSelection | null;
  problem_fingerprint?: string | null;
  matrix_fingerprint?: string | null;
  distance_units?: string | null;
  feasible?: boolean | null;
  drivers?: DriverRouteResponse[];
  execution?: Execution | null;
}

export interface ComparisonResponse {
  instance_id: string;
  num_stops: number;
  num_drivers: number;
  comparisons: MethodComparison[];
  problem_fingerprint?: string | null;
  matrix_fingerprint?: string | null;
}

export interface Execution {
  independently_validated?: boolean;
  schema_version?: string; route_validity?: string; search_status?: string;
  schedule_completed?: boolean; neighborhoods_truncated?: number;
  controller?: AdaptiveEvidence | null;
  status: string; termination: string; initial_distance?: number; final_distance?: number;
  improvement_percent?: number; initial_definition?: string; operations: number | null;
  operation_limit?: number; search_seed?: number; budget_exhausted: boolean;
  operator_calls?: number; accepted_moves?: number; ils_iterations?: number; selected_source?: string;
  strategy_job_id?: string | null; strategy_id?: string | null; strategy_fingerprint?: string | null;
  errors?: string[]; work_by_category?: Record<string, number>;
  constructors?: Array<{ method: string; status: string; distance: number | null }>;
  raw_events?: Array<{ stage: string; method: string; status: string; raw_distance: number | null; retained_distance: number; accepted: boolean }>;
}
export interface AdaptiveEvidence {
  problem?:{distance_units:string};
  mode: string; model: string; calls: number; reserved_tokens: number; reported_tokens: number;
  usage_known: boolean; model_seconds: number;
  decisions: Array<{stage:string;source:string;accepted:boolean;request:{error?:string|null};
    proposal?:{rationale?:string;action?:string;config?:Record<string,unknown>}|null;
    execution?:{status:string;reason?:string};
    telemetry?:{best_distance:number;improvement_since_checkpoint:number;stagnated:boolean;operations:number;remaining_operations:number;
      operator_statistics:Record<string,{attempts:number;accepted_improvements:number;rejected_moves:number;operations:number;distance_reduction:number}>}}>
}
export type HybridMethod = 'portfolio' | 'vnd' | 'vnd_ils' | 'strategy' | 'adaptive';
export interface OptimizeRequest {
  instance_id: string; method: HybridMethod; operations?: number; seconds?: number; search_seed: number;
  strategy_job_id?: string; strategy_id?: string;
  adaptive?: {provider:StartStrategyRequest['provider'];experience_job_ids:string[]};
}
export interface OptimizationJob {
  controller?: AdaptiveEvidence | null;
  job_id: string; instance_id: string; method: HybridMethod; problem_fingerprint: string; matrix_fingerprint: string;
  status: 'pending' | 'running' | 'cancelling' | 'cancelled' | 'completed' | 'incomplete' | 'failed';
  stage: string; termination?: string; error?: string | null; result?: RoutingResultResponse | null;
  execution?: Record<string, unknown>; published?: boolean;
}
export interface StrategyFitness {
  eligible: boolean; mean_distance: number | null; completed: number; incomplete: number; failed: number;
  cases: number; expected_cases: number; operations: number; seconds: number;
  missing_cases?: number; policy?: string;
}
export interface StrategyRecord {
  strategy_id: string; parents: string[]; generation: number; configuration_fingerprint: string;
  config: Record<string, unknown>; rationale: string; creation_method: 'seed' | 'llm' | 'mutation' | 'crossover' | 'random';
  fitness: StrategyFitness;
  evaluation_history?: Array<{rows:Array<{feasible:boolean;status:string;case_id:string;independently_validated?:boolean;termination?:string}>}>;
}
export interface StrategyExperiment {
  seed_comparison?: {verified:boolean;winner_id:string;seed_id:string;winner_mean:number;seed_mean:number;difference:number;percentage:number|null;cases:number;distance_units:string}|null;
  proposal_events?: Array<{source:string;outcome:string;strategy_id?:string}>;
  job_id?: string; experiment_id?: string; status: string; termination?: string | null;
  generation?: number; best_id?: string | null; population?: string[]; records?: Record<string, StrategyRecord>;
  history?: Array<{ generation: number; best_so_far: number | null; unique_configurations: number; behavioral_diversity: number; population: string[] }>;
  actual_operations?: number; reserved_evaluations?: number; llm_calls?: number; llm_tokens?: number | null;
  elapsed_seconds?: number; proposals_by_source?: Record<string, number>; rejections?: Record<string, number>;
  provider_usage?: Array<{ calls: number; seconds: number; tokens: number | null; error: string | null; mode: string }>;
  manifest?: { arm: string; config: { generations: number; population_size: number; case_ids: string[]; proposal_policy?:string }; provider_mode: string; software?: unknown; panel?: unknown };
}
export interface StartStrategyRequest {
  workflow?: 'research' | 'ai_product';
  arm: 'llm' | 'random' | 'hand'; mode: 'offline' | 'ollama';
  config: { case_ids: string[]; seed: number; search_seed: number; population_size: number; generations: number;
    elites: number; max_evaluations: number; operations_per_evaluation: number; seconds_per_evaluation: number;
    max_total_operations: number; max_seconds: number; max_proposals: number; max_llm_calls: number };
  provider: { model: string; temperature: number; timeout: number; retries: number; max_tokens: number };
}
