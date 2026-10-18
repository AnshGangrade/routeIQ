"""
Unit tests for the heuristic scoring system.

Tests verify:
- HeuristicContext and HeuristicResult models
- Validation of scores (finite, correct count, etc.)
- RouteHarness route construction
- Built-in nearest_distance_heuristic
- Edge cases (zero stops, single stop, etc.)
- Error handling for invalid heuristic outputs
"""

import numpy as np
import pytest
from engine.heuristics import (
    HeuristicContext,
    HeuristicResult,
    ScoringHeuristic,
    RouteHarness,
    nearest_distance_heuristic
)
from engine.instances import compute_distance_matrix, Point, InstanceGenerator
from engine.baselines import nearest_neighbor


class TestHeuristicContext:
    """Test the HeuristicContext model."""
    
    def test_context_creation(self):
        """HeuristicContext should store context data."""
        dist_matrix = np.array([[0, 10], [10, 0]], dtype=float)
        ctx = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=dist_matrix,
            partial_route=[0]
        )
        
        assert ctx.current_location == 0
        assert ctx.candidate_stops == [1]
        assert np.array_equal(ctx.distance_matrix, dist_matrix)
        assert ctx.partial_route == [0]
    
    def test_context_validates_partial_route_starts_with_depot(self):
        """Partial route must start with depot (0)."""
        dist_matrix = np.array([[0, 10], [10, 0]], dtype=float)
        
        with pytest.raises(ValueError, match="start with depot"):
            HeuristicContext(
                current_location=1,
                candidate_stops=[2],
                distance_matrix=dist_matrix,
                partial_route=[1]  # Should start with 0
            )
    
    def test_context_validates_empty_partial_route(self):
        """Partial route cannot be empty."""
        dist_matrix = np.array([[0, 10], [10, 0]], dtype=float)
        
        with pytest.raises(ValueError, match="cannot be empty"):
            HeuristicContext(
                current_location=0,
                candidate_stops=[1],
                distance_matrix=dist_matrix,
                partial_route=[]
            )
    
    def test_context_validates_candidate_stops(self):
        """Candidate stops must be positive integers."""
        dist_matrix = np.array([[0, 10], [10, 0]], dtype=float)
        
        with pytest.raises(ValueError, match="positive integers"):
            HeuristicContext(
                current_location=0,
                candidate_stops=[0],  # Depot not allowed as candidate
                distance_matrix=dist_matrix,
                partial_route=[0]
            )
    
    def test_context_validates_unique_candidates(self):
        """Candidate stops must be unique."""
        dist_matrix = np.array([[0, 10, 20], [10, 0, 5], [20, 5, 0]], dtype=float)
        
        with pytest.raises(ValueError, match="unique"):
            HeuristicContext(
                current_location=0,
                candidate_stops=[1, 1, 2],  # Duplicate
                distance_matrix=dist_matrix,
                partial_route=[0]
            )


