"""Data models for evolution tracking and persistence."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class CandidateRecord(BaseModel):
    """Record of a single candidate in a generation."""
    
    candidate_id: str
    generation: int
    source_code: str
    is_valid: bool
    
    # Evaluation results (None if invalid)
    fitness_score: Optional[float] = None
    avg_route_distance: Optional[float] = None
    evaluation_time: Optional[float] = None
    
    # Error info (if invalid)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GenerationRecord(BaseModel):
    """Record of a complete generation."""
    
    generation_number: int
    candidates: List[CandidateRecord]
    
    # Best candidate in this generation
    best_candidate_id: Optional[str] = None
    best_fitness: Optional[float] = None
    
    # Best candidate so far (across all generations up to this point)
    best_so_far_id: Optional[str] = None
    best_so_far_fitness: Optional[float] = None
    
    # Statistics
    num_valid: int
    num_invalid: int
    avg_fitness: Optional[float] = None  # Average of valid candidates
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BaselineComparison(BaseModel):
    """Comparison with baseline algorithms."""
    
    algorithm: str  # "nearest_neighbor" or "two_opt"
    avg_route_distance: float
    evaluation_time: float


class TestSetEvaluation(BaseModel):
    """Evaluation results on held-out test set."""
    
    candidate_id: str
    test_instances_count: int
    
    # Best evolved candidate results
    evolved_avg_distance: float
    evolved_evaluation_time: float
    
    # Baseline comparisons
    baselines: List[BaselineComparison]
    
    # Improvement metrics (can be negative!)
    improvement_vs_nn_percent: float
    improvement_vs_2opt_percent: float
    
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EvolutionRun(BaseModel):
    """Complete evolution run with all tracking data."""
    
    # Identification
    run_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    
    # Configuration
    config: Dict[str, Any]  # Serialized EvolutionConfig
    
    # Random seeds used
    training_seed: int
    test_seed: int
    
    # Generation history
    generations: List[GenerationRecord] = Field(default_factory=list)
    
    # Final results
    best_candidate_id: Optional[str] = None
    best_candidate_code: Optional[str] = None
    best_training_fitness: Optional[float] = None
    
    # Held-out test evaluation
    test_evaluation: Optional[TestSetEvaluation] = None
    
    # Error tracking
    failures: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Status
    status: str = "running"  # "running", "completed", "failed"
    error_message: Optional[str] = None
    
    def mark_completed(self):
        """Mark run as completed."""
        self.status = "completed"
        self.completed_at = datetime.now(timezone.utc)
    
    def mark_failed(self, error: str):
        """Mark run as failed."""
        self.status = "failed"
        self.error_message = error
        self.completed_at = datetime.now(timezone.utc)
    
    def add_generation(self, generation: GenerationRecord):
        """Add a generation record."""
        self.generations.append(generation)
    
    def add_failure(self, failure_info: Dict[str, Any]):
        """Record a failure without crashing the run."""
        self.failures.append(failure_info)
    
    def get_convergence_history(self) -> List[float]:
        """Get best-so-far fitness across generations for plotting."""
        return [
            gen.best_so_far_fitness 
            for gen in self.generations 
            if gen.best_so_far_fitness is not None
        ]
    
    def get_generation_summary(self) -> Dict[str, Any]:
        """Get summary statistics across all generations."""
        if not self.generations:
            return {}
        
        total_candidates = sum(len(g.candidates) for g in self.generations)
        total_valid = sum(g.num_valid for g in self.generations)
        total_invalid = sum(g.num_invalid for g in self.generations)
        
        return {
            "total_generations": len(self.generations),
            "total_candidates": total_candidates,
            "total_valid": total_valid,
            "total_invalid": total_invalid,
            "validity_rate": total_valid / total_candidates if total_candidates > 0 else 0,
            "final_best_fitness": self.best_training_fitness,
        }
