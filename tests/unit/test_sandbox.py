"""
Unit tests for candidate heuristic validation and execution.

Tests verify:
- Static AST validation (allowlist-based)
- Rejection of dangerous constructs WITHOUT executing them
- Controlled execution with timeout
- Integration with existing harness
"""

import pytest
import numpy as np
from engine.sandbox import (
    CandidateHeuristic,
    ValidationResult,
    ExecutionResult,
    HeuristicValidator,
    HeuristicExecutor,
    CandidateAdapter,
    create_scoring_function,
)
from engine.heuristics import HeuristicContext, HeuristicResult, RouteHarness
from engine.instances import InstanceGenerator, compute_distance_matrix


# Valid candidate examples for testing
VALID_NEAREST_DISTANCE = """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
"""

VALID_WITH_HEURISTIC_RESULT = """
def score_candidates(context):
    from engine.heuristics import HeuristicResult
    scores = {
        stop: float(context.distance_matrix[context.current_location, stop])
        for stop in context.candidate_stops
    }
    return HeuristicResult(scores=scores)
"""

VALID_COMPLEX_LOGIC = """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        base_score = context.distance_matrix[context.current_location, stop]
        
        # Prefer stops closer to depot
        if len(context.partial_route) > 1:
            depot_dist = context.distance_matrix[stop, 0]
            base_score = base_score * 0.7 + depot_dist * 0.3
        
        scores[stop] = base_score
    
    return {"scores": scores}
"""


class TestCandidateHeuristic:
    """Test CandidateHeuristic model."""
    
    def test_model_creation(self):
        """CandidateHeuristic should store source and function name."""
        candidate = CandidateHeuristic(
            source_code="def score_candidates(ctx): pass",
            function_name="score_candidates"
        )
        assert candidate.source_code == "def score_candidates(ctx): pass"
        assert candidate.function_name == "score_candidates"
        assert candidate.metadata == {}
    
    def test_default_function_name(self):
        """Function name defaults to score_candidates."""
        candidate = CandidateHeuristic(source_code="def score_candidates(ctx): pass")
        assert candidate.function_name == "score_candidates"
    
    def test_with_metadata(self):
        """CandidateHeuristic can store metadata."""
        candidate = CandidateHeuristic(
            source_code="def score_candidates(ctx): pass",
            metadata={"temperature": 0.7, "model": "gpt-4"}
        )
        assert candidate.metadata["temperature"] == 0.7
        assert candidate.metadata["model"] == "gpt-4"


class TestValidationResult:
    """Test ValidationResult model."""
    
    def test_valid_result(self):
        """Valid result should have VALID status."""
        result = ValidationResult(status="valid", errors=[], warnings=[])
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_invalid_result(self):
        """Invalid result should have INVALID status and errors."""
        result = ValidationResult(
            status="invalid",
            errors=["Syntax error", "Missing function"]
        )
        assert not result.is_valid
        assert len(result.errors) == 2


class TestHeuristicValidator:
    """Test static AST validation."""
    
    def test_valid_simple_heuristic(self):
        """Validator should accept valid simple heuristic."""
        candidate = CandidateHeuristic(source_code=VALID_NEAREST_DISTANCE)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_valid_complex_heuristic(self):
        """Validator should accept valid complex heuristic."""
        candidate = CandidateHeuristic(source_code=VALID_COMPLEX_LOGIC)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_reject_syntax_error(self):
        """Validator should reject code with syntax errors."""
        code = "def score_candidates(context):\n    return {1: 10.0"  # Missing }
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Syntax error" in err for err in result.errors)
    
    def test_reject_no_function(self):
        """Validator should reject code with no function."""
        code = "x = 5"
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("No function definition" in err for err in result.errors)
    
    def test_reject_wrong_function_name(self):
        """Validator should reject function with wrong name."""
        code = "def wrong_name(context):\n    return {'scores': {}}"
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Function name mismatch" in err for err in result.errors)
    
    def test_reject_multiple_functions(self):
        """Validator should reject code with multiple functions."""
        code = """
def score_candidates(context):
    return {"scores": {}}

def helper():
    return 5
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Multiple function definitions" in err for err in result.errors)
    
    def test_reject_import_statement(self):
        """Validator should reject import statements."""
        code = """
import os

