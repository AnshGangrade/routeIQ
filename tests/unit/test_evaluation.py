"""
Unit tests for heuristic evaluation system.

Tests evaluator, fitness scoring, selection, and feedback preparation.
"""

import pytest
import numpy as np

from engine.evaluation import (
    HeuristicEvaluator,
    FitnessFunction,
    WeightedFitnessFunction,
    CandidateSelector,
    prepare_feedback,
    EvaluationStatus,
    BenchmarkResult,
)
from engine.sandbox import CandidateHeuristic
from engine.instances import InstanceGenerator


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def small_instances():
    """Generate small test instances."""
    generator = InstanceGenerator(seed=100)
    return generator.generate_batch(n_instances=3, n_stops=5, start_seed=100)


@pytest.fixture
def valid_candidate():
    """Valid nearest-distance candidate."""
    code = """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
"""
    return CandidateHeuristic(source_code=code, function_name="score_candidates")


@pytest.fixture
def invalid_candidate():
    """Invalid candidate with import statement."""
    code = """
import os

def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
"""
    return CandidateHeuristic(source_code=code, function_name="score_candidates")


@pytest.fixture
def failing_candidate():
    """Candidate that will fail at runtime."""
    code = """
def score_candidates(context):
    # Will fail: returns wrong type
    return "not a valid result"
"""
    return CandidateHeuristic(source_code=code, function_name="score_candidates")


# ============================================================================
# Evaluator Tests
# ============================================================================

class TestHeuristicEvaluator:
    """Test the HeuristicEvaluator class."""
    
    def test_create_evaluator(self):
        """Test creating evaluator."""
        evaluator = HeuristicEvaluator()
        assert evaluator is not None
        assert evaluator.harness is not None
    
    def test_evaluate_valid_candidate(self, valid_candidate, small_instances):
        """Test evaluating a valid candidate."""
        evaluator = HeuristicEvaluator()
        
        result = evaluator.evaluate_candidate(
            candidate=valid_candidate,
            instances=small_instances,
            candidate_id="test_001"
        )
        
        assert result.candidate_id == "test_001"
        assert result.instances_evaluated == 3
        assert result.successful_evaluations == 3
        assert result.failed_evaluations == 0
        assert result.success_rate == 1.0
        assert result.mean_distance is not None
        assert result.median_distance is not None
        assert result.total_distance is not None
        assert len(result.per_instance_results) == 3
    
    def test_evaluate_invalid_candidate(self, invalid_candidate, small_instances):
        """Test evaluating candidate that fails validation."""
        evaluator = HeuristicEvaluator()
        
        result = evaluator.evaluate_candidate(
            candidate=invalid_candidate,
            instances=small_instances,
            candidate_id="test_invalid"
        )
        
        assert result.candidate_id == "test_invalid"
        assert result.instances_evaluated == 3
        assert result.successful_evaluations == 0
        assert result.failed_evaluations == 3
        assert result.success_rate == 0.0
        assert result.mean_distance is None
        assert "validation_failed" in result.failure_breakdown
    
    def test_evaluate_failing_candidate(self, failing_candidate, small_instances):
        """Test evaluating candidate that fails at execution."""
        evaluator = HeuristicEvaluator()
        
        result = evaluator.evaluate_candidate(
            candidate=failing_candidate,
            instances=small_instances,
            candidate_id="test_failing"
        )
        
        assert result.candidate_id == "test_failing"
        assert result.successful_evaluations == 0
        assert result.failed_evaluations == 3
        assert result.success_rate == 0.0
        assert result.failure_breakdown.get("execution_failed", 0) > 0
    
    def test_baseline_nn_evaluation(self, small_instances):
        """Test evaluating Nearest Neighbor baseline."""
        evaluator = HeuristicEvaluator()
        
        result = evaluator.evaluate_baseline_nn(small_instances)
        
        assert result.candidate_id == "baseline_nn"
        assert result.algorithm_name == "Nearest Neighbor"
        assert result.successful_evaluations == 3
        assert result.success_rate == 1.0
        assert result.mean_distance is not None
    
    def test_baseline_2opt_evaluation(self, small_instances):
        """Test evaluating NN + 2-Opt baseline."""
        evaluator = HeuristicEvaluator()
        
        result = evaluator.evaluate_baseline_2opt(small_instances, max_2opt_iterations=10)
        
        assert result.candidate_id == "baseline_2opt"
        assert result.algorithm_name == "Nearest Neighbor + 2-Opt"
        assert result.successful_evaluations == 3
        assert result.success_rate == 1.0
        assert result.mean_distance is not None
    
    def test_compare_with_baselines(self, valid_candidate, small_instances):
        """Test comparison with baselines."""
        evaluator = HeuristicEvaluator()
        
        # Evaluate candidate
        candidate_result = evaluator.evaluate_candidate(
            candidate=valid_candidate,
            instances=small_instances,
            candidate_id="test_comp"
        )
        
        # Compare with baselines
        comparison = evaluator.compare_with_baselines(
            candidate_result=candidate_result,
            instances=small_instances
        )
        
        assert comparison.candidate_result == candidate_result
        assert comparison.baseline_nn_result is not None
        assert comparison.baseline_2opt_result is not None
        assert comparison.improvement_vs_nn is not None
        assert comparison.improvement_vs_2opt is not None
        assert len(comparison.per_instance_comparisons) == 3


