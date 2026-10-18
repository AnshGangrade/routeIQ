"""
Adapter to integrate validated candidates with the existing harness.

This module bridges candidate heuristics with the RouteHarness interface.
"""

from typing import Callable
from .models import CandidateHeuristic
from .validator import HeuristicValidator
from .executor import HeuristicExecutor
from engine.heuristics import HeuristicContext, HeuristicResult


class CandidateAdapter:
    """
    Adapts a CandidateHeuristic to work with RouteHarness.
    
    This class validates and wraps a candidate heuristic to create
    a callable that matches the ScoringHeuristic protocol.
    
    Example:
        >>> candidate = CandidateHeuristic(
        ...     source_code="def score_candidates(ctx): ...",
        ...     function_name="score_candidates"
        ... )
        >>> adapter = CandidateAdapter(candidate)
        >>> 
        >>> # Validate
        >>> validation = adapter.validate()
        >>> if not validation.is_valid:
        ...     print(f"Validation failed: {validation.errors}")
        >>> 
        >>> # Use with harness
        >>> harness = RouteHarness()
        >>> result = harness.build_route(
        ...     heuristic=adapter.create_callable(),
        ...     distance_matrix=dist_matrix,
        ...     n_stops=10
        ... )
    """
    
    def __init__(
        self,
        candidate: CandidateHeuristic,
        validator: HeuristicValidator = None,
        executor: HeuristicExecutor = None
    ):
        """
        Initialize the adapter.
        
        Args:
            candidate: Candidate heuristic to adapt
            validator: Validator instance (creates default if None)
            executor: Executor instance (creates default if None)
        """
        self.candidate = candidate
        self.validator = validator or HeuristicValidator()
        self.executor = executor or HeuristicExecutor(timeout=5.0)
        self._validated = False
    
    def validate(self):
        """
        Validate the candidate heuristic.
        
        Returns:
            ValidationResult
        """
        result = self.validator.validate(self.candidate)
        self._validated = result.is_valid
        return result
    
    def create_callable(self, skip_validation: bool = False) -> Callable[[HeuristicContext], HeuristicResult]:
        """
        Create a callable that implements the ScoringHeuristic protocol.
        
        Args:
            skip_validation: Skip validation check (dangerous, for testing only)
            
        Returns:
            Callable that accepts HeuristicContext and returns HeuristicResult
            
        Raises:
            ValueError: If candidate has not been validated
        """
        if not skip_validation and not self._validated:
            raise ValueError(
                "Candidate must be validated before creating callable. "
                "Call validate() first."
            )
        
        def scoring_function(context: HeuristicContext) -> HeuristicResult:
            """Generated scoring function for candidate heuristic."""
            return self.executor.execute_to_heuristic_result(self.candidate, context)
        
        return scoring_function


def create_scoring_function(
    source_code: str,
    function_name: str = "score_candidates",
    timeout: float = 5.0,
    validate_first: bool = True
) -> Callable[[HeuristicContext], HeuristicResult]:
    """
    Convenience function to create a scoring function from source code.
    
    Args:
        source_code: Python source code
        function_name: Name of the entry point function
        timeout: Execution timeout in seconds
        validate_first: Whether to validate before creating callable
        
    Returns:
        Callable scoring function
        
    Raises:
        ValueError: If validation fails
        
    Example:
        >>> code = '''
        ... def score_candidates(context):
        ...     scores = {}
        ...     for stop in context.candidate_stops:
        ...         scores[stop] = context.distance_matrix[context.current_location, stop]
        ...     return {"scores": scores}
        ... '''
        >>> scorer = create_scoring_function(code)
        >>> # Use with harness
        >>> result = harness.build_route(scorer, dist_matrix, n_stops=10)
    """
    candidate = CandidateHeuristic(
        source_code=source_code,
        function_name=function_name
    )
    
    validator = HeuristicValidator()
    executor = HeuristicExecutor(timeout=timeout)
    adapter = CandidateAdapter(candidate, validator, executor)
    
    if validate_first:
        validation = adapter.validate()
        if not validation.is_valid:
            error_msg = "; ".join(validation.errors)
            raise ValueError(f"Validation failed: {error_msg}")
    
    return adapter.create_callable(skip_validation=not validate_first)