def score_candidates(context):
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Import statements not allowed" in err for err in result.errors)
    
    def test_reject_from_import(self):
        """Validator should reject from imports."""
        code = """
from os import environ

def score_candidates(context):
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Import statements not allowed" in err for err in result.errors)
    
    def test_reject_exec(self):
        """Validator should reject exec()."""
        code = """
def score_candidates(context):
    exec("print('hello')")
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Forbidden function call: exec" in err for err in result.errors)
    
    def test_reject_eval(self):
        """Validator should reject eval()."""
        code = """
def score_candidates(context):
    x = eval("1 + 1")
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Forbidden function call: eval" in err for err in result.errors)
    
    def test_reject_open(self):
        """Validator should reject open() for file access."""
        code = """
def score_candidates(context):
    with open('/etc/passwd') as f:
        data = f.read()
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Forbidden function call: open" in err for err in result.errors)
    
    def test_reject_getattr(self):
        """Validator should reject getattr()."""
        code = """
def score_candidates(context):
    attr = getattr(context, 'distance_matrix')
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Forbidden function call: getattr" in err for err in result.errors)
    
    def test_reject_globals(self):
        """Validator should reject globals()."""
        code = """
def score_candidates(context):
    g = globals()
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Forbidden function call: globals" in err for err in result.errors)
    
    def test_reject_underscore_attribute(self):
        """Validator should reject underscore-prefixed attributes."""
        code = """
def score_candidates(context):
    x = context.__dict__
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("underscore-prefixed attributes" in err for err in result.errors)
    
    def test_reject_context_assignment(self):
        """Validator should reject assignment to context attributes."""
        code = """
def score_candidates(context):
    context.current_location = 999
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Cannot assign to context attributes" in err for err in result.errors)
    
    def test_reject_global_statement(self):
        """Validator should reject global statement."""
        code = """
def score_candidates(context):
    global x
    x = 5
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("global/nonlocal statements not allowed" in err for err in result.errors)
    
    def test_reject_nested_function(self):
        """Validator should reject nested function definitions."""
        code = """
def score_candidates(context):
    def helper():
        return 5
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Nested function definitions not allowed" in err for err in result.errors)
    
    def test_reject_class_definition(self):
        """Validator should reject class definitions."""
        code = """
class Helper:
    pass

def score_candidates(context):
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Class definitions not allowed" in err for err in result.errors)
    
    def test_reject_unknown_context_attribute(self):
        """Validator should reject unknown context attributes."""
        code = """
def score_candidates(context):
    x = context.unknown_attribute
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("Unknown context attribute" in err for err in result.errors)
    
    def test_accept_allowed_context_attributes(self):
        """Validator should accept all allowed context attributes."""
        code = """
def score_candidates(context):
    loc = context.current_location
    cands = context.candidate_stops
    dm = context.distance_matrix
    route = context.partial_route
    return {"scores": {cands[0]: 10.0}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert result.is_valid
    
    def test_warn_on_many_loops(self):
        """Validator should warn about many loops."""
        code = """
def score_candidates(context):
    for i in range(10):
        for j in range(10):
            for k in range(10):
                for l in range(10):
                    for m in range(10):
                        for n in range(10):
                            pass
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        # Should be valid but with warnings
        assert result.is_valid
        assert len(result.warnings) > 0
        assert any("Many loops" in warn for warn in result.warnings)
    
    def test_reject_too_long_source(self):
        """Validator should reject very long source code."""
        code = "def score_candidates(context):\n" + "    x = 1\n" * 5000
        candidate = CandidateHeuristic(source_code=code)
        validator = HeuristicValidator()
        result = validator.validate(candidate)
        
        assert not result.is_valid
        assert any("too long" in err for err in result.errors)