class TestImprovementCalculation:
    """Test improvement percentage calculations."""
    
    def test_improvement_calculation_better(self):
        """Test improvement when candidate is better."""
        evaluator = HeuristicEvaluator()
        
        # Candidate: 80, Baseline: 100
        # Improvement: (100 - 80) / 100 = 20%
        improvement = evaluator._calculate_improvement(
            candidate_mean=80.0,
            baseline_mean=100.0
        )
        
        assert improvement == pytest.approx(20.0)
    
    def test_improvement_calculation_worse(self):
        """Test improvement when candidate is worse."""
        evaluator = HeuristicEvaluator()
        
        # Candidate: 120, Baseline: 100
        # Improvement: (100 - 120) / 100 = -20%
        improvement = evaluator._calculate_improvement(
            candidate_mean=120.0,
            baseline_mean=100.0
        )
        
        assert improvement == pytest.approx(-20.0)
    
    def test_improvement_calculation_equal(self):
        """Test improvement when equal."""
        evaluator = HeuristicEvaluator()
        
        improvement = evaluator._calculate_improvement(
            candidate_mean=100.0,
            baseline_mean=100.0
        )
        
        assert improvement == pytest.approx(0.0)
    
    def test_improvement_with_none_values(self):
        """Test improvement with None values."""
        evaluator = HeuristicEvaluator()
        
        assert evaluator._calculate_improvement(None, 100.0) is None
        assert evaluator._calculate_improvement(100.0, None) is None
        assert evaluator._calculate_improvement(None, None) is None
    
    def test_improvement_zero_baseline(self):
        """Test improvement with zero baseline."""
        evaluator = HeuristicEvaluator()
        
        # Both zero
        improvement = evaluator._calculate_improvement(0.0, 0.0)
        assert improvement == pytest.approx(0.0)
        
        # Non-zero candidate, zero baseline
        improvement = evaluator._calculate_improvement(100.0, 0.0)
        assert improvement is None  # Percentage is undefined against a zero baseline.


# ============================================================================
# Fitness Function Tests
# ============================================================================

