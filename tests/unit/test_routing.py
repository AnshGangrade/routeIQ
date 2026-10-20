"""Unit tests for multi-driver routing."""

import pytest
import numpy as np
from engine.routing import (
    DriverAssignment,
    DriverRoute,
    FleetResult,
    assign_stops_by_sweep,
    FleetRouter,
)
from engine.routing.assignment import validate_assignment
from engine.instances import InstanceGenerator, Point
from engine.instances.models import DeliveryInstance, Stop
from engine.heuristics.builtin import nearest_distance_heuristic


@pytest.mark.unit
class TestDriverAssignment:
    """Test driver assignment model."""
    
    def test_create_assignment(self):
        """Test creating a driver assignment."""
        assignment = DriverAssignment(driver_id=0, stop_ids=[1, 2, 3])
        
        assert assignment.driver_id == 0
        assert assignment.stop_ids == [1, 2, 3]
    
    def test_empty_assignment(self):
        """Test empty driver assignment."""
        assignment = DriverAssignment(driver_id=5, stop_ids=[])
        
        assert assignment.driver_id == 5
        assert len(assignment.stop_ids) == 0


@pytest.mark.unit
class TestDriverRoute:
    """Test driver route model."""
    
    def test_create_route(self):
        """Test creating a driver route."""
        route = DriverRoute(
            driver_id=0,
            assigned_stops=[1, 2],
            route=[0, 1, 2, 0],
            distance=150.5,
            algorithm="Test"
        )
        
        assert route.driver_id == 0
        assert route.assigned_stops == [1, 2]
        assert route.route == [0, 1, 2, 0]
        assert route.distance == 150.5


@pytest.mark.unit
class TestFleetResult:
    """Test fleet result model."""
    
    def test_create_fleet_result(self):
        """Test creating a fleet result."""
        driver_routes = [
            DriverRoute(
                driver_id=0,
                assigned_stops=[1, 2],
                route=[0, 1, 2, 0],
                distance=100.0,
                algorithm="Test"
            ),
            DriverRoute(
                driver_id=1,
                assigned_stops=[3, 4],
                route=[0, 3, 4, 0],
                distance=150.0,
                algorithm="Test"
            )
        ]
        
        result = FleetResult(
            driver_routes=driver_routes,
            total_distance=250.0,
            longest_route_distance=150.0,
            num_drivers=2,
            num_stops_assigned=4,
            num_stops_visited=4,
            algorithm="Test"
        )
        
        assert result.total_distance == 250.0
        assert result.longest_route_distance == 150.0
        assert result.num_drivers == 2


