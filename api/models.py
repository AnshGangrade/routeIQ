"""
Pydantic models for API request and response validation.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from engine.evolution.models import TestSetEvaluation
from engine.routing.problem import WorkloadConstraints


# ============================================================================
# Instance Models
# ============================================================================

class GenerateInstanceRequest(BaseModel):
    """Request to generate a synthetic routing instance."""
    num_stops: int = Field(..., ge=5, le=200, description="Number of delivery stops")
    num_drivers: int = Field(..., ge=1, le=20, description="Number of drivers")
    seed: Optional[int] = Field(None, ge=0, le=4294960000, description="Random seed for reproducibility")
    layout: str = Field("uniform", description="Layout type: 'uniform' or 'clustered'")
    mode: str = Field("synthetic", description="Mode: 'synthetic' or 'road'")
    # Road mode parameters (only used if mode='road')
    depot_coords: Optional[List[float]] = Field(None, description="[longitude, latitude] for depot")
    stop_coords: Optional[List[List[float]]] = Field(None, max_length=200, description="List of [lon, lat] for each stop")
    workload: Optional[WorkloadConstraints] = None

    @model_validator(mode="after")
    def valid_layout(self):
        if self.layout not in ("uniform", "clustered"):
            raise ValueError("Layout must be uniform or clustered")
        if self.workload is not None:
            lower, remainder = divmod(self.num_stops, self.num_drivers)
            upper = lower + bool(remainder)
            lo, hi = self.workload.minimum_stops, self.workload.maximum_stops
            if (len(lo) != self.num_drivers or len(hi) != self.num_drivers
                    or any(not lower <= a <= b <= upper for a, b in zip(lo, hi))
                    or sum(lo) > self.num_stops or sum(hi) < self.num_stops):
                raise ValueError("Workload must be feasible within balanced stop-count bounds")
        return self


class StopResponse(BaseModel):
    """A delivery stop in the API response."""
    stop_id: int
    x: float
    y: float
    assigned_driver: Optional[int] = None
    visit_sequence: Optional[int] = None
    distance_from_previous: Optional[float] = None


class DriverResponse(BaseModel):
    """A driver in the API response."""
    driver_id: int
    name: str
    color: str
    assigned_stops: List[int]


class InstanceResponse(BaseModel):
    """Full instance with depot, stops, and drivers."""
    instance_id: str
    seed: int
    num_stops: int
    num_drivers: int
    layout: str
    mode: str  # 'synthetic' or 'road'
    depot: Dict[str, float]  # {"x": float, "y": float} or {"lon": float, "lat": float}
    stops: List[StopResponse]
    drivers: List[DriverResponse]
    road_routing_info: Optional[Dict[str, Any]] = None  # metadata if road mode
    problem_fingerprint: Optional[str] = None
    matrix_fingerprint: Optional[str] = None
    distance_units: Optional[str] = None
    workload: Optional[WorkloadConstraints] = None


# ============================================================================
# Routing Models
# ============================================================================

class SolveRoutingRequest(BaseModel):
    """Request to solve routing for an instance."""
    instance_id: str
    method: str = Field(..., description="Method: 'nearest_neighbor', '2opt', or 'evolved'")
    heuristic_code: Optional[str] = Field(None, max_length=50000, description="Heuristic code for 'evolved' method")
    run_id: Optional[str] = Field(None, description="Completed evolution run whose winner should be applied")
    preview: bool = Field(False, description="Measure a winner without replacing the applied route")


class DriverRouteResponse(BaseModel):
    """Route for a single driver."""
    driver_id: int
    route: List[int]  # Sequence of stop IDs
    distance: float
    duration: Optional[float] = None  # Travel duration in seconds (if available)
    geometry: Optional[List[List[float]]] = None  # [[lat, lon], ...] route geometry
    geometry_error: Optional[str] = None  # Error message if geometry fetch failed


class OptimizationSelection(BaseModel):
    """Current-plan measurements, never training or held-out fitness."""
    nearest_neighbor_distance: Optional[float] = None
    two_opt_distance: Optional[float] = None
    best_baseline_distance: float
    raw_evolved_distance: Optional[float] = None
    refined_evolved_distance: Optional[float] = None
    selected_source: str
    baseline_retained: bool
    improvement_percent: float
    errors: Dict[str, str] = Field(default_factory=dict)


class RoutingResultResponse(BaseModel):
    """Result of routing operation."""
    instance_id: str
    method: str
    drivers: List[DriverRouteResponse]
    total_distance: float
    longest_route_distance: float
    computation_time: float
    optimization: Optional[OptimizationSelection] = None
    run_id: Optional[str] = None
    problem_fingerprint: Optional[str] = None
    matrix_fingerprint: Optional[str] = None
    distance_units: Optional[str] = None
    feasible: Optional[bool] = None
    execution: Optional[Dict[str, Any]] = None


# ============================================================================
# Evolution Models
# ============================================================================

class StartEvolutionRequest(BaseModel):
    """Request to start an evolution run."""
    num_stops: int = Field(30, ge=10, le=100, description="Stops per training instance")
    num_instances: int = Field(10, ge=3, le=50, description="Number of training instances")
    num_generations: int = Field(6, ge=2, le=20, description="Number of generations")
    candidates_per_generation: int = Field(4, ge=2, le=10, description="Candidates per generation")
    elites_kept: int = Field(2, ge=1, le=10, description="Number of elites to keep")
    seed: Optional[int] = Field(None, ge=0, le=4294960000, description="Random seed for instance generation")
    mode: str = Field("mock", description="Mode: 'mock', 'replay', or 'live'")
    llm_model: Optional[str] = Field(None, min_length=1, max_length=200, description="LLM model name (for live mode)")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=1.0, description="LLM temperature")

    @model_validator(mode="after")
    def work_budget(self):
        if self.num_generations * self.candidates_per_generation * self.num_instances * self.num_stops > 100000:
            raise ValueError("Evolution exceeds local work budget (100000 candidate-stop evaluations)")
        return self


class HeuristicInfo(BaseModel):
    """Information about a single heuristic."""
    heuristic_id: str
    generation: int
    parent_id: Optional[str]
    code: str
    rationale: str
    is_valid: bool
    rejection_reason: Optional[str]
    fitness: Optional[float]


class GenerationResult(BaseModel):
    """Results for a single generation."""
    generation: int
    candidates: List[HeuristicInfo]
    best_fitness: Optional[float]
    valid_count: int
    invalid_count: int


class EvolutionProgressResponse(BaseModel):
    """Progress of an evolution run."""
    run_id: str
    status: str  # "running", "completed", "failed"
    current_generation: int
    total_generations: int
    generations: List[GenerationResult]
    best_heuristic_id: Optional[str]
    error: Optional[str]
    stage: str = "pending"
    candidates_done: int = 0
    candidates_per_generation: int = 0
    test_evaluation: Optional[TestSetEvaluation] = None


class EvolutionRunResponse(BaseModel):
    """Response when starting an evolution run."""
    run_id: str
    status: str
    message: str


class BestHeuristicResponse(BaseModel):
    """The best heuristic from an evolution run."""
    run_id: str
    heuristic: HeuristicInfo
    validation_fitness: Optional[float]
    test_results: Optional[Dict[str, float]]
    training_fitness: Optional[float] = None
    test_evaluation: Optional[TestSetEvaluation] = None


# ============================================================================
# Results / Comparison Models
# ============================================================================

class MethodComparison(BaseModel):
    """Comparison of routing methods on a single instance."""
    method: str
    total_distance: float
    longest_route_distance: float
    computation_time: float
    improvement_vs_nn: Optional[float]
    optimization: Optional[OptimizationSelection] = None
    problem_fingerprint: Optional[str] = None
    matrix_fingerprint: Optional[str] = None
    distance_units: Optional[str] = None
    feasible: Optional[bool] = None
    drivers: List[DriverRouteResponse] = Field(default_factory=list)
    execution: Optional[Dict[str, Any]] = None


class ComparisonResponse(BaseModel):
    """Comparison table for all methods on an instance."""
    instance_id: str
    num_stops: int
    num_drivers: int
    comparisons: List[MethodComparison]
    problem_fingerprint: Optional[str] = None
    matrix_fingerprint: Optional[str] = None