class TestFitnessFunction:
    """Test fitness scoring."""
    
    def test_create_fitness_function(self):
        """Test creating fitness function."""
        fitness = FitnessFunction()
        assert fitness is not None
    
    def test_fitness_successful_candidate(self):
        """Test fitness for fully successful candidate."""
        fitness = FitnessFunction()
        
        result = BenchmarkResult(
            candidate_id="test",
            algorithm_name="Test",
            instances_evaluated=5,
            successful_evaluations=5,
            failed_evaluations=0,
            mean_distance=100.0,
            median_distance=95.0,
            success_rate=1.0,
            total_execution_time=1.0,
            total_distance=500.0,
            per_instance_results=[],
            failure_breakdown={}
        )
        
        score = fitness.calculate(result)
        assert score == pytest.approx(100.0)
    
    def test_fitness_failed_candidate(self):
        """Test fitness for completely failed candidate."""
        fitness = FitnessFunction()
        
        result = BenchmarkResult(
            candidate_id="test",
            algorithm_name="Test",
            instances_evaluated=5,
            successful_evaluations=0,
            failed_evaluations=5,
            mean_distance=None,
            median_distance=None,
            success_rate=0.0,
            total_execution_time=0.0,
            total_distance=None,
            per_instance_results=[],
            failure_breakdown={"validation_failed": 5}
        )
        
        score = fitness.calculate(result)
        assert score == float('inf')
    
    def test_fitness_partial_failure(self):
        """Test fitness for partially failed candidate."""
        fitness = FitnessFunction()  # Default: requires 100% success
        
        result = BenchmarkResult(
            candidate_id="test",
            algorithm_name="Test",
            instances_evaluated=10,
            successful_evaluations=8,
            failed_evaluations=2,
            mean_distance=100.0,
            median_distance=95.0,
            success_rate=0.8,
            total_execution_time=1.0,
            total_distance=800.0,
            per_instance_results=[],
            failure_breakdown={"execution_failed": 2}
        )
        
        score = fitness.calculate(result)
        # With default threshold (1.0), partial failures get infinite penalty
        assert score == float('inf')
    
    def test_fitness_with_custom_threshold(self):
        """Test fitness with custom success threshold."""
        fitness = FitnessFunction(success_rate_threshold=0.7)
        
        # 80% success - should pass threshold
        result = BenchmarkResult(
            candidate_id="test",
            algorithm_name="Test",
            instances_evaluated=10,
            successful_evaluations=8,
            failed_evaluations=2,
            mean_distance=100.0,
            median_distance=95.0,
            success_rate=0.8,
            total_execution_time=1.0,
            total_distance=800.0,
            per_instance_results=[],
            failure_breakdown={}
        )
        
        score = fitness.calculate(result)
        assert score == pytest.approx(100.0)
    
    def test_fitness_batch_calculation(self):
        """Test batch fitness calculation."""
        fitness = FitnessFunction()
        
        results = [
            BenchmarkResult(
                candidate_id="good",
                algorithm_name="Good",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=100.0,
                median_distance=95.0,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=500.0,
                per_instance_results=[],
                failure_breakdown={}
            ),
            BenchmarkResult(
                candidate_id="bad",
                algorithm_name="Bad",
                instances_evaluated=5,
                successful_evaluations=0,
                failed_evaluations=5,
                mean_distance=None,
                median_distance=None,
                success_rate=0.0,
                total_execution_time=0.0,
                total_distance=None,
                per_instance_results=[],
                failure_breakdown={}
            )
        ]
        
        scores = fitness.calculate_batch(results)
        assert len(scores) == 2
        assert scores["good"] == pytest.approx(100.0)
        assert scores["bad"] == float('inf')


class TestWeightedFitnessFunction:
    """Test weighted fitness scoring."""
    
    def test_weighted_fitness_perfect(self):
        """Test weighted fitness with perfect success."""
        fitness = WeightedFitnessFunction()
        
        result = BenchmarkResult(
            candidate_id="test",
            algorithm_name="Test",
            instances_evaluated=10,
            successful_evaluations=10,
            failed_evaluations=0,
            mean_distance=100.0,
            median_distance=95.0,
            success_rate=1.0,
            total_execution_time=1.0,
            total_distance=1000.0,
            per_instance_results=[],
            failure_breakdown={}
        )
        
        score = fitness.calculate(result)
        # multiplier = 2.0 - 1.0 = 1.0
        assert score == pytest.approx(100.0)
    
    def test_weighted_fitness_partial(self):
        """Test weighted fitness with partial success."""
        fitness = WeightedFitnessFunction()
        
        result = BenchmarkResult(
            candidate_id="test",
            algorithm_name="Test",
            instances_evaluated=10,
            successful_evaluations=5,
            failed_evaluations=5,
            mean_distance=100.0,
            median_distance=95.0,
            success_rate=0.5,
            total_execution_time=1.0,
            total_distance=500.0,
            per_instance_results=[],
            failure_breakdown={}
        )
        
        score = fitness.calculate(result)
        # multiplier = 2.0 - 0.5 = 1.5
        assert score == pytest.approx(150.0)
    
    def test_weighted_fitness_complete_failure(self):
        """Test weighted fitness with complete failure."""
        fitness = WeightedFitnessFunction()
        
        result = BenchmarkResult(
            candidate_id="test",
            algorithm_name="Test",
            instances_evaluated=10,
            successful_evaluations=0,
            failed_evaluations=10,
            mean_distance=None,
            median_distance=None,
            success_rate=0.0,
            total_execution_time=0.0,
            total_distance=None,
            per_instance_results=[],
            failure_breakdown={}
        )
        
        score = fitness.calculate(result)
        assert score == float('inf')