@pytest.mark.unit
class TestSweepAssignment:
    """Test sweep-angle assignment strategy."""
    
    def test_zero_stops(self):
        """Test assignment with zero stops."""
        instance = InstanceGenerator(seed=42).generate(n_stops=0)
        assignments = assign_stops_by_sweep(instance, num_drivers=3)
        
        assert len(assignments) == 3
        for assignment in assignments:
            assert len(assignment.stop_ids) == 0
    
    def test_one_stop_one_driver(self):
        """Test single stop, single driver."""
        instance = InstanceGenerator(seed=42).generate(n_stops=1)
        assignments = assign_stops_by_sweep(instance, num_drivers=1)
        
        assert len(assignments) == 1
        assert assignments[0].stop_ids == [1]
    
    def test_more_drivers_than_stops(self):
        """Test case where drivers exceed stops."""
        instance = InstanceGenerator(seed=42).generate(n_stops=2)
        assignments = assign_stops_by_sweep(instance, num_drivers=5)
        
        assert len(assignments) == 5
        
        # Check all stops assigned
        all_stops = []
        for assignment in assignments:
            all_stops.extend(assignment.stop_ids)
        assert sorted(all_stops) == [1, 2]
        
        # Some drivers should have empty assignments
        empty_drivers = sum(1 for a in assignments if len(a.stop_ids) == 0)
        assert empty_drivers == 3
    
    def test_even_distribution(self):
        """Test even distribution of stops."""
        instance = InstanceGenerator(seed=42).generate(n_stops=6)
        assignments = assign_stops_by_sweep(instance, num_drivers=3)
        
        assert len(assignments) == 3
        
        # Each driver should get 2 stops
        for assignment in assignments:
            assert len(assignment.stop_ids) == 2
        
        # All stops should be assigned
        all_stops = []
        for assignment in assignments:
            all_stops.extend(assignment.stop_ids)
        assert sorted(all_stops) == [1, 2, 3, 4, 5, 6]
    
    def test_uneven_distribution(self):
        """Test uneven distribution of stops."""
        instance = InstanceGenerator(seed=42).generate(n_stops=7)
        assignments = assign_stops_by_sweep(instance, num_drivers=3)
        
        # Total stops should match
        total_assigned = sum(len(a.stop_ids) for a in assignments)
        assert total_assigned == 7
        
        # Distribution should be as even as possible
        counts = [len(a.stop_ids) for a in assignments]
        assert min(counts) >= 2
        assert max(counts) <= 3
    
    def test_deterministic_assignment(self):
        """Test that assignment is deterministic."""
        instance = InstanceGenerator(seed=42).generate(n_stops=10)
        
        assignments1 = assign_stops_by_sweep(instance, num_drivers=3)
        assignments2 = assign_stops_by_sweep(instance, num_drivers=3)
        
        for a1, a2 in zip(assignments1, assignments2):
            assert a1.driver_id == a2.driver_id
            assert a1.stop_ids == a2.stop_ids
    
    def test_all_stops_assigned_exactly_once(self):
        """Test that every stop is assigned exactly once."""
        instance = InstanceGenerator(seed=42).generate(n_stops=15)
        assignments = assign_stops_by_sweep(instance, num_drivers=4)
        
        all_stops = []
        for assignment in assignments:
            all_stops.extend(assignment.stop_ids)
        
        # No duplicates
        assert len(all_stops) == len(set(all_stops))
        
        # All stops present
        assert sorted(all_stops) == list(range(1, 16))
    
    def test_invalid_num_drivers(self):
        """Test validation of num_drivers."""
        instance = InstanceGenerator(seed=42).generate(n_stops=5)
        
        with pytest.raises(ValueError, match="num_drivers must be >= 1"):
            assign_stops_by_sweep(instance, num_drivers=0)
        
        with pytest.raises(ValueError):
            assign_stops_by_sweep(instance, num_drivers=-1)


@pytest.mark.unit
class TestAssignmentValidation:
    """Test assignment validation."""
    
    def test_valid_assignment(self):
        """Test validating a correct assignment."""
        assignments = [
            DriverAssignment(driver_id=0, stop_ids=[1, 2]),
            DriverAssignment(driver_id=1, stop_ids=[3, 4, 5]),
        ]
        
        # Should not raise
        validate_assignment(assignments, expected_stop_count=5)
    
    def test_duplicate_stop(self):
        """Test detection of duplicate stop assignment."""
        assignments = [
            DriverAssignment(driver_id=0, stop_ids=[1, 2]),
            DriverAssignment(driver_id=1, stop_ids=[2, 3]),  # 2 appears twice
        ]
        
        with pytest.raises(ValueError, match="assigned to multiple drivers"):
            validate_assignment(assignments, expected_stop_count=4)
    
    def test_wrong_count(self):
        """Test detection of wrong stop count."""
        assignments = [
            DriverAssignment(driver_id=0, stop_ids=[1, 2]),
        ]
        
        with pytest.raises(ValueError, match="Expected 3 stops"):
            validate_assignment(assignments, expected_stop_count=3)
    
    def test_depot_assignment(self):
        """Test rejection of depot in assignment."""
        assignments = [
            DriverAssignment(driver_id=0, stop_ids=[0, 1]),  # Depot wrongly assigned
        ]
        
        with pytest.raises(ValueError, match="Depot"):
            validate_assignment(assignments, expected_stop_count=2)