class TestHeuristicResult:
    """Test the HeuristicResult model."""
    
    def test_result_creation(self):
        """HeuristicResult should store scores."""
        result = HeuristicResult(scores={1: 10.0, 2: 20.0, 3: 30.0})
        assert result.scores == {1: 10.0, 2: 20.0, 3: 30.0}
    
    def test_result_rejects_nan(self):
        """Scores cannot be NaN."""
        with pytest.raises(ValueError, match="finite"):
            HeuristicResult(scores={1: float('nan')})
    
    def test_result_rejects_infinity(self):
        """Scores cannot be infinite."""
        with pytest.raises(ValueError, match="finite"):
            HeuristicResult(scores={1: float('inf')})
        
        with pytest.raises(ValueError, match="finite"):
            HeuristicResult(scores={1: float('-inf')})
    
    def test_result_rejects_nonnumeric(self):
        """Scores must be numeric."""
        with pytest.raises((ValueError, Exception), match="(numeric|valid number|parse)"):
            HeuristicResult(scores={1: "not a number"})
    
    def test_result_rejects_invalid_stop_id(self):
        """Stop IDs must be positive integers."""
        with pytest.raises(ValueError, match="positive integer"):
            HeuristicResult(scores={0: 10.0})  # Depot not allowed
        
        with pytest.raises(ValueError, match="positive integer"):
            HeuristicResult(scores={-1: 10.0})  # Negative not allowed
    
    def test_result_rejects_empty_scores(self):
        """Scores cannot be empty."""
        with pytest.raises(ValueError, match="cannot be empty"):
            HeuristicResult(scores={})
    
    def test_get_best_stop_simple(self):
        """get_best_stop should return stop with lowest score."""
        result = HeuristicResult(scores={1: 30.0, 2: 10.0, 3: 20.0})
        best = result.get_best_stop([1, 2, 3])
        assert best == 2  # Lowest score
    
    def test_get_best_stop_tie_breaking(self):
        """get_best_stop should use lowest index for ties."""
        result = HeuristicResult(scores={1: 10.0, 2: 10.0, 3: 10.0})
        best = result.get_best_stop([1, 2, 3])
        assert best == 1  # Tie broken by lowest index
    
    def test_get_best_stop_validates_score_count(self):
        """get_best_stop should reject score mismatch."""
        result = HeuristicResult(scores={1: 10.0, 2: 20.0})
        
        # Missing score
        with pytest.raises(ValueError, match="missing scores"):
            result.get_best_stop([1, 2, 3])
        
        # Extra score
        with pytest.raises(ValueError, match="unexpected scores"):
            result.get_best_stop([1])


