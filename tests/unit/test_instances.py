"""
Unit tests for instance generation and distance calculations.
"""

import pytest
import numpy as np
from engine.instances import (
    InstanceGenerator,
    DeliveryInstance,
    Stop,
    Point,
    euclidean_distance,
    compute_distance_matrix,
    calculate_route_cost,
)
from engine.instances.distance import validate_route


class TestPoint:
    """Tests for Point model."""
    
    def test_point_creation(self):
        """Point can be created with coordinates."""
        p = Point(x=3.5, y=4.5)
        assert p.x == 3.5
        assert p.y == 4.5
    
    def test_point_to_tuple(self):
        """Point converts to tuple correctly."""
        p = Point(x=1.0, y=2.0)
        assert p.to_tuple() == (1.0, 2.0)


class TestEuclideanDistance:
    """Tests for Euclidean distance calculation."""
    
    def test_distance_same_point(self):
        """Distance from point to itself is zero."""
        p = Point(x=5, y=10)
        dist = euclidean_distance(p, p)
        assert dist == 0.0
    
    def test_distance_known_values(self):
        """Distance calculation matches hand-calculated values."""
        # Classic 3-4-5 right triangle
        p1 = Point(x=0, y=0)
        p2 = Point(x=3, y=4)
        dist = euclidean_distance(p1, p2)
        assert abs(dist - 5.0) < 1e-10
    
    def test_distance_symmetric(self):
        """Distance is symmetric: d(A, B) == d(B, A)."""
        p1 = Point(x=1, y=2)
        p2 = Point(x=4, y=6)
        assert euclidean_distance(p1, p2) == euclidean_distance(p2, p1)
    
    def test_distance_negative_coordinates(self):
        """Distance works with negative coordinates."""
        p1 = Point(x=-3, y=-4)
        p2 = Point(x=0, y=0)
        dist = euclidean_distance(p1, p2)
        assert abs(dist - 5.0) < 1e-10
    
    def test_distance_horizontal(self):
        """Distance along horizontal line."""
        p1 = Point(x=0, y=5)
        p2 = Point(x=10, y=5)
        assert euclidean_distance(p1, p2) == 10.0
    
    def test_distance_vertical(self):
        """Distance along vertical line."""
        p1 = Point(x=5, y=0)
        p2 = Point(x=5, y=8)
        assert euclidean_distance(p1, p2) == 8.0


class TestDistanceMatrix:
    """Tests for distance matrix computation."""
    
    def test_single_location(self):
        """Distance matrix for single location is 1x1 with zero."""
        depot = Point(x=0, y=0)
        matrix = compute_distance_matrix([depot])
        
        assert matrix.shape == (1, 1)
        assert matrix[0, 0] == 0.0
    
    def test_two_locations(self):
        """Distance matrix for two locations."""
        depot = Point(x=0, y=0)
        stop1 = Point(x=3, y=4)
        matrix = compute_distance_matrix([depot, stop1])
        
        assert matrix.shape == (2, 2)
        assert matrix[0, 0] == 0.0  # depot to itself
        assert matrix[1, 1] == 0.0  # stop to itself
        assert abs(matrix[0, 1] - 5.0) < 1e-10  # depot to stop
        assert abs(matrix[1, 0] - 5.0) < 1e-10  # stop to depot
    
    def test_matrix_symmetry(self):
        """Distance matrix is symmetric."""
        locations = [
            Point(x=0, y=0),
            Point(x=1, y=1),
            Point(x=2, y=2),
            Point(x=3, y=3),
        ]
        matrix = compute_distance_matrix(locations)
        
        n = len(locations)
        for i in range(n):
            for j in range(n):
                assert matrix[i, j] == matrix[j, i]
    
    def test_matrix_diagonal_zero(self):
        """Distance matrix diagonal is all zeros."""
        locations = [Point(x=i*10, y=i*10) for i in range(5)]
        matrix = compute_distance_matrix(locations)
        
        for i in range(len(locations)):
            assert matrix[i, i] == 0.0
    
    def test_empty_locations_raises_error(self):
        """Empty locations list raises ValueError."""
        with pytest.raises(ValueError, match="empty locations"):
            compute_distance_matrix([])
    
    def test_matrix_shape_correct(self):
        """Distance matrix has correct shape NxN."""
        n = 10
        locations = [Point(x=i, y=i*2) for i in range(n)]
        matrix = compute_distance_matrix(locations)
        
        assert matrix.shape == (n, n)
        assert isinstance(matrix, np.ndarray)