@pytest.mark.unit
class TestFleetRouter:
    """Test fleet router."""
    
    def test_create_router(self):
        """Test creating a fleet router."""
        instance = InstanceGenerator(seed=42).generate(n_stops=6)
        router = FleetRouter(instance, num_drivers=2)
        
        assert router.num_drivers == 2
        assert len(router.assignments) == 2
        assert router.distance_matrix.shape == (7, 7)  # Depot + 6 stops
    
    def test_invalid_num_drivers(self):
        """Test validation of num_drivers."""
        instance = InstanceGenerator(seed=42).generate(n_stops=5)
        
        with pytest.raises(ValueError):
            FleetRouter(instance, num_drivers=0)
    
    def test_route_with_nearest_neighbor(self):
        """Test routing with nearest neighbor."""
        instance = InstanceGenerator(seed=42).generate(n_stops=6)
        router = FleetRouter(instance, num_drivers=2)
        
        result = router.route_fleet_with_nearest_neighbor()
        
        assert result.algorithm == "Nearest Neighbor"
        assert result.num_drivers == 2
        assert result.num_stops_assigned == 6
        assert result.num_stops_visited == 6
        assert result.total_distance > 0
        assert result.longest_route_distance > 0
    
    def test_route_with_2opt(self):
        """Test routing with 2-Opt."""
        instance = InstanceGenerator(seed=42).generate(n_stops=6)
        router = FleetRouter(instance, num_drivers=2)
        
        result = router.route_fleet_with_2opt()
        
        assert result.algorithm == "2-Opt"
        assert result.num_drivers == 2
        assert result.num_stops_assigned == 6
    
    def test_route_with_heuristic(self):
        """Test routing with custom heuristic."""
        instance = InstanceGenerator(seed=42).generate(n_stops=6)
        router = FleetRouter(instance, num_drivers=2)
        
        # Use the nearest distance heuristic directly
        result = router.route_fleet_with_heuristic(
            nearest_distance_heuristic,
            "Custom"
        )
        
        assert result.algorithm == "Custom"
        assert result.num_drivers == 2
        assert result.num_stops_assigned == 6
    
    def test_empty_driver_routes(self):
        """Test handling of empty driver assignments."""
        instance = InstanceGenerator(seed=42).generate(n_stops=2)
        router = FleetRouter(instance, num_drivers=5)
        
        result = router.route_fleet_with_nearest_neighbor()
        
        # Check that all 5 drivers have routes
        assert len(result.driver_routes) == 5
        
        # Some should be empty (depot only)
        empty_routes = [r for r in result.driver_routes if len(r.assigned_stops) == 0]
        assert len(empty_routes) == 3
        
        # Empty routes should be [0, 0] with distance 0
        for route in empty_routes:
            assert route.route == [0, 0]
            assert route.distance == 0.0
    
    def test_zero_stops(self):
        """Test routing with zero stops."""
        instance = InstanceGenerator(seed=42).generate(n_stops=0)
        router = FleetRouter(instance, num_drivers=3)
        
        result = router.route_fleet_with_nearest_neighbor()
        
        assert result.num_stops_assigned == 0
        assert result.num_stops_visited == 0
        assert result.total_distance == 0.0
        assert result.longest_route_distance == 0.0
        
        # All drivers should have empty routes
        for route in result.driver_routes:
            assert route.route == [0, 0]
            assert route.distance == 0.0


