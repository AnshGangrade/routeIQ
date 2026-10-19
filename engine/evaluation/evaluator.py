"""
Heuristic evaluator for benchmark testing.

Evaluates candidate heuristics on synthetic instances and compares
with baseline algorithms.
"""

import time
import numpy as np
from typing import List, Optional, Callable
from collections import Counter

from .models import (
    InstanceEvaluation,
    BenchmarkResult,
    ComparisonMetrics,
    EvaluationStatus
)
from engine.instances import DeliveryInstance, compute_distance_matrix, validate_route
from engine.heuristics import HeuristicContext, RouteHarness
from engine.baselines import nearest_neighbor, nearest_neighbor_with_2opt
from engine.sandbox import CandidateHeuristic, HeuristicValidator, create_scoring_function


class HeuristicEvaluator:
    """
    Evaluate candidate heuristics on benchmark instances.
    
    The evaluator:
    1. Validates candidates through the sandbox pipeline
    2. Builds routes using the trusted harness
    3. Validates route correctness (all stops visited, returns to depot)
    4. Calculates true distance using shared distance function
    5. Compares with baseline algorithms on identical instances
    6. Aggregates metrics across multiple instances
    
    Example:
        >>> evaluator = HeuristicEvaluator()
        >>> instances = [instance1, instance2, instance3]
        >>> 
        >>> # Evaluate candidate
        >>> result = evaluator.evaluate_candidate(
        ...     candidate=my_candidate,
        ...     instances=instances,
        ...     candidate_id="gen_001"
        ... )
        >>> print(f"Success rate: {result.success_rate:.1%}")
        >>> print(f"Mean distance: {result.mean_distance:.2f}")
        >>> 
        >>> # Compare with baselines
        >>> comparison = evaluator.compare_with_baselines(
        ...     candidate_result=result,
        ...     instances=instances
        ... )
        >>> print(f"Improvement vs NN: {comparison.improvement_vs_nn:+.1f}%")
    """
    
    def __init__(
        self,
        validator: Optional[HeuristicValidator] = None,
        timeout: float = 5.0
    ):
        """
        Initialize the evaluator.
        
        Args:
            validator: Validator for candidate heuristics (creates default if None)
            timeout: Execution timeout per evaluation (seconds)
        """
        self.validator = validator or HeuristicValidator()
        self.timeout = timeout
        self.harness = RouteHarness()
    
    def evaluate_candidate(
        self,
        candidate: CandidateHeuristic,
        instances: List[DeliveryInstance],
        candidate_id: str,
        algorithm_name: Optional[str] = None
    ) -> BenchmarkResult:
        """
        Evaluate a candidate heuristic on multiple instances.
        
        Args:
            candidate: Candidate heuristic to evaluate
            instances: List of delivery instances to evaluate on
            candidate_id: Unique identifier for this candidate
            algorithm_name: Name for the algorithm (default: from candidate metadata)
            
        Returns:
            BenchmarkResult with aggregated metrics
        """
        # Validate candidate first
        validation = self.validator.validate(candidate)
        
        if not validation.is_valid:
            # All evaluations fail due to validation
            return self._create_validation_failed_result(
                candidate_id=candidate_id,
                algorithm_name=algorithm_name or "Invalid Heuristic",
                instances=instances,
                validation_errors=validation.errors
            )
        
        # Create scoring function
        try:
            scoring_function = create_scoring_function(
                source_code=candidate.source_code,
                function_name=candidate.function_name,
                timeout=self.timeout,
                validate_first=False  # Already validated
            )
        except Exception as e:
            return self._create_validation_failed_result(
                candidate_id=candidate_id,
                algorithm_name=algorithm_name or "Invalid Heuristic",
                instances=instances,
                validation_errors=[str(e)]
            )
        
        # Evaluate on each instance
        instance_results = []
        for instance in instances:
            result = self._evaluate_on_instance(
                scoring_function=scoring_function,
                instance=instance,
                algorithm_name=algorithm_name or f"Candidate {candidate_id}"
            )
            instance_results.append(result)
        
        # Aggregate results
        return self._aggregate_results(
            candidate_id=candidate_id,
            algorithm_name=algorithm_name or f"Candidate {candidate_id}",
            instance_results=instance_results
        )
    
    def _evaluate_on_instance(
        self,
        scoring_function: Callable,
        instance: DeliveryInstance,
        algorithm_name: str
    ) -> InstanceEvaluation:
        """
        Evaluate a scoring function on a single instance.
        
        Args:
            scoring_function: Validated scoring function
            instance: Delivery instance to evaluate on
            algorithm_name: Name for the algorithm
            
        Returns:
            InstanceEvaluation with result or failure details
        """
        start_time = time.time()
        
        try:
            # Compute distance matrix
            locations = instance.get_all_locations()
            distance_matrix = compute_distance_matrix(locations)
            
            # Build route using harness
            result = self.harness.build_route(
                heuristic=scoring_function,
                distance_matrix=distance_matrix,
                n_stops=instance.n_stops,
                algorithm_name=algorithm_name
            )
            
            # Validate route correctness
            try:
                validate_route(
                    route=result.route,
                    n_stops=instance.n_stops
                )
            except ValueError as e:
                execution_time = time.time() - start_time
                return InstanceEvaluation(
                    instance_seed=instance.seed,
                    n_stops=instance.n_stops,
                    status=EvaluationStatus.INVALID_ROUTE,
                    route=result.route,
                    distance=None,
                    execution_time=execution_time,
                    error_message=f"Route validation failed: {e}"
                )
            
            # Success
            execution_time = time.time() - start_time
            return InstanceEvaluation(
                instance_seed=instance.seed,
                n_stops=instance.n_stops,
                status=EvaluationStatus.SUCCESS,
                route=result.route,
                distance=result.total_distance,
                execution_time=execution_time,
                error_message=None
            )
            
        except ValueError as e:
            # Harness raised ValueError (invalid heuristic output)
            execution_time = time.time() - start_time
            return InstanceEvaluation(
                instance_seed=instance.seed,
                n_stops=instance.n_stops,
                status=EvaluationStatus.EXECUTION_FAILED,
                route=None,
                distance=None,
                execution_time=execution_time,
                error_message=f"Execution error: {e}"
            )
        
        except Exception as e:
            # Unexpected error during route construction
            execution_time = time.time() - start_time
            return InstanceEvaluation(
                instance_seed=instance.seed,
                n_stops=instance.n_stops,
                status=EvaluationStatus.CONSTRUCTION_FAILED,
                route=None,
                distance=None,
                execution_time=execution_time,
                error_message=f"Construction failed: {type(e).__name__}: {e}"
            )
    
    def _create_validation_failed_result(
        self,
        candidate_id: str,
        algorithm_name: str,
        instances: List[DeliveryInstance],
        validation_errors: List[str]
    ) -> BenchmarkResult:
        """Create a BenchmarkResult for a candidate that failed validation."""
        error_msg = "; ".join(validation_errors)
        
        instance_results = [
            InstanceEvaluation(
                instance_seed=inst.seed,
                n_stops=inst.n_stops,
                status=EvaluationStatus.VALIDATION_FAILED,
                route=None,
                distance=None,
                execution_time=0.0,
                error_message=error_msg
            )
            for inst in instances
        ]
        
        return BenchmarkResult(
            candidate_id=candidate_id,
            algorithm_name=algorithm_name,
            instances_evaluated=len(instances),
            successful_evaluations=0,
            failed_evaluations=len(instances),
            total_distance=None,
            mean_distance=None,
            median_distance=None,
            success_rate=0.0,
            total_execution_time=0.0,
            per_instance_results=instance_results,
            failure_breakdown={"validation_failed": len(instances)}
        )
    
    def _aggregate_results(
        self,
        candidate_id: str,
        algorithm_name: str,
        instance_results: List[InstanceEvaluation]
    ) -> BenchmarkResult:
        """
        Aggregate instance results into benchmark metrics.
        
        Args:
            candidate_id: Candidate identifier
            algorithm_name: Algorithm name
            instance_results: List of instance evaluation results
            
        Returns:
            BenchmarkResult with aggregated metrics
        """
        total_instances = len(instance_results)
        successful = [r for r in instance_results if r.status == EvaluationStatus.SUCCESS]
        failed = [r for r in instance_results if r.status != EvaluationStatus.SUCCESS]
        
        # Count failures by type
        failure_breakdown = Counter(r.status.value for r in failed)
        
        # Calculate distance metrics
        if successful:
            distances = [r.distance for r in successful]
            total_distance = sum(distances)
            mean_distance = np.mean(distances)
            median_distance = np.median(distances)
        else:
            total_distance = None
            mean_distance = None
            median_distance = None
        
        # Calculate execution time
        total_execution_time = sum(r.execution_time or 0.0 for r in instance_results)
        
        # Calculate success rate
        success_rate = len(successful) / total_instances if total_instances > 0 else 0.0
        
        return BenchmarkResult(
            candidate_id=candidate_id,
            algorithm_name=algorithm_name,
            instances_evaluated=total_instances,
            successful_evaluations=len(successful),
            failed_evaluations=len(failed),
            total_distance=total_distance,
            mean_distance=mean_distance,
            median_distance=median_distance,
            success_rate=success_rate,
            total_execution_time=total_execution_time,
            per_instance_results=instance_results,
            failure_breakdown=dict(failure_breakdown)
        )
    
    def evaluate_baseline_nn(
        self,
        instances: List[DeliveryInstance]
    ) -> BenchmarkResult:
        """
        Evaluate Nearest Neighbor baseline on instances.
        
        Args:
            instances: List of delivery instances
            
        Returns:
            BenchmarkResult for Nearest Neighbor
        """
        instance_results = []
        
        for instance in instances:
            start_time = time.time()
            
            try:
                # Compute distance matrix
                locations = instance.get_all_locations()
                distance_matrix = compute_distance_matrix(locations)
                
                # Run Nearest Neighbor
                result = nearest_neighbor(distance_matrix)
                
                # Validate route
                validate_route(
                    route=result.route,
                    n_stops=instance.n_stops
                )
                
                execution_time = time.time() - start_time
                instance_results.append(InstanceEvaluation(
                    instance_seed=instance.seed,
                    n_stops=instance.n_stops,
                    status=EvaluationStatus.SUCCESS,
                    route=result.route,
                    distance=result.total_distance,
                    execution_time=execution_time,
                    error_message=None
                ))
                
            except Exception as e:
                execution_time = time.time() - start_time
                instance_results.append(InstanceEvaluation(
                    instance_seed=instance.seed,
                    n_stops=instance.n_stops,
                    status=EvaluationStatus.CONSTRUCTION_FAILED,
                    route=None,
                    distance=None,
                    execution_time=execution_time,
                    error_message=str(e)
                ))
        
        return self._aggregate_results(
            candidate_id="baseline_nn",
            algorithm_name="Nearest Neighbor",
            instance_results=instance_results
        )
    
    def evaluate_baseline_2opt(
        self,
        instances: List[DeliveryInstance],
        max_2opt_iterations: int = 100
    ) -> BenchmarkResult:
        """
        Evaluate Nearest Neighbor + 2-Opt baseline on instances.
        
        Args:
            instances: List of delivery instances
            max_2opt_iterations: Maximum 2-Opt iterations per instance
            
        Returns:
            BenchmarkResult for NN + 2-Opt
        """
        instance_results = []
        
        for instance in instances:
            start_time = time.time()
            
            try:
                # Compute distance matrix
                locations = instance.get_all_locations()
                distance_matrix = compute_distance_matrix(locations)
                
                # Run NN + 2-Opt
                result = nearest_neighbor_with_2opt(
                    distance_matrix,
                    max_2opt_iterations=max_2opt_iterations
                )
                
                # Validate route
                validate_route(
                    route=result.route,
                    n_stops=instance.n_stops
                )
                
                execution_time = time.time() - start_time
                instance_results.append(InstanceEvaluation(
                    instance_seed=instance.seed,
                    n_stops=instance.n_stops,
                    status=EvaluationStatus.SUCCESS,
                    route=result.route,
                    distance=result.total_distance,
                    execution_time=execution_time,
                    error_message=None
                ))
                
            except Exception as e:
                execution_time = time.time() - start_time
                instance_results.append(InstanceEvaluation(
                    instance_seed=instance.seed,
                    n_stops=instance.n_stops,
                    status=EvaluationStatus.CONSTRUCTION_FAILED,
                    route=None,
                    distance=None,
                    execution_time=execution_time,
                    error_message=str(e)
                ))
        
        return self._aggregate_results(
            candidate_id="baseline_2opt",
            algorithm_name="Nearest Neighbor + 2-Opt",
            instance_results=instance_results
        )
    
    def compare_with_baselines(
        self,
        candidate_result: BenchmarkResult,
        instances: List[DeliveryInstance],
        max_2opt_iterations: int = 100
    ) -> ComparisonMetrics:
        """
        Compare candidate with both baseline algorithms.
        
        Baselines are evaluated on the same instances for fair comparison.
        
        Args:
            candidate_result: Candidate's benchmark result
            instances: Instances to evaluate baselines on
            max_2opt_iterations: Maximum 2-Opt iterations
            
        Returns:
            ComparisonMetrics with improvement percentages
        """
        # Evaluate baselines on same instances
        nn_result = self.evaluate_baseline_nn(instances)
        two_opt_result = self.evaluate_baseline_2opt(instances, max_2opt_iterations)
        
        # Calculate improvement percentages
        improvement_vs_nn = self._calculate_improvement(
            candidate_mean=candidate_result.mean_distance,
            baseline_mean=nn_result.mean_distance
        )
        
        improvement_vs_2opt = self._calculate_improvement(
            candidate_mean=candidate_result.mean_distance,
            baseline_mean=two_opt_result.mean_distance
        )
        
        # Build per-instance comparisons
        per_instance = self._build_per_instance_comparisons(
            candidate_result=candidate_result,
            nn_result=nn_result,
            two_opt_result=two_opt_result
        )
        
        return ComparisonMetrics(
            candidate_result=candidate_result,
            baseline_nn_result=nn_result,
            baseline_2opt_result=two_opt_result,
            improvement_vs_nn=improvement_vs_nn,
            improvement_vs_2opt=improvement_vs_2opt,
            per_instance_comparisons=per_instance
        )
    
    def _calculate_improvement(
        self,
        candidate_mean: Optional[float],
        baseline_mean: Optional[float]
    ) -> Optional[float]:
        """
        Calculate improvement percentage.
        
        Formula: ((baseline - candidate) / baseline) × 100
        
        Positive = candidate is better (shorter distance)
        Negative = candidate is worse (longer distance)
        
        Args:
            candidate_mean: Candidate mean distance
            baseline_mean: Baseline mean distance
            
        Returns:
            Improvement percentage or None if either is None
        """
        if candidate_mean is None or baseline_mean is None:
            return None
        
        if baseline_mean == 0:
            # Avoid division by zero
            if candidate_mean == 0:
                return 0.0
            else:
                # Candidate is worse (has non-zero distance vs zero baseline)
                return -100.0
        
        improvement = ((baseline_mean - candidate_mean) / baseline_mean) * 100.0
        return improvement
    
    def _build_per_instance_comparisons(
        self,
        candidate_result: BenchmarkResult,
        nn_result: BenchmarkResult,
        two_opt_result: BenchmarkResult
    ) -> List[dict]:
        """Build per-instance comparison data."""
        comparisons = []
        
        for i in range(len(candidate_result.per_instance_results)):
            cand = candidate_result.per_instance_results[i]
            nn = nn_result.per_instance_results[i]
            two_opt = two_opt_result.per_instance_results[i]
            
            comp = {
                "instance_seed": cand.instance_seed,
                "n_stops": cand.n_stops,
                "candidate_distance": cand.distance,
                "candidate_status": cand.status.value,
                "nn_distance": nn.distance,
                "two_opt_distance": two_opt.distance,
            }
            
            # Calculate per-instance improvements
            if cand.distance is not None and nn.distance is not None:
                comp["improvement_vs_nn"] = self._calculate_improvement(
                    cand.distance, nn.distance
                )
            
            if cand.distance is not None and two_opt.distance is not None:
                comp["improvement_vs_2opt"] = self._calculate_improvement(
                    cand.distance, two_opt.distance
                )
            
            comparisons.append(comp)
        
        return comparisons