class TestRouteCost:
    """Tests for route cost calculation."""
    
    def test_single_stop_round_trip(self):
        """Cost for depot -> stop -> depot."""
        # depot at (0,0), stop at (3,4), distance = 5
        matrix = np.array([
            [0, 5],
            [5, 0]
        ])
        route = [0, 1, 0]
        cost = calculate_route_cost(route, matrix)
        assert cost == 10.0  # 5 + 5
    
    def test_multiple_stops(self):
        """Cost for route with multiple stops."""
        # Simple square: (0,0), (10,0), (10,10), (0,10)
        matrix = np.array([
            [0,  10, 14.142, 10],
            [10,  0, 10, 14.142],
            [14.142, 10,  0, 10],
            [10, 14.142, 10,  0]
        ])
        route = [0, 1, 2, 3, 0]
        cost = calculate_route_cost(route, matrix)
        # 10 + 10 + 10 + 10 = 40
        assert abs(cost - 40.0) < 0.01
    
    def test_auto_return_to_depot(self):
        """Automatically adds return to depot if not present."""
        matrix = np.array([
            [0, 5, 10],
            [5, 0, 7],
            [10, 7, 0]
        ])
        route = [0, 1, 2]  # Missing return to depot
        cost = calculate_route_cost(route, matrix, return_to_depot=True)
        # 0->1: 5, 1->2: 7, 2->0: 10 = 22
        assert cost == 22.0
    
    def test_no_auto_return(self):
        """Does not add return to depot when disabled."""
        matrix = np.array([
            [0, 5, 10],
            [5, 0, 7],
            [10, 7, 0]
        ])
        route = [0, 1, 2]
        cost = calculate_route_cost(route, matrix, return_to_depot=False)
        # 0->1: 5, 1->2: 7 = 12 (no return)
        assert cost == 12.0
    
    def test_empty_route_raises_error(self):
        """Empty route raises ValueError."""
        matrix = np.array([[0, 5], [5, 0]])
        with pytest.raises(ValueError, match="at least one stop"):
            calculate_route_cost([], matrix)
    
    def test_invalid_index_raises_error(self):
        """Route with out-of-bounds index raises ValueError."""
        matrix = np.array([[0, 5], [5, 0]])
        route = [0, 5, 0]  # Index 5 doesn't exist
        with pytest.raises(ValueError, match="out of bounds"):
            calculate_route_cost(route, matrix)
    
    def test_negative_index_raises_error(self):
        """Negative index raises ValueError."""
        matrix = np.array([[0, 5], [5, 0]])
        route = [0, -1, 0]
        with pytest.raises(ValueError, match="out of bounds"):
            calculate_route_cost(route, matrix)
    
    def test_non_integer_index_raises_error(self):
        """Non-integer index raises ValueError."""
        matrix = np.array([[0, 5], [5, 0]])
        route = [0, 1.5, 0]
        with pytest.raises(ValueError, match="must be integers"):
            calculate_route_cost(route, matrix)


