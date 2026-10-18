"""
Unit tests for baseline routing algorithms (Nearest Neighbor and 2-Opt).

Tests verify:
- Empty and single-stop edge cases
- All stops visited exactly once
- Routes start and end at depot
- NN produces expected routes for hand-calculated examples
- 2-Opt preserves validity and never increases distance
- Known crossing routes improved by 2-Opt
- Deterministic tie-breaking
- Invalid inputs rejected
"""

import numpy as np
import pytest
from engine.baselines import (
    nearest_neighbor,
    two_opt,
    nearest_neighbor_with_2opt,
    RouteResult
)
from engine.instances import compute_distance_matrix, Point


def make_distance_matrix_from_coords(coords: np.ndarray) -> np.ndarray:
    """Helper to convert numpy coordinate array to distance matrix via Point objects."""
    points = [Point(x=float(coord[0]), y=float(coord[1])) for coord in coords]
    return compute_distance_matrix(points)


class TestRouteResult:
    """Test the RouteResult model."""
    
    def test_route_result_creation(self):
        """RouteResult should store route, distance, and algorithm name."""
        result = RouteResult(
            route=[0, 1, 2, 0],
            total_distance=10.5,
            algorithm="test"
        )
        assert result.route == [0, 1, 2, 0]
        assert result.total_distance == 10.5
        assert result.algorithm == "test"
    
    def test_route_result_validation(self):
        """RouteResult should validate types."""
        with pytest.raises(Exception):  # Pydantic validation error
            RouteResult(
                route="not a list",
                total_distance=10.5,
                algorithm="test"
            )