# ============================================================================
# Selection Tests
# ============================================================================

class TestCandidateSelector:
    """Test candidate selection."""
    
    def test_create_selector(self):
        """Test creating selector."""
        selector = CandidateSelector()
        assert selector is not None
    
    def test_select_best_single(self):
        """Test selecting single best candidate."""
        selector = CandidateSelector()
        
        results = [
            BenchmarkResult(
                candidate_id="good",
                algorithm_name="Good",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=80.0,
                median_distance=75.0,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=400.0,
                per_instance_results=[],
                failure_breakdown={}
            ),
            BenchmarkResult(
                candidate_id="medium",
                algorithm_name="Medium",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=100.0,
                median_distance=95.0,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=500.0,
                per_instance_results=[],
                failure_breakdown={}
            ),
            BenchmarkResult(
                candidate_id="bad",
                algorithm_name="Bad",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=150.0,
                median_distance=145.0,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=750.0,
                per_instance_results=[],
                failure_breakdown={}
            )
        ]
        
        selection = selector.select_best(results, n_select=1)
        
        assert len(selection.selected_candidates) == 1
        assert selection.selected_candidates[0] == "good"
        assert selection.rankings["good"] == 1
        assert selection.rankings["medium"] == 2
        assert selection.rankings["bad"] == 3
    
    def test_select_best_multiple(self):
        """Test selecting multiple best candidates."""
        selector = CandidateSelector()
        
        results = [
            BenchmarkResult(
                candidate_id=f"cand_{i}",
                algorithm_name=f"Cand {i}",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=100.0 + i * 10,
                median_distance=95.0 + i * 10,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=500.0 + i * 50,
                per_instance_results=[],
                failure_breakdown={}
            )
            for i in range(5)
        ]
        
        selection = selector.select_best(results, n_select=3)
        
        assert len(selection.selected_candidates) == 3
        assert selection.selected_candidates == ["cand_0", "cand_1", "cand_2"]
    
    def test_select_with_failures(self):
        """Test selection with failed candidates."""
        selector = CandidateSelector()
        
        results = [
            BenchmarkResult(
                candidate_id="success",
                algorithm_name="Success",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=100.0,
                median_distance=95.0,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=500.0,
                per_instance_results=[],
                failure_breakdown={}
            ),
            BenchmarkResult(
                candidate_id="failure",
                algorithm_name="Failure",
                instances_evaluated=5,
                successful_evaluations=0,
                failed_evaluations=5,
                mean_distance=None,
                median_distance=None,
                success_rate=0.0,
                total_execution_time=0.0,
                total_distance=None,
                per_instance_results=[],
                failure_breakdown={}
            )
        ]
        
        selection = selector.select_best(results, n_select=1)
        
        assert selection.selected_candidates[0] == "success"
        assert selection.rankings["success"] == 1
        assert selection.rankings["failure"] == 2
    
    def test_select_tie_breaking(self):
        """Test deterministic tie-breaking."""
        selector = CandidateSelector()
        
        # Two candidates with same fitness
        results = [
            BenchmarkResult(
                candidate_id="alpha",
                algorithm_name="Alpha",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=100.0,
                median_distance=95.0,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=500.0,
                per_instance_results=[],
                failure_breakdown={}
            ),
            BenchmarkResult(
                candidate_id="beta",
                algorithm_name="Beta",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=100.0,  # Same as alpha
                median_distance=95.0,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=500.0,
                per_instance_results=[],
                failure_breakdown={}
            )
        ]
        
        selection = selector.select_best(results, n_select=1)
        
        # Lexicographic tie-breaking: "alpha" < "beta"
        assert selection.selected_candidates[0] == "alpha"
    
    def test_select_empty_raises_error(self):
        """Test that selecting from empty list raises error."""
        selector = CandidateSelector()
        
        with pytest.raises(ValueError, match="empty"):
            selector.select_best([], n_select=1)
    
    def test_select_invalid_n_raises_error(self):
        """Test that invalid n_select raises error."""
        selector = CandidateSelector()
        results = [
            BenchmarkResult(
                candidate_id="test",
                algorithm_name="Test",
                instances_evaluated=5,
                successful_evaluations=5,
                failed_evaluations=0,
                mean_distance=100.0,
                median_distance=95.0,
                success_rate=1.0,
                total_execution_time=1.0,
                total_distance=500.0,
                per_instance_results=[],
                failure_breakdown={}
            )
        ]
        
        with pytest.raises(ValueError, match="n_select"):
            selector.select_best(results, n_select=0)


