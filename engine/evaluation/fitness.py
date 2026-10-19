"""
Fitness scoring for evolutionary candidate selection.

Fitness functions must balance route quality (distance) with
validity (success rate). Failed candidates cannot gain unfair
advantage by failing on difficult instances.
"""

from typing import Dict, List, Optional
from .models import BenchmarkResult


class FitnessFunction:
    """
    Configurable fitness function for ranking candidates.
    
    The fitness function:
    1. Prioritizes route distance (lower is better)
    2. Penalizes failed evaluations
    3. Ensures failed candidates score worse than successful ones
    4. Provides deterministic scoring
    
    Fitness Direction: LOWER fitness = BETTER candidate
    
    This matches the scoring convention used throughout RouteIQ
    (lower scores indicate better/more preferred options).
    
    Example:
        >>> fitness_fn = FitnessFunction()
        >>> 
        >>> # Successful candidate with good distance
        >>> good_result = BenchmarkResult(
        ...     candidate_id="good",
        ...     mean_distance=100.0,
        ...     success_rate=1.0,
        ...     ...
        ... )
        >>> fitness_fn.calculate(good_result)  # Low fitness (good)
        100.0
        >>> 
        >>> # Successful candidate with poor distance
        >>> poor_result = BenchmarkResult(
        ...     candidate_id="poor",
        ...     mean_distance=200.0,
        ...     success_rate=1.0,
        ...     ...
        ... )
        >>> fitness_fn.calculate(poor_result)  # High fitness (bad)
        200.0
        >>> 
        >>> # Partially failed candidate
        >>> failed_result = BenchmarkResult(
        ...     candidate_id="failed",
        ...     mean_distance=50.0,  # Very good distance
        ...     success_rate=0.5,    # But only 50% success
        ...     ...
        ... )
        >>> fitness_fn.calculate(failed_result)  # Penalized fitness
        inf  # Worse than any successful candidate
    """
    
    def __init__(
        self,
        failure_penalty: float = float('inf'),
        success_rate_threshold: float = 1.0
    ):
        """
        Initialize fitness function.
        
        Args:
            failure_penalty: Penalty for failed evaluations (default: inf)
            success_rate_threshold: Minimum success rate to avoid penalty (default: 1.0)
                                   Set to 1.0 to require perfect success
                                   Set lower (e.g., 0.8) to tolerate some failures
        """
        self.failure_penalty = failure_penalty
        self.success_rate_threshold = success_rate_threshold
    
    def calculate(self, result: BenchmarkResult) -> float:
        """
        Calculate fitness score for a benchmark result.
        
        Fitness = mean_distance (if success_rate >= threshold)
                  else failure_penalty
        
        Args:
            result: Benchmark result to score
            
        Returns:
            Fitness score (lower is better)
        """
        # Check success rate
        if result.success_rate < self.success_rate_threshold:
            # Failed too many evaluations - apply penalty
            return self.failure_penalty
        
        # Check if we have valid distance
        if result.mean_distance is None:
            # No successful evaluations
            return self.failure_penalty
        
        # Successful candidate - use mean distance as fitness
        return result.mean_distance
    
    def calculate_batch(
        self,
        results: List[BenchmarkResult]
    ) -> Dict[str, float]:
        """
        Calculate fitness for multiple results.
        
        Args:
            results: List of benchmark results
            
        Returns:
            Dictionary mapping candidate_id to fitness score
        """
        return {
            result.candidate_id: self.calculate(result)
            for result in results
        }
    
    def __repr__(self) -> str:
        return (
            f"FitnessFunction(penalty={self.failure_penalty}, "
            f"threshold={self.success_rate_threshold})"
        )


class WeightedFitnessFunction(FitnessFunction):
    """
    Alternative fitness function with weighted penalties.
    
    Instead of infinite penalty for failures, applies graduated penalties
    based on success rate. Still ensures failed candidates score worse
    than successful ones with comparable distances.
    
    Fitness = mean_distance * (2 - success_rate)
    
    This gives:
    - 100% success: multiplier = 1.0 (no penalty)
    - 50% success: multiplier = 1.5 (50% penalty)
    - 0% success: multiplier = 2.0 (100% penalty)
    
    Example:
        >>> fitness_fn = WeightedFitnessFunction()
        >>> 
        >>> # Perfect candidate
        >>> perfect = BenchmarkResult(mean_distance=100, success_rate=1.0, ...)
        >>> fitness_fn.calculate(perfect)
        100.0
        >>> 
        >>> # Partial failures
        >>> partial = BenchmarkResult(mean_distance=100, success_rate=0.5, ...)
        >>> fitness_fn.calculate(partial)
        150.0  # 50% penalty
    """
    
    def __init__(self):
        """Initialize weighted fitness function."""
        # Don't use parent's failure penalty
        self.success_rate_threshold = 0.0  # Allow any success rate
    
    def calculate(self, result: BenchmarkResult) -> float:
        """
        Calculate weighted fitness score.
        
        Args:
            result: Benchmark result to score
            
        Returns:
            Fitness score (lower is better)
        """
        if result.mean_distance is None or result.successful_evaluations == 0:
            # No successful evaluations - use infinite penalty
            return float('inf')
        
        # Apply weighted penalty based on success rate
        # multiplier ranges from 1.0 (perfect) to 2.0 (0% success)
        multiplier = 2.0 - result.success_rate
        
        return result.mean_distance * multiplier
    
    def __repr__(self) -> str:
        return "WeightedFitnessFunction()"


def create_fitness_function(
    strategy: str = "strict",
    **kwargs
) -> FitnessFunction:
    """
    Factory function to create fitness functions.
    
    Args:
        strategy: Fitness strategy:
                 - "strict": Requires 100% success (default)
                 - "weighted": Graduated penalties for partial failures
        **kwargs: Additional arguments for fitness function
        
    Returns:
        FitnessFunction instance
        
    Example:
        >>> # Strict fitness (default)
        >>> fitness = create_fitness_function("strict")
        >>> 
        >>> # Weighted fitness
        >>> fitness = create_fitness_function("weighted")
        >>> 
        >>> # Custom threshold
        >>> fitness = create_fitness_function("strict", success_rate_threshold=0.8)
    """
    if strategy == "strict":
        return FitnessFunction(**kwargs)
    elif strategy == "weighted":
        return WeightedFitnessFunction()
    else:
        raise ValueError(
            f"Unknown fitness strategy '{strategy}'. "
            f"Valid options: 'strict', 'weighted'"
        )
