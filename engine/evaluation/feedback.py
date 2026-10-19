"""
Feedback preparation for LLM iteration.

Creates structured feedback from evaluation results suitable for
use in prompt generation.
"""

from typing import Optional
from .models import BenchmarkResult, ComparisonMetrics, FeedbackData


def prepare_feedback(
    comparison: ComparisonMetrics,
    fitness_score: float
) -> FeedbackData:
    """
    Prepare structured feedback from comparison metrics.
    
    Args:
        comparison: Comparison metrics with baselines
        fitness_score: Computed fitness score
        
    Returns:
        FeedbackData ready for use in prompts
    """
    candidate = comparison.candidate_result
    nn_baseline = comparison.baseline_nn_result
    two_opt_baseline = comparison.baseline_2opt_result
    
    # Build failure summary if applicable
    failure_summary = None
    if candidate.failed_evaluations > 0:
        failure_parts = []
        for status, count in candidate.failure_breakdown.items():
            failure_parts.append(f"- {status.replace('_', ' ').title()}: {count} instances")
        failure_summary = "\n".join(failure_parts)
    
    # Build observations
    observations = _build_observations(comparison)
    
    return FeedbackData(
        candidate_id=candidate.candidate_id,
        algorithm_name=candidate.algorithm_name,
        fitness_score=fitness_score,
        instances_evaluated=candidate.instances_evaluated,
        success_rate=candidate.success_rate,
        mean_distance=candidate.mean_distance,
        median_distance=candidate.median_distance,
        improvement_vs_nn=comparison.improvement_vs_nn,
        improvement_vs_2opt=comparison.improvement_vs_2opt,
        baseline_nn_mean=nn_baseline.mean_distance,
        baseline_2opt_mean=two_opt_baseline.mean_distance,
        failure_summary=failure_summary,
        observations=observations
    )


def _build_observations(comparison: ComparisonMetrics) -> Optional[str]:
    """
    Build factual observations from evaluation results.
    
    Args:
        comparison: Comparison metrics
        
    Returns:
        Observation text or None
    """
    observations = []
    
    candidate = comparison.candidate_result
    
    # Success rate observations
    if candidate.success_rate < 1.0:
        observations.append(
            f"The heuristic failed on {candidate.failed_evaluations} out of "
            f"{candidate.instances_evaluated} instances ({(1 - candidate.success_rate) * 100:.1f}%)."
        )
    
    # Distance variance observations
    if candidate.mean_distance is not None and candidate.median_distance is not None:
        distance_ratio = candidate.median_distance / candidate.mean_distance
        if distance_ratio < 0.9:
            observations.append(
                "The median distance is notably lower than the mean, "
                "suggesting some instances had much longer routes."
            )
        elif distance_ratio > 1.1:
            observations.append(
                "The median distance is notably higher than the mean, "
                "suggesting some instances had much shorter routes."
            )
    
    # Per-instance consistency
    if comparison.per_instance_comparisons:
        successes = [
            c for c in comparison.per_instance_comparisons
            if c.get("candidate_status") == "success"
        ]
        
        if successes:
            improvements_vs_nn = [
                c.get("improvement_vs_nn") 
                for c in successes 
                if c.get("improvement_vs_nn") is not None
            ]
            
            if improvements_vs_nn:
                positive_count = sum(1 for imp in improvements_vs_nn if imp > 0)
                negative_count = sum(1 for imp in improvements_vs_nn if imp < 0)
                
                if positive_count > 0 and negative_count > 0:
                    observations.append(
                        f"Performance varied: better than NN on {positive_count} instances, "
                        f"worse on {negative_count} instances."
                    )
    
    # Baseline comparisons
    if comparison.improvement_vs_nn is not None and comparison.improvement_vs_2opt is not None:
        if comparison.improvement_vs_nn > 0 and comparison.improvement_vs_2opt < 0:
            observations.append(
                "The heuristic beat Nearest Neighbor but not NN+2-Opt, "
                "suggesting the construction is reasonable but lacks local optimization."
            )
        elif comparison.improvement_vs_nn < 0:
            observations.append(
                "The heuristic performed worse than both baselines. "
                "Consider strategies closer to nearest-neighbor or distance-minimization."
            )
    
    return "\n".join(observations) if observations else None


def format_feedback_for_prompt(feedback: FeedbackData) -> str:
    """
    Format feedback as text suitable for LLM prompts.
    
    This is a convenience wrapper around FeedbackData.to_feedback_text().
    
    Args:
        feedback: Structured feedback data
        
    Returns:
        Formatted feedback text
    """
    return feedback.to_feedback_text()


def prepare_feedback_batch(
    comparisons: list[ComparisonMetrics],
    fitness_scores: dict[str, float]
) -> list[FeedbackData]:
    """
    Prepare feedback for multiple candidates.
    
    Args:
        comparisons: List of comparison metrics
        fitness_scores: Dictionary mapping candidate_id to fitness score
        
    Returns:
        List of FeedbackData objects
    """
    return [
        prepare_feedback(
            comparison=comp,
            fitness_score=fitness_scores[comp.candidate_result.candidate_id]
        )
        for comp in comparisons
    ]
