"""
Data models for heuristic evaluation and benchmarking.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class EvaluationStatus(str, Enum):
    """Status of a single evaluation run."""
    SUCCESS = "success"
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_FAILED = "execution_failed"
    CONSTRUCTION_FAILED = "construction_failed"
    INVALID_ROUTE = "invalid_route"


class InstanceEvaluation(BaseModel):
    """
    Result of evaluating a heuristic on a single instance.
    
    Attributes:
        instance_seed: Seed used to generate the instance
        n_stops: Number of delivery stops in the instance
        status: Evaluation status (success or failure reason)
        route: Constructed route if successful
        distance: Route distance if successful
        execution_time: Time taken to build route (seconds)
        error_message: Detailed error if failed
    """
    instance_seed: int = Field(..., description="Instance generation seed")
    n_stops: int = Field(..., ge=0, description="Number of delivery stops")
    status: EvaluationStatus = Field(..., description="Evaluation outcome")
    route: Optional[List[int]] = Field(None, description="Constructed route")
    distance: Optional[float] = Field(None, ge=0, description="Route distance")
    execution_time: Optional[float] = Field(None, ge=0, description="Execution time (seconds)")
    error_message: Optional[str] = Field(None, description="Error details if failed")
    
    def __repr__(self) -> str:
        if self.status == EvaluationStatus.SUCCESS:
            return f"InstanceEvaluation(seed={self.instance_seed}, distance={self.distance:.2f})"
        return f"InstanceEvaluation(seed={self.instance_seed}, status={self.status.value})"


class BenchmarkResult(BaseModel):
    """
    Complete evaluation of a heuristic across multiple instances.
    
    Aggregates both successful and failed evaluations with detailed metrics.
    
    Attributes:
        candidate_id: Identifier for the evaluated candidate
        algorithm_name: Name/description of the heuristic
        instances_evaluated: Total number of instances attempted
        successful_evaluations: Number of successful route constructions
        failed_evaluations: Number of failed evaluations
        
        total_distance: Sum of distances for successful evaluations
        mean_distance: Mean distance across successful evaluations
        median_distance: Median distance across successful evaluations
        
        success_rate: Fraction of successful evaluations (0.0-1.0)
        total_execution_time: Total time across all evaluations
        
        per_instance_results: Detailed results for each instance
        failure_breakdown: Count of failures by type
    """
    candidate_id: str = Field(..., description="Candidate identifier")
    algorithm_name: str = Field(..., description="Algorithm/heuristic name")
    
    instances_evaluated: int = Field(..., ge=0, description="Total instances evaluated")
    successful_evaluations: int = Field(..., ge=0, description="Successful evaluations")
    failed_evaluations: int = Field(..., ge=0, description="Failed evaluations")
    
    total_distance: Optional[float] = Field(None, ge=0, description="Sum of successful distances")
    mean_distance: Optional[float] = Field(None, ge=0, description="Mean successful distance")
    median_distance: Optional[float] = Field(None, ge=0, description="Median successful distance")
    
    success_rate: float = Field(..., ge=0.0, le=1.0, description="Success rate (0.0-1.0)")
    total_execution_time: float = Field(..., ge=0, description="Total execution time (seconds)")
    
    per_instance_results: List[InstanceEvaluation] = Field(
        default_factory=list,
        description="Individual instance results"
    )
    
    failure_breakdown: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of failures by status"
    )
    
    def __repr__(self) -> str:
        if self.successful_evaluations > 0:
            return (
                f"BenchmarkResult(id='{self.candidate_id}', "
                f"success={self.successful_evaluations}/{self.instances_evaluated}, "
                f"mean_dist={self.mean_distance:.2f})"
            )
        return (
            f"BenchmarkResult(id='{self.candidate_id}', "
            f"success=0/{self.instances_evaluated})"
        )


class ComparisonMetrics(BaseModel):
    """
    Comparison of a candidate heuristic against baseline algorithms.
    
    Attributes:
        candidate_result: Candidate's benchmark result
        baseline_nn_result: Nearest Neighbor baseline result
        baseline_2opt_result: NN + 2-Opt baseline result
        
        improvement_vs_nn: Improvement percentage vs NN (can be negative)
        improvement_vs_2opt: Improvement percentage vs NN+2-Opt (can be negative)
        
        per_instance_comparisons: Detailed per-instance comparisons
    """
    candidate_result: BenchmarkResult = Field(..., description="Candidate benchmark result")
    baseline_nn_result: BenchmarkResult = Field(..., description="Nearest Neighbor baseline")
    baseline_2opt_result: BenchmarkResult = Field(..., description="NN + 2-Opt baseline")
    
    improvement_vs_nn: Optional[float] = Field(None, description="Improvement % vs NN")
    improvement_vs_2opt: Optional[float] = Field(None, description="Improvement % vs NN+2-Opt")
    
    per_instance_comparisons: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Per-instance comparison details"
    )
    
    def __repr__(self) -> str:
        parts = [f"ComparisonMetrics(candidate='{self.candidate_result.candidate_id}'"]
        if self.improvement_vs_nn is not None:
            parts.append(f"vs_nn={self.improvement_vs_nn:+.1f}%")
        if self.improvement_vs_2opt is not None:
            parts.append(f"vs_2opt={self.improvement_vs_2opt:+.1f}%")
        return ", ".join(parts) + ")"


class SelectionResult(BaseModel):
    """
    Result of candidate selection process.
    
    Attributes:
        selected_candidates: List of selected candidate IDs (ordered best to worst)
        fitness_scores: Fitness score for each candidate
        rankings: Rank for each candidate (1 = best)
        selection_reason: Explanation of selection criteria
    """
    selected_candidates: List[str] = Field(..., description="Selected candidate IDs")
    fitness_scores: Dict[str, float] = Field(..., description="Fitness score per candidate")
    rankings: Dict[str, int] = Field(..., description="Rank per candidate (1=best)")
    selection_reason: str = Field(..., description="Selection explanation")
    
    def __repr__(self) -> str:
        n_selected = len(self.selected_candidates)
        if n_selected > 0:
            best_id = self.selected_candidates[0]
            best_fitness = self.fitness_scores[best_id]
            return f"SelectionResult(selected={n_selected}, best='{best_id}', fitness={best_fitness:.2f})"
        return "SelectionResult(selected=0)"


class FeedbackData(BaseModel):
    """
    Structured feedback for LLM iteration.
    
    Attributes:
        candidate_id: Candidate identifier
        algorithm_name: Brief heuristic description
        fitness_score: Computed fitness value
        
        instances_evaluated: Total instances evaluated
        success_rate: Fraction of successful evaluations
        
        mean_distance: Mean distance on successful evaluations
        median_distance: Median distance on successful evaluations
        
        improvement_vs_nn: Improvement percentage vs Nearest Neighbor
        improvement_vs_2opt: Improvement percentage vs NN+2-Opt
        
        baseline_nn_mean: NN baseline mean distance
        baseline_2opt_mean: NN+2-Opt baseline mean distance
        
        failure_summary: Summary of failure types if any
        observations: Additional factual observations
    """
    candidate_id: str = Field(..., description="Candidate identifier")
    algorithm_name: str = Field(..., description="Algorithm name")
    fitness_score: float = Field(..., description="Fitness score")
    
    instances_evaluated: int = Field(..., ge=0, description="Total instances")
    success_rate: float = Field(..., ge=0.0, le=1.0, description="Success rate")
    
    mean_distance: Optional[float] = Field(None, ge=0, description="Mean distance if successful")
    median_distance: Optional[float] = Field(None, ge=0, description="Median distance if successful")
    
    improvement_vs_nn: Optional[float] = Field(None, description="% improvement vs NN")
    improvement_vs_2opt: Optional[float] = Field(None, description="% improvement vs NN+2-Opt")
    
    baseline_nn_mean: Optional[float] = Field(None, ge=0, description="NN baseline mean")
    baseline_2opt_mean: Optional[float] = Field(None, ge=0, description="NN+2-Opt baseline mean")
    
    failure_summary: Optional[str] = Field(None, description="Failure type summary")
    observations: Optional[str] = Field(None, description="Additional observations")
    
    def to_feedback_text(self) -> str:
        """
        Convert to human-readable feedback text for LLM prompts.
        
        Returns:
            Formatted feedback string
        """
        lines = []
        
        # Performance summary
        lines.append(f"Your heuristic '{self.algorithm_name}' achieved:")
        lines.append(f"- Fitness score: {self.fitness_score:.2f}")
        lines.append(f"- Success rate: {self.success_rate * 100:.1f}% ({int(self.success_rate * self.instances_evaluated)}/{self.instances_evaluated} instances)")
        
        if self.mean_distance is not None:
            lines.append(f"- Mean distance: {self.mean_distance:.2f}")
            lines.append(f"- Median distance: {self.median_distance:.2f}")
        
        # Baseline comparisons
        if self.improvement_vs_nn is not None:
            sign = "better" if self.improvement_vs_nn > 0 else "worse"
            lines.append(f"\nComparison with Nearest Neighbor baseline:")
            lines.append(f"- Your heuristic: {self.mean_distance:.2f}")
            lines.append(f"- NN baseline: {self.baseline_nn_mean:.2f}")
            lines.append(f"- Result: {abs(self.improvement_vs_nn):.1f}% {sign}")
        
        if self.improvement_vs_2opt is not None:
            sign = "better" if self.improvement_vs_2opt > 0 else "worse"
            lines.append(f"\nComparison with NN + 2-Opt baseline:")
            lines.append(f"- Your heuristic: {self.mean_distance:.2f}")
            lines.append(f"- NN+2-Opt baseline: {self.baseline_2opt_mean:.2f}")
            lines.append(f"- Result: {abs(self.improvement_vs_2opt):.1f}% {sign}")
        
        # Failures
        if self.failure_summary:
            lines.append(f"\nFailure analysis:")
            lines.append(self.failure_summary)
        
        # Observations
        if self.observations:
            lines.append(f"\nObservations:")
            lines.append(self.observations)
        
        return "\n".join(lines)
    
    def __repr__(self) -> str:
        return (
            f"FeedbackData(id='{self.candidate_id}', "
            f"fitness={self.fitness_score:.2f}, "
            f"success_rate={self.success_rate:.1%})"
        )