class TestNearestNeighbor:
    """Test Nearest Neighbor construction algorithm."""
    
    def test_empty_distance_matrix(self):
        """NN should reject empty distance matrix."""
        dist_matrix = np.array([])
        with pytest.raises(ValueError, match="at least the depot"):
            nearest_neighbor(dist_matrix)
    
    def test_single_stop_only_depot(self):
        """NN with only depot (1x1 matrix) should return depot-only route."""
        dist_matrix = np.array([[0.0]])
        result = nearest_neighbor(dist_matrix)
        
        assert result.route == [0, 0]
        assert result.total_distance == 0.0
        assert result.algorithm == "Nearest Neighbor"
    
    def test_depot_plus_one_stop(self):
        """NN with depot + 1 stop should visit that stop."""
        # Depot at origin, stop at (3, 4), distance = 5
        dist_matrix = np.array([
            [0.0, 5.0],
            [5.0, 0.0]
        ])
        result = nearest_neighbor(dist_matrix)
        
        assert result.route == [0, 1, 0]
        assert result.total_distance == 10.0  # 5 + 5
        assert result.algorithm == "Nearest Neighbor"
    
    def test_three_stops_simple(self):
        """NN should visit all stops exactly once."""
        # Create a simple triangle: depot + 2 stops
        locations = np.array([
            [0.0, 0.0],  # depot
            [1.0, 0.0],  # stop 1
            [0.0, 1.0]   # stop 2
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        result = nearest_neighbor(dist_matrix)
        
        # Route should start and end at depot
        assert result.route[0] == 0
        assert result.route[-1] == 0
        
        # Should visit all stops exactly once
        visited_stops = set(result.route[1:-1])
        assert visited_stops == {1, 2}
        assert len(result.route) == 4  # [0, ..., ..., 0]
        
        # Distance should be positive
        assert result.total_distance > 0
    
    def test_deterministic_tie_breaking(self):
        """NN should use lowest index when distances are equal."""
        # Create scenario where stop 1 and stop 2 are equidistant from depot
        # Both at distance 5 from depot
        dist_matrix = np.array([
            [0.0, 5.0, 5.0, 10.0],  # depot to all
            [5.0, 0.0, 8.0, 6.0],   # stop 1
            [5.0, 8.0, 0.0, 6.0],   # stop 2
            [10.0, 6.0, 6.0, 0.0]   # stop 3
        ])
        
        result = nearest_neighbor(dist_matrix)
        
        # First stop after depot should be stop 1 (lower index) due to tie
        assert result.route[1] == 1
        
        # Run multiple times to verify determinism
        for _ in range(5):
            result2 = nearest_neighbor(dist_matrix)
            assert result2.route == result.route
    
    def test_hand_calculated_example(self):
        """NN should produce expected route for hand-calculated example."""
        # Simple layout: depot at origin, stops forming a line
        # Depot(0,0) -> Stop1(1,0) -> Stop2(2,0) -> Stop3(3,0)
        # Nearest neighbor should follow the line
        locations = np.array([
            [0.0, 0.0],  # depot
            [1.0, 0.0],  # stop 1
            [2.0, 0.0],  # stop 2
            [3.0, 0.0]   # stop 3
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        result = nearest_neighbor(dist_matrix)
        
        # Expected route: 0 -> 1 -> 2 -> 3 -> 0
        assert result.route == [0, 1, 2, 3, 0]
        
        # Expected distance: 1 + 1 + 1 + 3 = 6
        assert abs(result.total_distance - 6.0) < 1e-10
    
    def test_all_stops_visited(self):
        """NN should visit every stop exactly once."""
        # Create random-ish distance matrix
        n_stops = 10
        np.random.seed(42)
        locations = np.random.rand(n_stops, 2) * 100
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        result = nearest_neighbor(dist_matrix)
        
        # Extract stops (excluding start and end depot)
        visited_stops = result.route[1:-1]
        
        # Should visit all stops 1..n_stops-1 exactly once
        assert len(visited_stops) == n_stops - 1
        assert set(visited_stops) == set(range(1, n_stops))
        assert len(visited_stops) == len(set(visited_stops))  # no duplicates
    
    def test_route_starts_and_ends_at_depot(self):
        """NN route must start and end at depot (index 0)."""
        locations = np.array([
            [0.0, 0.0],
            [5.0, 5.0],
            [10.0, 10.0]
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        result = nearest_neighbor(dist_matrix)
        
        assert result.route[0] == 0
        assert result.route[-1] == 0
    
    def test_invalid_distance_matrix_shape(self):
        """NN should reject non-square distance matrix."""
        dist_matrix = np.array([[1, 2], [3, 4], [5, 6]])  # 3x2, not square
        with pytest.raises(ValueError, match="square"):
            nearest_neighbor(dist_matrix)
    
    def test_negative_distances_rejected(self):
        """NN should reject negative distances."""
        dist_matrix = np.array([
            [0.0, 5.0],
            [-1.0, 0.0]  # negative distance
        ])
        with pytest.raises(ValueError, match="negative"):
            nearest_neighbor(dist_matrix)


class TestTwoOpt:
    """Test 2-Opt local search improvement algorithm."""
    
    def test_two_opt_preserves_depot_endpoints(self):
        """2-Opt should never move depot from start/end positions."""
        # Simple route
        initial_route = [0, 1, 2, 3, 0]
        dist_matrix = np.array([
            [0, 1, 2, 3],
            [1, 0, 1, 2],
            [2, 1, 0, 1],
            [3, 2, 1, 0]
        ], dtype=float)
        
        result = two_opt(initial_route, dist_matrix, max_iterations=100)
        
        assert result.route[0] == 0
        assert result.route[-1] == 0
    
    def test_two_opt_never_increases_distance(self):
        """2-Opt should never increase total distance."""
        from engine.instances import calculate_route_cost
        
        initial_route = [0, 3, 1, 2, 0]
        locations = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [3.0, 0.0]
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        initial_distance = calculate_route_cost(initial_route, dist_matrix, return_to_depot=False)
        result = two_opt(initial_route, dist_matrix, max_iterations=100)
        
        assert result.total_distance <= initial_distance
    
    def test_two_opt_improves_crossing_route(self):
        """2-Opt should fix known crossing route."""
        # Create a route with obvious crossing:
        # Depot(0,0), A(0,10), B(10,10), C(10,0)
        # Bad route: 0 -> A -> C -> B -> 0 (crosses itself)
        # Good route: 0 -> A -> B -> C -> 0 (no crossing)
        locations = np.array([
            [0.0, 0.0],   # depot (0)
            [0.0, 10.0],  # A (1)
            [10.0, 10.0], # B (2)
            [10.0, 0.0]   # C (3)
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        # Bad route with crossing
        bad_route = [0, 1, 3, 2, 0]
        
        result = two_opt(bad_route, dist_matrix, max_iterations=100)
        
        # 2-Opt should fix the crossing
        # Good route: [0, 1, 2, 3, 0]
        assert result.route == [0, 1, 2, 3, 0]
        
        # Distance should be improved
        from engine.instances import calculate_route_cost
        bad_distance = calculate_route_cost(bad_route, dist_matrix, return_to_depot=False)
        assert result.total_distance < bad_distance
    
    def test_two_opt_preserves_all_stops(self):
        """2-Opt should not add or remove stops."""
        initial_route = [0, 1, 2, 3, 4, 0]
        dist_matrix = np.random.rand(5, 5)
        dist_matrix = (dist_matrix + dist_matrix.T) / 2  # symmetric
        np.fill_diagonal(dist_matrix, 0)
        
        result = two_opt(initial_route, dist_matrix, max_iterations=10)
        
        # Same stops, possibly different order
        assert len(result.route) == len(initial_route)
        assert set(result.route) == set(initial_route)
    
    def test_two_opt_already_optimal(self):
        """2-Opt on optimal route should return same route."""
        # Optimal route for stops in a line
        optimal_route = [0, 1, 2, 3, 0]
        locations = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [2.0, 0.0],
            [3.0, 0.0]
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        result = two_opt(optimal_route, dist_matrix, max_iterations=100)
        
        # Should return same route (already optimal)
        assert result.route == optimal_route
    
    def test_two_opt_max_iterations(self):
        """2-Opt should respect max_iterations parameter."""
        initial_route = [0, 3, 1, 2, 0]
        dist_matrix = np.random.rand(4, 4)
        dist_matrix = (dist_matrix + dist_matrix.T) / 2
        np.fill_diagonal(dist_matrix, 0)
        
        # Should complete without error even with limited iterations
        result = two_opt(initial_route, dist_matrix, max_iterations=1)
        assert result.route is not None
        assert result.algorithm == "2-Opt"
    
    def test_two_opt_single_stop(self):
        """2-Opt with single stop should return unchanged."""
        initial_route = [0, 1, 0]
        dist_matrix = np.array([
            [0.0, 5.0],
            [5.0, 0.0]
        ])
        
        result = two_opt(initial_route, dist_matrix, max_iterations=10)
        
        assert result.route == [0, 1, 0]
        assert result.total_distance == 10.0
    
    def test_two_opt_invalid_route(self):
        """2-Opt should reject invalid routes."""
        dist_matrix = np.array([
            [0, 1, 2],
            [1, 0, 1],
            [2, 1, 0]
        ], dtype=float)
        
        # Route doesn't start with depot
        with pytest.raises(ValueError, match="start and end at depot"):
            two_opt([1, 2, 0], dist_matrix, max_iterations=10)
        
        # Route doesn't end with depot
        with pytest.raises(ValueError, match="start and end at depot"):
            two_opt([0, 1, 2], dist_matrix, max_iterations=10)


class TestNearestNeighborWith2Opt:
    """Test combined NN + 2-Opt algorithm."""
    
    def test_combined_algorithm_runs(self):
        """NN + 2-Opt should complete successfully."""
        locations = np.array([
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0]
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        result = nearest_neighbor_with_2opt(dist_matrix, max_2opt_iterations=100)
        
        assert result.route[0] == 0
        assert result.route[-1] == 0
        assert result.total_distance > 0
        assert result.algorithm == "Nearest Neighbor + 2-Opt"
    
    def test_combined_better_than_nn_alone(self):
        """NN + 2-Opt should be at least as good as NN alone."""
        # Create crossing route scenario
        locations = np.array([
            [0.0, 0.0],
            [0.0, 10.0],
            [10.0, 10.0],
            [10.0, 0.0]
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        nn_result = nearest_neighbor(dist_matrix)
        combined_result = nearest_neighbor_with_2opt(dist_matrix, max_2opt_iterations=100)
        
        # Combined should be at least as good as NN alone
        assert combined_result.total_distance <= nn_result.total_distance
    
    def test_combined_all_stops_visited(self):
        """NN + 2-Opt should visit all stops exactly once."""
        n_stops = 8
        np.random.seed(123)
        locations = np.random.rand(n_stops, 2) * 100
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        result = nearest_neighbor_with_2opt(dist_matrix, max_2opt_iterations=50)
        
        visited_stops = result.route[1:-1]
        assert len(visited_stops) == n_stops - 1
        assert set(visited_stops) == set(range(1, n_stops))


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_very_large_instance(self):
        """Algorithms should handle moderately large instances."""
        n_stops = 50
        np.random.seed(999)
        locations = np.random.rand(n_stops, 2) * 1000
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        # Should complete in reasonable time
        result = nearest_neighbor(dist_matrix)
        assert len(result.route) == n_stops + 1
        
        result_2opt = nearest_neighbor_with_2opt(dist_matrix, max_2opt_iterations=100)
        assert len(result_2opt.route) == n_stops + 1
    
    def test_collinear_stops(self):
        """Algorithms should handle collinear stops."""
        # All stops on a line
        locations = np.array([
            [i, 0.0] for i in range(10)
        ])
        dist_matrix = make_distance_matrix_from_coords(locations)
        
        result = nearest_neighbor(dist_matrix)
        assert result.route[0] == 0
        assert result.route[-1] == 0
        assert len(set(result.route[1:-1])) == 9  # all stops visited
    
    def test_symmetric_distance_matrix(self):
        """Algorithms should work with symmetric distances."""
        dist_matrix = np.array([
            [0, 1, 2, 3],
            [1, 0, 1, 2],
            [2, 1, 0, 1],
            [3, 2, 1, 0]
        ], dtype=float)
        
        result = nearest_neighbor(dist_matrix)
        assert result.route is not None
        
        result_2opt = two_opt([0, 1, 2, 3, 0], dist_matrix, max_iterations=10)
        assert result_2opt.route is not None
