"""
Heuristic evaluation, fitness scoring, and candidate selection.

This module provides:
- Benchmark evaluation on synthetic instances
- Fair comparison with baseline algorithms
- Fitness scoring for evolutionary selection
- Candidate ranking and selection
- Structured feedback preparation for LLM iteration

Example Usage:
    >>> from engine.evaluation import (
    ...     HeuristicEvaluator,
    ...     FitnessFunction,
    ...     CandidateSelector,
    ...     prepare_feedback
    ... )
    >>> 
    >>> # Evaluate candidate
    >>> evaluator = HeuristicEvaluator()
    >>> result = evaluator.evaluate_candidate(
    ...     candidate=my_candidate,
    ...     instances=test_instances,
    ...     candidate_id="gen_001"
    ... )
    >>> 
    >>> # Compare with baselines
    >>> comparison = evaluator.compare_with_baselines(
    ...     candidate_result=result,
    ...     instances=test_instances
    ... )
    >>> 
    >>> # Calculate fitness
    >>> fitness_fn = FitnessFunction()
    >>> fitness = fitness_fn.calculate(result)
    >>> 
    >>> # Select best candidates
    >>> selector = CandidateSelector(fitness_function=fitness_fn)
    >>> selection = selector.select_best(all_results, n_select=3)
    >>> 
    >>> # Prepare feedback for next iteration
    >>> feedback = prepare_feedback(comparison, fitness)
    >>> feedback_text = feedback.to_feedback_text()
"""

from .models import (
    EvaluationStatus,
    InstanceEvaluation,
    BenchmarkResult,
    ComparisonMetrics,
    SelectionResult,
    FeedbackData,
)

from .evaluator import HeuristicEvaluator

from .fitness import (
    FitnessFunction,
    WeightedFitnessFunction,
    create_fitness_function,
)

from .selection import (
    CandidateSelector,
    select_elite,
)

from .feedback import (
    prepare_feedback,
    format_feedback_for_prompt,
    prepare_feedback_batch,
)

__all__ = [
    # Models
    "EvaluationStatus",
    "InstanceEvaluation",
    "BenchmarkResult",
    "ComparisonMetrics",
    "SelectionResult",
    "FeedbackData",
    
    # Evaluator
    "HeuristicEvaluator",
    
    # Fitness
    "FitnessFunction",
    "WeightedFitnessFunction",
    "create_fitness_function",
    
    # Selection
    "CandidateSelector",
    "select_elite",
    
    # Feedback
    "prepare_feedback",
    "format_feedback_for_prompt",
    "prepare_feedback_batch",
]