class TestHeuristicExecutor:
    """Test controlled execution of validated heuristics."""
    
    def test_execute_simple_heuristic(self):
        """Executor should run simple valid heuristic."""
        candidate = CandidateHeuristic(source_code=VALID_NEAREST_DISTANCE)
        executor = HeuristicExecutor(timeout=5.0)
        
        # Create test context
        dist_matrix = np.array([
            [0, 10, 20],
            [10, 0, 5],
            [20, 5, 0]
        ], dtype=float)
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1, 2],
            distance_matrix=dist_matrix,
            partial_route=[0]
        )
        
        result = executor.execute(candidate, context)
        
        assert result.is_success
        assert result.output is not None
        assert result.execution_time > 0
    
    def test_execute_returns_correct_scores(self):
        """Executor should return correct scores."""
        candidate = CandidateHeuristic(source_code=VALID_NEAREST_DISTANCE)
        executor = HeuristicExecutor(timeout=5.0)
        
        dist_matrix = np.array([
            [0, 10, 20],
            [10, 0, 5],
            [20, 5, 0]
        ], dtype=float)
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1, 2],
            distance_matrix=dist_matrix,
            partial_route=[0]
        )
        
        result = executor.execute(candidate, context)
        
        assert result.is_success
        scores = result.output['scores']
        assert scores[1] == 10.0
        assert scores[2] == 20.0
    
    def test_execute_to_heuristic_result(self):
        """execute_to_heuristic_result should convert output."""
        candidate = CandidateHeuristic(source_code=VALID_NEAREST_DISTANCE)
        executor = HeuristicExecutor(timeout=5.0)
        
        dist_matrix = np.array([[0, 10], [10, 0]], dtype=float)
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=dist_matrix,
            partial_route=[0]
        )
        
        heuristic_result = executor.execute_to_heuristic_result(candidate, context)
        
        assert isinstance(heuristic_result, HeuristicResult)
        assert heuristic_result.scores[1] == 10.0
    
    def test_execute_syntax_error(self):
        """Executor should handle syntax errors."""
        code = "def score_candidates(context):\n    return {1: 10.0"  # Missing }
        candidate = CandidateHeuristic(source_code=code)
        executor = HeuristicExecutor(timeout=5.0)
        
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=np.array([[0, 10], [10, 0]], dtype=float),
            partial_route=[0]
        )
        
        result = executor.execute(candidate, context)
        
        assert not result.is_success
        assert result.status == "syntax_error"
        assert "Syntax error" in result.error
    
    def test_execute_runtime_error(self):
        """Executor should handle runtime errors."""
        code = """
def score_candidates(context):
    x = 1 / 0  # Division by zero
    return {"scores": {}}
"""
        candidate = CandidateHeuristic(source_code=code)
        executor = HeuristicExecutor(timeout=5.0)
        
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=np.array([[0, 10], [10, 0]], dtype=float),
            partial_route=[0]
        )
        
        result = executor.execute(candidate, context)
        
        assert not result.is_success
        assert result.status == "runtime_error"
        assert "ZeroDivisionError" in result.error
    
    def test_execute_invalid_output_type(self):
        """Executor should reject invalid output types."""
        code = """
def score_candidates(context):
    return "not a dict or HeuristicResult"
"""
        candidate = CandidateHeuristic(source_code=code)
        executor = HeuristicExecutor(timeout=5.0)
        
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=np.array([[0, 10], [10, 0]], dtype=float),
            partial_route=[0]
        )
        
        result = executor.execute(candidate, context)
        
        assert not result.is_success
        assert result.status == "invalid_output"
        assert "Invalid output type" in result.error
    
    def test_execute_missing_scores(self):
        """Executor should reject output missing scores."""
        code = """
def score_candidates(context):
    return {"scores": {}}  # Empty scores
"""
        candidate = CandidateHeuristic(source_code=code)
        executor = HeuristicExecutor(timeout=5.0)
        
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=np.array([[0, 10], [10, 0]], dtype=float),
            partial_route=[0]
        )
        
        result = executor.execute(candidate, context)
        
        assert not result.is_success
        assert result.status == "invalid_output"
        assert "Score count mismatch" in result.error
    
    def test_execute_nan_score(self):
        """Executor should reject NaN scores."""
        code = """
def score_candidates(context):
    return {"scores": {1: float('nan')}}
"""
        candidate = CandidateHeuristic(source_code=code)
        executor = HeuristicExecutor(timeout=5.0)
        
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=np.array([[0, 10], [10, 0]], dtype=float),
            partial_route=[0]
        )
        
        result = executor.execute(candidate, context)
        
        assert not result.is_success
        assert result.status == "invalid_output"
        assert "not finite" in result.error
    
    def test_execute_infinity_score(self):
        """Executor should reject infinity scores."""
        code = """
def score_candidates(context):
    return {"scores": {1: float('inf')}}
"""
        candidate = CandidateHeuristic(source_code=code)
        executor = HeuristicExecutor(timeout=5.0)
        
        context = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=np.array([[0, 10], [10, 0]], dtype=float),
            partial_route=[0]
        )
        
        result = executor.execute(candidate, context)
        
        assert not result.is_success
        assert result.status == "invalid_output"
        assert "not finite" in result.error