class TestRouteHarness:
    """Test the RouteHarness route builder."""
    
    def test_harness_zero_stops(self):
        """Harness should handle depot-only instance."""
        dist_matrix = np.array([[0.0]])
        harness = RouteHarness()
        
        result = harness.build_route(
            heuristic=nearest_distance_heuristic,
            distance_matrix=dist_matrix,
            n_stops=0
        )
        
        assert result.route == [0, 0]
        assert result.total_distance == 0.0
        assert result.algorithm == "Heuristic"
    
    def test_harness_one_stop(self):
        """Harness should handle single stop."""
        # Depot at (0,0), stop at (3,4), distance = 5
        dist_matrix = np.array([[0.0, 5.0], [5.0, 0.0]])
        harness = RouteHarness()
        
        result = harness.build_route(
            heuristic=nearest_distance_heuristic,
            distance_matrix=dist_matrix,
            n_stops=1
        )
        
        assert result.route == [0, 1, 0]
        assert result.total_distance == 10.0
        assert result.route[0] == 0
        assert result.route[-1] == 0
    
    def test_harness_multiple_stops(self):
        """Harness should construct complete route."""
        # Simple 4-location instance
        locations = [
            Point(x=0, y=0),  # depot
            Point(x=1, y=0),  # stop 1
            Point(x=2, y=0),  # stop 2
            Point(x=3, y=0)   # stop 3
        ]
        dist_matrix = compute_distance_matrix(locations)
        harness = RouteHarness()
        
        result = harness.build_route(
            heuristic=nearest_distance_heuristic,
            distance_matrix=dist_matrix,
            n_stops=3
        )
        
        # Should visit all stops
        visited = set(result.route[1:-1])
        assert visited == {1, 2, 3}
        
        # Should start and end at depot
        assert result.route[0] == 0
        assert result.route[-1] == 0
        
        # Route length should be n_stops + 2 (depot at start and end)
        assert len(result.route) == 5  # [0, 1, 2, 3, 0]
    
    def test_harness_all_stops_visited_once(self):
        """Harness should visit each stop exactly once."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=10)
        locations = instance.get_all_locations()
        dist_matrix = compute_distance_matrix(locations)
        harness = RouteHarness()
        
        result = harness.build_route(
            heuristic=nearest_distance_heuristic,
            distance_matrix=dist_matrix,
            n_stops=10
        )
        
        # Extract stops (excluding depot at start/end)
        visited_stops = result.route[1:-1]
        
        # All stops visited
        assert set(visited_stops) == set(range(1, 11))
        
        # No duplicates
        assert len(visited_stops) == len(set(visited_stops))
    
    def test_harness_custom_algorithm_name(self):
        """Harness should use provided algorithm name."""
        dist_matrix = np.array([[0.0, 5.0], [5.0, 0.0]])
        harness = RouteHarness()
        
        result = harness.build_route(
            heuristic=nearest_distance_heuristic,
            distance_matrix=dist_matrix,
            n_stops=1,
            algorithm_name="Custom Algorithm"
        )
        
        assert result.algorithm == "Custom Algorithm"
    
    def test_harness_validates_distance_matrix_shape(self):
        """Harness should reject non-square matrices."""
        dist_matrix = np.array([[0, 1], [2, 3], [4, 5]])  # 3x2
        harness = RouteHarness()
        
        with pytest.raises(ValueError, match="square"):
            harness.build_route(
                heuristic=nearest_distance_heuristic,
                distance_matrix=dist_matrix,
                n_stops=2
            )
    
    def test_harness_validates_n_stops_matches_matrix(self):
        """Harness should reject mismatched n_stops and matrix size."""
        dist_matrix = np.array([[0, 1], [1, 0]], dtype=float)
        harness = RouteHarness()
        
        with pytest.raises(ValueError, match="doesn't match"):
            harness.build_route(
                heuristic=nearest_distance_heuristic,
                distance_matrix=dist_matrix,
                n_stops=5  # Matrix only has room for 1 stop
            )
    
    def test_harness_validates_negative_n_stops(self):
        """Harness should reject negative n_stops."""
        dist_matrix = np.array([[0]], dtype=float)
        harness = RouteHarness()
        
        with pytest.raises(ValueError, match="cannot be negative"):
            harness.build_route(
                heuristic=nearest_distance_heuristic,
                distance_matrix=dist_matrix,
                n_stops=-1
            )
    
    def test_harness_rejects_wrong_score_count(self):
        """Harness should reject heuristic returning wrong number of scores."""
        def bad_heuristic(ctx: HeuristicContext) -> HeuristicResult:
            # Return too few scores
            if ctx.candidate_stops:
                return HeuristicResult(scores={ctx.candidate_stops[0]: 10.0})
            return HeuristicResult(scores={1: 10.0})
        
        dist_matrix = np.array([
            [0, 1, 2],
            [1, 0, 1],
            [2, 1, 0]
        ], dtype=float)
        harness = RouteHarness()
        
        with pytest.raises(ValueError, match="missing scores"):
            harness.build_route(
                heuristic=bad_heuristic,
                distance_matrix=dist_matrix,
                n_stops=2
            )
    
    def test_harness_rejects_nan_scores(self):
        """Harness should reject heuristic returning NaN."""
        def nan_heuristic(ctx: HeuristicContext) -> HeuristicResult:
            scores = {stop: float('nan') for stop in ctx.candidate_stops}
            return HeuristicResult(scores=scores)
        
        dist_matrix = np.array([[0, 1], [1, 0]], dtype=float)
        harness = RouteHarness()
        
        with pytest.raises(ValueError, match="finite"):
            harness.build_route(
                heuristic=nan_heuristic,
                distance_matrix=dist_matrix,
                n_stops=1
            )
    
    def test_harness_rejects_infinity_scores(self):
        """Harness should reject heuristic returning infinity."""
        def inf_heuristic(ctx: HeuristicContext) -> HeuristicResult:
            scores = {stop: float('inf') for stop in ctx.candidate_stops}
            return HeuristicResult(scores=scores)
        
        dist_matrix = np.array([[0, 1], [1, 0]], dtype=float)
        harness = RouteHarness()
        
        with pytest.raises(ValueError, match="finite"):
            harness.build_route(
                heuristic=inf_heuristic,
                distance_matrix=dist_matrix,
                n_stops=1
            )
    
    def test_harness_rejects_wrong_return_type(self):
        """Harness should reject heuristic not returning HeuristicResult."""
        def bad_heuristic(ctx: HeuristicContext):
            # Return dict instead of HeuristicResult
            return {stop: 10.0 for stop in ctx.candidate_stops}
        
        dist_matrix = np.array([[0, 1], [1, 0]], dtype=float)
        harness = RouteHarness()
        
        with pytest.raises(TypeError, match="HeuristicResult"):
            harness.build_route(
                heuristic=bad_heuristic,
                distance_matrix=dist_matrix,
                n_stops=1
            )
    
    def test_harness_rejects_heuristic_exception(self):
        """Harness should catch and report heuristic exceptions."""
        def crashing_heuristic(ctx: HeuristicContext) -> HeuristicResult:
            raise RuntimeError("Heuristic failed!")
        
        dist_matrix = np.array([[0, 1], [1, 0]], dtype=float)
        harness = RouteHarness()
        
        with pytest.raises(ValueError, match="Heuristic raised exception"):
            harness.build_route(
                heuristic=crashing_heuristic,
                distance_matrix=dist_matrix,
                n_stops=1
            )


class TestNearestDistanceHeuristic:
    """Test the built-in nearest_distance_heuristic."""
    
    def test_nearest_distance_scores_by_distance(self):
        """nearest_distance_heuristic should score by distance."""
        dist_matrix = np.array([
            [0, 10, 20, 30],
            [10, 0, 5, 15],
            [20, 5, 0, 10],
            [30, 15, 10, 0]
        ], dtype=float)
        
        ctx = HeuristicContext(
            current_location=0,
            candidate_stops=[1, 2, 3],
            distance_matrix=dist_matrix,
            partial_route=[0]
        )
        
        result = nearest_distance_heuristic(ctx)
        
        assert result.scores[1] == 10.0
        assert result.scores[2] == 20.0
        assert result.scores[3] == 30.0
    
    def test_nearest_distance_from_non_depot(self):
        """nearest_distance_heuristic should work from any location."""
        dist_matrix = np.array([
            [0, 10, 20, 30],
            [10, 0, 5, 15],
            [20, 5, 0, 10],
            [30, 15, 10, 0]
        ], dtype=float)
        
        ctx = HeuristicContext(
            current_location=1,  # Currently at stop 1
            candidate_stops=[2, 3],
            distance_matrix=dist_matrix,
            partial_route=[0, 1]
        )
        
        result = nearest_distance_heuristic(ctx)
        
        assert result.scores[2] == 5.0   # Distance from stop 1 to stop 2
        assert result.scores[3] == 15.0  # Distance from stop 1 to stop 3
    
    def test_nearest_distance_reproduces_nearest_neighbor(self):
        """Harness + nearest_distance_heuristic should match Nearest Neighbor."""
        # Generate instance
        gen = InstanceGenerator(seed=123)
        instance = gen.generate(n_stops=15)
        locations = instance.get_all_locations()
        dist_matrix = compute_distance_matrix(locations)
        
        # Run Nearest Neighbor baseline
        nn_result = nearest_neighbor(dist_matrix)
        
        # Run harness with nearest_distance_heuristic
        harness = RouteHarness()
        harness_result = harness.build_route(
            heuristic=nearest_distance_heuristic,
            distance_matrix=dist_matrix,
            n_stops=15,
            algorithm_name="Nearest Distance Heuristic"
        )
        
        # Routes should be identical (deterministic tie-breaking)
        assert harness_result.route == nn_result.route
        
        # Distances should match (within floating point precision)
        assert abs(harness_result.total_distance - nn_result.total_distance) < 1e-10


class TestDeterministicTieBreaking:
    """Test deterministic tie-breaking in the harness."""
    
    def test_tie_breaking_prefers_lowest_index(self):
        """When scores are tied, harness should select lowest index."""
        # All candidates have equal distance from depot
        dist_matrix = np.array([
            [0, 5, 5, 5],
            [5, 0, 1, 2],
            [5, 1, 0, 1],
            [5, 2, 1, 0]
        ], dtype=float)
        
        harness = RouteHarness()
        result = harness.build_route(
            heuristic=nearest_distance_heuristic,
            distance_matrix=dist_matrix,
            n_stops=3
        )
        
        # First stop after depot should be stop 1 (lowest index in tie)
        assert result.route[1] == 1
    
    def test_tie_breaking_is_deterministic(self):
        """Tie-breaking should produce same route on repeated runs."""
        dist_matrix = np.array([
            [0, 10, 10, 10, 10],
            [10, 0, 5, 5, 5],
            [10, 5, 0, 5, 5],
            [10, 5, 5, 0, 5],
            [10, 5, 5, 5, 0]
        ], dtype=float)
        
        harness = RouteHarness()
        
        # Run multiple times
        routes = []
        for _ in range(5):
            result = harness.build_route(
                heuristic=nearest_distance_heuristic,
                distance_matrix=dist_matrix,
                n_stops=4
            )
            routes.append(result.route)
        
        # All routes should be identical
        for route in routes[1:]:
            assert route == routes[0]


class TestCustomHeuristics:
    """Test the harness with custom heuristic functions."""
    
    def test_reverse_distance_heuristic(self):
        """Harness should work with custom heuristic (prefer farthest)."""
        def farthest_heuristic(ctx: HeuristicContext) -> HeuristicResult:
            """Prefer farthest stop (higher distance = lower score)."""
            scores = {
                stop: -ctx.distance_matrix[ctx.current_location, stop]
                for stop in ctx.candidate_stops
            }
            return HeuristicResult(scores=scores)
        
        # Line of stops: depot at 0, stops at 1, 2, 3
        locations = [
            Point(x=0, y=0),
            Point(x=1, y=0),
            Point(x=2, y=0),
            Point(x=3, y=0)
        ]
        dist_matrix = compute_distance_matrix(locations)
        
        harness = RouteHarness()
        result = harness.build_route(
            heuristic=farthest_heuristic,
            distance_matrix=dist_matrix,
            n_stops=3
        )
        
        # Should prefer farthest from depot (3), then farthest from 3 (1), then 2
        # 0 -> 3 (farthest from depot)
        # 3 -> 1 (farthest from 3: dist(3,1)=2 > dist(3,2)=1)
        # 1 -> 2 (only remaining)
        assert result.route == [0, 3, 1, 2, 0]
    
    def test_constant_score_heuristic(self):
        """Harness should handle constant scores (all ties)."""
        def constant_heuristic(ctx: HeuristicContext) -> HeuristicResult:
            """All candidates get same score."""
            scores = {stop: 1.0 for stop in ctx.candidate_stops}
            return HeuristicResult(scores=scores)
        
        dist_matrix = np.array([
            [0, 1, 2, 3],
            [1, 0, 1, 2],
            [2, 1, 0, 1],
            [3, 2, 1, 0]
        ], dtype=float)
        
        harness = RouteHarness()
        result = harness.build_route(
            heuristic=constant_heuristic,
            distance_matrix=dist_matrix,
            n_stops=3
        )
        
        # With all ties, should select by lowest index: 0 -> 1 -> 2 -> 3 -> 0
        assert result.route == [0, 1, 2, 3, 0]
    
    def test_hand_crafted_route(self):
        """Harness should follow specific scoring pattern."""
        # This heuristic creates a specific route by hand
        def specific_route_heuristic(ctx: HeuristicContext) -> HeuristicResult:
            """Create route 0 -> 2 -> 1 -> 3 -> 0."""
            # Priority order: 2 first, then 1, then 3
            priority = {1: 2, 2: 1, 3: 3}
            scores = {
                stop: priority.get(stop, 999)
                for stop in ctx.candidate_stops
            }
            return HeuristicResult(scores=scores)
        
        dist_matrix = np.array([
            [0, 1, 2, 3],
            [1, 0, 1, 2],
            [2, 1, 0, 1],
            [3, 2, 1, 0]
        ], dtype=float)
        
        harness = RouteHarness()
        result = harness.build_route(
            heuristic=specific_route_heuristic,
            distance_matrix=dist_matrix,
            n_stops=3
        )
        
        assert result.route == [0, 2, 1, 3, 0]
