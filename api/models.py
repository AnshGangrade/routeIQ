"""
Pydantic models for API request and response validation.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ============================================================================
# Instance Models
# ============================================================================

class GenerateInstanceRequest(BaseModel):
    """Request to generate a synthetic routing instance."""
    num_stops: int = Field(..., ge=5, le=200, description="Number of delivery stops")
    num_drivers: int = Field(..., ge=1, le=20, description="Number of drivers")
    seed: Optional[int] = Field(None, description="Random seed for reproducibility")
    layout: str = Field("uniform", description="Layout type: 'uniform' or 'clustered'")
    mode: str = Field("synthetic", description="Mode: 'synthetic' or 'road'")
    # Road mode parameters (only used if mode='road')
    depot_coords: Optional[List[float]] = Field(None, description="[longitude, latitude] for depot")
    stop_coords: Optional[List[List[float]]] = Field(None, description="List of [lon, lat] for each stop")


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


# ============================================================================
# Routing Models
# ============================================================================

class SolveRoutingRequest(BaseModel):
    """Request to solve routing for an instance."""
    instance_id: str
    method: str = Field(..., description="Method: 'nearest_neighbor', '2opt', or 'evolved'")
    heuristic_code: Optional[str] = Field(None, description="Heuristic code for 'evolved' method")


class DriverRouteResponse(BaseModel):
    """Route for a single driver."""
    driver_id: int
    route: List[int]  # Sequence of stop IDs
    distance: float


class RoutingResultResponse(BaseModel):
    """Result of routing operation."""
    instance_id: str
    method: str
    drivers: List[DriverRouteResponse]
    total_distance: float
    longest_route_distance: float
    computation_time: float


# ============================================================================
# Evolution Models
# ============================================================================

class StartEvolutionRequest(BaseModel):
    """Request to start an evolution run."""
    num_stops: int = Field(30, ge=10, le=100, description="Stops per training instance")
    num_instances: int = Field(10, ge=3, le=50, description="Number of training instances")
    num_generations: int = Field(6, ge=2, le=20, description="Number of generations")
    candidates_per_generation: int = Field(4, ge=2, le=10, description="Candidates per generation")
    elites_kept: int = Field(2, ge=1, description="Number of elites to keep")
    seed: Optional[int] = Field(None, description="Random seed for instance generation")
    mode: str = Field("mock", description="Mode: 'mock', 'replay', or 'live'")
    llm_model: Optional[str] = Field(None, description="LLM model name (for live mode)")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="LLM temperature")


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


class ComparisonResponse(BaseModel):
    """Comparison table for all methods on an instance."""
    instance_id: str
    num_stops: int
    num_drivers: int
    comparisons: List[MethodComparison]