@pytest.mark.unit
class TestFleetMetrics:
    """Test fleet-level metric calculations."""
    
    def test_total_distance_calculation(self):
        """Test that total distance sums correctly."""
        instance = InstanceGenerator(seed=42).generate(n_stops=6)
        router = FleetRouter(instance, num_drivers=2)
        
        result = router.route_fleet_with_nearest_neighbor()
        
        # Verify total is sum of individual routes
        manual_total = sum(route.distance for route in result.driver_routes)
        assert abs(result.total_distance - manual_total) < 0.01
    
    def test_longest_route_calculation(self):
        """Test longest route identification."""
        instance = InstanceGenerator(seed=42).generate(n_stops=6)
        router = FleetRouter(instance, num_drivers=2)
        
        result = router.route_fleet_with_nearest_neighbor()
        
        # Verify longest route
        max_distance = max(route.distance for route in result.driver_routes)
        assert abs(result.longest_route_distance - max_distance) < 0.01
    
    def test_all_routes_start_and_end_at_depot(self):
        """Test that all routes start and end at depot."""
        instance = InstanceGenerator(seed=42).generate(n_stops=10)
        router = FleetRouter(instance, num_drivers=3)
        
        result = router.route_fleet_with_nearest_neighbor()
        
        for route in result.driver_routes:
            if len(route.assigned_stops) > 0:
                assert route.route[0] == 0, "Route must start at depot"
                assert route.route[-1] == 0, "Route must end at depot"
    
    def test_same_assignments_for_all_algorithms(self):
        """Test that all algorithms get same stop assignments."""
        instance = InstanceGenerator(seed=42).generate(n_stops=12)
        router = FleetRouter(instance, num_drivers=3)
        
        nn_result = router.route_fleet_with_nearest_neighbor()
        opt_result = router.route_fleet_with_2opt()
        
        # Compare assigned stops (not routes, which will differ)
        for nn_route, opt_route in zip(nn_result.driver_routes, opt_result.driver_routes):
            assert nn_route.driver_id == opt_route.driver_id
            assert nn_route.assigned_stops == opt_route.assigned_stops


@pytest.mark.integration
class TestMultiDriverIntegration:
    """Integration tests for multi-driver routing."""
    
    def test_hand_calculated_two_drivers(self):
        """Test with hand-calculated simple case."""
        # Create simple instance: depot at origin, 4 stops in a square
        depot = Stop(id=0, location=Point(x=0, y=0), label="Depot")
        stops = [
            Stop(id=1, location=Point(x=10, y=0), label="Stop 1"),   # East
            Stop(id=2, location=Point(x=0, y=10), label="Stop 2"),   # North
            Stop(id=3, location=Point(x=-10, y=0), label="Stop 3"),  # West
            Stop(id=4, location=Point(x=0, y=-10), label="Stop 4"),  # South
        ]
        
        instance = DeliveryInstance(
            seed=42,
            depot=depot,
            stops=stops,
            n_stops=4
        )
        
        router = FleetRouter(instance, num_drivers=2)
        result = router.route_fleet_with_nearest_neighbor()
        
        # Verify results
        assert result.num_stops_assigned == 4
        assert result.num_stops_visited == 4
        assert result.num_drivers == 2
        
        # Each driver should visit 2 stops
        for route in result.driver_routes:
            assert len(route.assigned_stops) == 2
        
        # Total distance should be reasonable (4 radial trips)
        # Each stop is 10 units from depot, so minimum is 4 * 2 * 10 = 80
        assert result.total_distance >= 80
    
    def test_comparison_with_single_driver(self):
        """Test that single driver matches original behavior."""
        instance = InstanceGenerator(seed=42).generate(n_stops=5)
        
        # Single driver via FleetRouter
        router = FleetRouter(instance, num_drivers=1)
        fleet_result = router.route_fleet_with_nearest_neighbor()
        
        # Original single-route baseline
        from engine.instances import compute_distance_matrix
        from engine.baselines import nearest_neighbor
        
        locations = instance.get_all_locations()
        distance_matrix = compute_distance_matrix(locations)
        single_result = nearest_neighbor(distance_matrix)
        
        # Distances should match
        assert abs(fleet_result.total_distance - single_result.total_distance) < 0.01
        
        # Single driver should visit all stops
        assert fleet_result.num_stops_visited == 5