class TestRouteValidation:
    """Tests for route validation."""
    
    def test_valid_route(self):
        """Valid route passes all checks."""
        route = [0, 1, 2, 3, 0]
        validate_route(route, n_stops=3)  # Should not raise
    
    def test_missing_depot_start(self):
        """Route not starting at depot raises error."""
        route = [1, 2, 0]
        with pytest.raises(ValueError, match="must start at depot"):
            validate_route(route, n_stops=2, require_depot_start=True)
    
    def test_missing_depot_end(self):
        """Route not ending at depot raises error."""
        route = [0, 1, 2]
        with pytest.raises(ValueError, match="must end at depot"):
            validate_route(route, n_stops=2, require_depot_end=True)
    
    def test_missing_stop(self):
        """Route missing a stop raises error."""
        route = [0, 1, 0]  # Missing stop 2
        with pytest.raises(ValueError, match="missing stops"):
            validate_route(route, n_stops=2, require_all_stops=True)
    
    def test_duplicate_stop(self):
        """Route with duplicate stop raises error."""
        route = [0, 1, 1, 2, 0]
        with pytest.raises(ValueError, match="duplicate"):
            validate_route(route, n_stops=2, require_all_stops=True)
    
    def test_empty_route(self):
        """Empty route raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_route([], n_stops=0)


class TestInstanceGenerator:
    """Tests for InstanceGenerator."""
    
    def test_generator_creation(self):
        """Generator can be created with default parameters."""
        gen = InstanceGenerator()
        assert gen.seed is None
        assert gen.x_range == (0.0, 100.0)
        assert gen.y_range == (0.0, 100.0)
    
    def test_generator_with_seed(self):
        """Generator stores provided seed."""
        gen = InstanceGenerator(seed=42)
        assert gen.seed == 42
    
    def test_invalid_x_range_raises_error(self):
        """Invalid x_range raises ValueError."""
        with pytest.raises(ValueError, match="Invalid x_range"):
            InstanceGenerator(x_range=(100, 0))
    
    def test_invalid_y_range_raises_error(self):
        """Invalid y_range raises ValueError."""
        with pytest.raises(ValueError, match="Invalid y_range"):
            InstanceGenerator(y_range=(50, 50))


class TestInstanceGeneration:
    """Tests for instance generation."""
    
    def test_generate_zero_stops(self):
        """Can generate instance with zero stops."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=0)
        
        assert instance.n_stops == 0
        assert len(instance.stops) == 0
        assert instance.depot.id == 0
    
    def test_generate_one_stop(self):
        """Can generate instance with one stop."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=1)
        
        assert instance.n_stops == 1
        assert len(instance.stops) == 1
        assert instance.stops[0].id == 1
    
    def test_generate_multiple_stops(self):
        """Can generate instance with multiple stops."""
        gen = InstanceGenerator(seed=42)
        n = 10
        instance = gen.generate(n_stops=n)
        
        assert instance.n_stops == n
        assert len(instance.stops) == n
        for i, stop in enumerate(instance.stops, start=1):
            assert stop.id == i
    
    def test_same_seed_produces_same_instance(self):
        """Same seed produces identical coordinates."""
        gen1 = InstanceGenerator(seed=42)
        gen2 = InstanceGenerator(seed=42)
        
        instance1 = gen1.generate(n_stops=5)
        instance2 = gen2.generate(n_stops=5)
        
        # Depot should match
        assert instance1.depot.location.x == instance2.depot.location.x
        assert instance1.depot.location.y == instance2.depot.location.y
        
        # All stops should match
        for s1, s2 in zip(instance1.stops, instance2.stops):
            assert s1.location.x == s2.location.x
            assert s1.location.y == s2.location.y
    
    def test_different_seeds_produce_different_instances(self):
        """Different seeds typically produce different coordinates."""
        gen1 = InstanceGenerator(seed=42)
        gen2 = InstanceGenerator(seed=43)
        
        instance1 = gen1.generate(n_stops=5)
        instance2 = gen2.generate(n_stops=5)
        
        # At least one coordinate should differ
        coords1 = [instance1.depot.location.to_tuple()] + [
            s.location.to_tuple() for s in instance1.stops
        ]
        coords2 = [instance2.depot.location.to_tuple()] + [
            s.location.to_tuple() for s in instance2.stops
        ]
        
        assert coords1 != coords2
    
    def test_coordinates_within_bounds(self):
        """Generated coordinates respect configured bounds."""
        x_range = (10.0, 50.0)
        y_range = (20.0, 60.0)
        gen = InstanceGenerator(seed=42, x_range=x_range, y_range=y_range)
        
        instance = gen.generate(n_stops=20)
        
        # Check depot
        assert x_range[0] <= instance.depot.location.x <= x_range[1]
        assert y_range[0] <= instance.depot.location.y <= y_range[1]
        
        # Check all stops
        for stop in instance.stops:
            assert x_range[0] <= stop.location.x <= x_range[1]
            assert y_range[0] <= stop.location.y <= y_range[1]
    
    def test_negative_stops_raises_error(self):
        """Negative n_stops raises ValueError."""
        gen = InstanceGenerator(seed=42)
        with pytest.raises(ValueError, match="non-negative"):
            gen.generate(n_stops=-1)
    
    def test_fixed_depot_location(self):
        """Can specify fixed depot location."""
        depot_loc = Point(x=50, y=50)
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=5, depot_location=depot_loc)
        
        assert instance.depot.location.x == 50
        assert instance.depot.location.y == 50
    
    def test_clustered_distribution(self):
        """Can generate clustered distribution."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=20, distribution="clustered")
        
        assert instance.n_stops == 20
        assert len(instance.stops) == 20
    
    def test_invalid_distribution_raises_error(self):
        """Invalid distribution name raises ValueError."""
        gen = InstanceGenerator(seed=42)
        with pytest.raises(ValueError, match="distribution must be"):
            gen.generate(n_stops=5, distribution="invalid")