# ============================================================================
# Feedback Tests
# ============================================================================

class TestFeedbackPreparation:
    """Test feedback preparation."""
    
    def test_prepare_feedback_success(self, valid_candidate, small_instances):
        """Test preparing feedback for successful candidate."""
        evaluator = HeuristicEvaluator()
        
        # Evaluate candidate
        candidate_result = evaluator.evaluate_candidate(
            candidate=valid_candidate,
            instances=small_instances,
            candidate_id="test_fb"
        )
        
        # Compare with baselines
        comparison = evaluator.compare_with_baselines(
            candidate_result=candidate_result,
            instances=small_instances
        )
        
        # Calculate fitness
        fitness_fn = FitnessFunction()
        fitness = fitness_fn.calculate(candidate_result)
        
        # Prepare feedback
        feedback = prepare_feedback(comparison, fitness)
        
        assert feedback.candidate_id == "test_fb"
        assert feedback.fitness_score == fitness
        assert feedback.success_rate == 1.0
        assert feedback.mean_distance is not None
        assert feedback.improvement_vs_nn is not None
        assert feedback.improvement_vs_2opt is not None
    
    def test_feedback_to_text(self, valid_candidate, small_instances):
        """Test converting feedback to text."""
        evaluator = HeuristicEvaluator()
        
        candidate_result = evaluator.evaluate_candidate(
            candidate=valid_candidate,
            instances=small_instances,
            candidate_id="test_text"
        )
        
        comparison = evaluator.compare_with_baselines(
            candidate_result=candidate_result,
            instances=small_instances
        )
        
        fitness_fn = FitnessFunction()
        fitness = fitness_fn.calculate(candidate_result)
        
        feedback = prepare_feedback(comparison, fitness)
        text = feedback.to_feedback_text()
        
        assert isinstance(text, str)
        assert len(text) > 0
        assert "fitness score" in text.lower()
        assert "success rate" in text.lower()
        assert "baseline" in text.lower()


# ============================================================================
# Integration Tests
# ============================================================================

class TestEndToEndEvaluation:
    """End-to-end evaluation tests."""
    
    def test_full_evaluation_pipeline(self, valid_candidate, small_instances):
        """Test complete evaluation pipeline."""
        # 1. Create evaluator
        evaluator = HeuristicEvaluator()
        
        # 2. Evaluate candidate
        result = evaluator.evaluate_candidate(
            candidate=valid_candidate,
            instances=small_instances,
            candidate_id="e2e_test"
        )
        
        assert result.success_rate == 1.0
        
        # 3. Compare with baselines
        comparison = evaluator.compare_with_baselines(
            candidate_result=result,
            instances=small_instances
        )
        
        assert comparison.improvement_vs_nn is not None
        
        # 4. Calculate fitness
        fitness_fn = FitnessFunction()
        fitness = fitness_fn.calculate(result)
        
        assert fitness < float('inf')
        
        # 5. Select best (single candidate)
        selector = CandidateSelector(fitness_function=fitness_fn)
        selection = selector.select_best([result], n_select=1)
        
        assert len(selection.selected_candidates) == 1
        
        # 6. Prepare feedback
        feedback = prepare_feedback(comparison, fitness)
        feedback_text = feedback.to_feedback_text()
        
        assert len(feedback_text) > 0