class TestCandidateAdapter:
    """Test adapter for integrating candidates with harness."""
    
    def test_adapter_validate_and_create(self):
        """Adapter should validate and create callable."""
        candidate = CandidateHeuristic(source_code=VALID_NEAREST_DISTANCE)
        adapter = CandidateAdapter(candidate)
        
        validation = adapter.validate()
        assert validation.is_valid
        
        callable_func = adapter.create_callable()
        assert callable(callable_func)
    
    def test_adapter_reject_without_validation(self):
        """Adapter should reject creating callable without validation."""
        candidate = CandidateHeuristic(source_code=VALID_NEAREST_DISTANCE)
        adapter = CandidateAdapter(candidate)
        
        with pytest.raises(ValueError, match="must be validated"):
            adapter.create_callable()
    
    def test_adapter_with_harness(self):
        """Adapter output should work with RouteHarness."""
        candidate = CandidateHeuristic(source_code=VALID_NEAREST_DISTANCE)
        adapter = CandidateAdapter(candidate)
        
        validation = adapter.validate()
        assert validation.is_valid
        
        # Create instance
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=5)
        locations = instance.get_all_locations()
        dist_matrix = compute_distance_matrix(locations)
        
        # Use with harness
        harness = RouteHarness()
        result = harness.build_route(
            heuristic=adapter.create_callable(),
            distance_matrix=dist_matrix,
            n_stops=5,
            algorithm_name="Candidate Heuristic"
        )
        
        assert result.route[0] == 0
        assert result.route[-1] == 0
        assert len(result.route) == 7  # [0, ..., ..., ..., ..., ..., 0]


class TestCreateScoringFunction:
    """Test convenience function for creating scoring functions."""
    
    def test_create_from_valid_code(self):
        """create_scoring_function should work with valid code."""
        scorer = create_scoring_function(VALID_NEAREST_DISTANCE)
        assert callable(scorer)
    
    def test_create_rejects_invalid_code(self):
        """create_scoring_function should reject invalid code."""
        code = "import os\ndef score_candidates(ctx): pass"
        
        with pytest.raises(ValueError, match="Validation failed"):
            create_scoring_function(code)
    
    def test_create_with_custom_timeout(self):
        """create_scoring_function should accept custom timeout."""
        scorer = create_scoring_function(VALID_NEAREST_DISTANCE, timeout=10.0)
        assert callable(scorer)
    
    def test_create_and_use_with_harness(self):
        """Created scorer should work with harness."""
        scorer = create_scoring_function(VALID_COMPLEX_LOGIC)
        
        gen = InstanceGenerator(seed=99)
        instance = gen.generate(n_stops=8)
        locations = instance.get_all_locations()
        dist_matrix = compute_distance_matrix(locations)
        
        harness = RouteHarness()
        result = harness.build_route(
            heuristic=scorer,
            distance_matrix=dist_matrix,
            n_stops=8
        )
        
        assert result.route[0] == 0
        assert result.route[-1] == 0
        assert len(set(result.route[1:-1])) == 8  # All stops visited


class TestIntegrationWithBaseline:
    """Test that sandbox doesn't break existing functionality."""
    
    def test_builtin_heuristic_still_works(self):
        """Built-in nearest_distance_heuristic should still work."""
        from engine.heuristics import nearest_distance_heuristic
        from engine.baselines import nearest_neighbor
        
        gen = InstanceGenerator(seed=777)
        instance = gen.generate(n_stops=10)
        locations = instance.get_all_locations()
        dist_matrix = compute_distance_matrix(locations)
        
        # Baseline
        nn_result = nearest_neighbor(dist_matrix)
        
        # Harness with built-in
        harness = RouteHarness()
        harness_result = harness.build_route(
            heuristic=nearest_distance_heuristic,
            distance_matrix=dist_matrix,
            n_stops=10
        )
        
        # Should match
        assert harness_result.route == nn_result.route
        assert abs(harness_result.total_distance - nn_result.total_distance) < 1e-10