class TestInstanceModel:
    """Tests for DeliveryInstance model."""
    
    def test_get_all_locations(self):
        """get_all_locations returns depot first, then stops."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=3)
        
        locations = instance.get_all_locations()
        assert len(locations) == 4  # depot + 3 stops
        assert locations[0] == instance.depot.location
        assert locations[1] == instance.stops[0].location
        assert locations[2] == instance.stops[1].location
        assert locations[3] == instance.stops[2].location
    
    def test_get_stop_by_id_depot(self):
        """get_stop_by_id(0) returns depot."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=2)
        
        stop = instance.get_stop_by_id(0)
        assert stop.id == 0
        assert stop == instance.depot
    
    def test_get_stop_by_id_valid(self):
        """get_stop_by_id returns correct stop for valid ID."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=3)
        
        stop2 = instance.get_stop_by_id(2)
        assert stop2.id == 2
        assert stop2 == instance.stops[1]
    
    def test_get_stop_by_id_invalid(self):
        """get_stop_by_id raises IndexError for invalid ID."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=2)
        
        with pytest.raises(IndexError, match="Invalid stop_id"):
            instance.get_stop_by_id(5)
    
    def test_depot_must_have_id_zero(self):
        """Depot with non-zero ID raises validation error."""
        with pytest.raises(ValueError, match="Depot must have id=0"):
            DeliveryInstance(
                seed=42,
                depot=Stop(id=1, location=Point(x=0, y=0)),
                stops=[],
                n_stops=0
            )
    
    def test_stops_must_have_sequential_ids(self):
        """Stops with non-sequential IDs raise validation error."""
        depot = Stop(id=0, location=Point(x=0, y=0))
        stops = [
            Stop(id=1, location=Point(x=1, y=1)),
            Stop(id=3, location=Point(x=2, y=2)),  # Should be 2
        ]
        
        with pytest.raises(ValueError, match="must have id=2"):
            DeliveryInstance(seed=42, depot=depot, stops=stops, n_stops=2)


class TestBatchGeneration:
    """Tests for batch instance generation."""
    
    def test_generate_batch(self):
        """Can generate multiple instances."""
        gen = InstanceGenerator()
        instances = gen.generate_batch(
            n_instances=5,
            n_stops=10,
            start_seed=100
        )
        
        assert len(instances) == 5
        for instance in instances:
            assert instance.n_stops == 10
    
    def test_batch_has_sequential_seeds(self):
        """Batch instances have sequential seeds."""
        gen = InstanceGenerator()
        instances = gen.generate_batch(
            n_instances=3,
            n_stops=5,
            start_seed=50
        )
        
        assert instances[0].seed == 50
        assert instances[1].seed == 51
        assert instances[2].seed == 52
    
    def test_batch_instances_are_different(self):
        """Batch instances have different coordinates."""
        gen = InstanceGenerator()
        instances = gen.generate_batch(
            n_instances=3,
            n_stops=5,
            start_seed=100
        )
        
        # Check that at least depot locations differ
        depot_coords = [inst.depot.location.to_tuple() for inst in instances]
        assert len(set(depot_coords)) > 1  # At least some should differ


class TestIntegration:
    """Integration tests combining generation and distance calculations."""
    
    def test_end_to_end_simple_instance(self):
        """Complete workflow: generate, compute distances, calculate route cost."""
        # Generate small instance
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=3)
        
        # Compute distance matrix
        locations = instance.get_all_locations()
        dist_matrix = compute_distance_matrix(locations)
        
        # Create a simple route
        route = [0, 1, 2, 3, 0]
        cost = calculate_route_cost(route, dist_matrix)
        
        # Cost should be positive
        assert cost > 0
        
        # Should match sum of individual legs
        expected = (
            dist_matrix[0, 1] +
            dist_matrix[1, 2] +
            dist_matrix[2, 3] +
            dist_matrix[3, 0]
        )
        assert abs(cost - expected) < 1e-10
    
    def test_distance_matrix_size_matches_instance(self):
        """Distance matrix size matches instance (depot + stops)."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=10)
        
        locations = instance.get_all_locations()
        matrix = compute_distance_matrix(locations)
        
        expected_size = 1 + instance.n_stops  # depot + stops
        assert matrix.shape == (expected_size, expected_size)
    
    def test_zero_stops_workflow(self):
        """Workflow works with zero stops (depot only)."""
        gen = InstanceGenerator(seed=42)
        instance = gen.generate(n_stops=0)
        
        locations = instance.get_all_locations()
        assert len(locations) == 1
        
        matrix = compute_distance_matrix(locations)
        assert matrix.shape == (1, 1)
        assert matrix[0, 0] == 0.0
