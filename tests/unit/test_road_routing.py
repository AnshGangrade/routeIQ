"""
Tests for road distance integration with routing.

Ensures that road distances are correctly used in optimization,
not silently replaced with Euclidean distances.
"""

import numpy as np
import pytest
from engine.routing.fleet import FleetRouter
from engine.instances.models import DeliveryInstance, Stop, Point


class TestRoadDistanceIntegration:
    """Test that road distances are correctly used in routing."""
    
    def test_fleet_router_uses_provided_distance_matrix(self):
        """
        Critical: FleetRouter must use the provided distance matrix,
        not recompute Euclidean distances from coordinates.
        """
        # Create a simple instance with geographic coordinates
        # (longitude/latitude values that look realistic)
        depot = Stop(id=0, location=Point(x=13.388860, y=52.517037), label="Depot")
        stops = [
            Stop(id=1, location=Point(x=13.397634, y=52.529407), label="Stop 1"),
            Stop(id=2, location=Point(x=13.428555, y=52.523219), label="Stop 2"),
        ]
        instance = DeliveryInstance(seed=42, depot=depot, stops=stops, n_stops=2)
        
        # Create a mock road distance matrix (in meters)
        # These are realistic road distances, NOT Euclidean from coordinates
        road_distances = np.array([
            [0.0, 2500.0, 3200.0],     # Depot to stops
            [2500.0, 0.0, 1800.0],     # Stop 1 to others
            [3200.0, 1800.0, 0.0]      # Stop 2 to others
        ])
        
        # Create FleetRouter with road distances
        router = FleetRouter(instance, num_drivers=1, distance_matrix=road_distances)
        
        # Verify the router uses the provided matrix
        assert np.array_equal(router.distance_matrix, road_distances)
        
        # Route with nearest neighbor
        result = router.route_fleet_with_nearest_neighbor()
        
        # The route distance MUST be calculated from road_distances,
        # not from Euclidean coordinate differences
        assert len(result.driver_routes) == 1
        route = result.driver_routes[0]
        
        # Verify route uses road distances
        # Route should be [0, 1, 2, 0] or [0, 2, 1, 0]
        # Calculate expected distance for each possibility
        if route.route == [0, 1, 2, 0]:
            expected = road_distances[0, 1] + road_distances[1, 2] + road_distances[2, 0]
        elif route.route == [0, 2, 1, 0]:
            expected = road_distances[0, 2] + road_distances[2, 1] + road_distances[1, 0]
        else:
            pytest.fail(f"Unexpected route: {route.route}")
        
        # Distance should match road distances, not Euclidean
        assert abs(route.distance - expected) < 0.01, (
            f"Route distance {route.distance} does not match expected {expected} "
            f"from road distance matrix. Route may be using Euclidean distances!"
        )
    
    def test_fleet_router_rejects_wrong_size_matrix(self):
        """FleetRouter should validate distance matrix size."""
        depot = Stop(id=0, location=Point(x=0, y=0), label="Depot")
        stops = [
            Stop(id=1, location=Point(x=10, y=10), label="Stop 1"),
            Stop(id=2, location=Point(x=20, y=20), label="Stop 2"),
        ]
        instance = DeliveryInstance(seed=42, depot=depot, stops=stops, n_stops=2)
        
        # Wrong size matrix (4x4 instead of 3x3)
        wrong_matrix = np.zeros((4, 4))
        
        with pytest.raises(ValueError, match="Distance matrix shape"):
            FleetRouter(instance, num_drivers=1, distance_matrix=wrong_matrix)
    
    def test_fleet_router_falls_back_to_euclidean_when_no_matrix(self):
        """When no matrix provided, FleetRouter should compute Euclidean."""
        depot = Stop(id=0, location=Point(x=0, y=0), label="Depot")
        stops = [
            Stop(id=1, location=Point(x=3, y=4), label="Stop 1"),  # Distance 5
        ]
        instance = DeliveryInstance(seed=42, depot=depot, stops=stops, n_stops=1)
        
        # No distance matrix provided
        router = FleetRouter(instance, num_drivers=1)
        
        # Should compute Euclidean distances
        expected_distance = 5.0  # sqrt(3^2 + 4^2)
        assert abs(router.distance_matrix[0, 1] - expected_distance) < 0.01
    
    def test_road_vs_euclidean_produces_different_results(self):
        """
        Critical regression test: road distances and Euclidean distances
        should produce different route costs for the same coordinates.
        
        This test fails if road distances are silently replaced with Euclidean.
        """
        # Create instance with lat/lon coordinates
        depot = Stop(id=0, location=Point(x=13.388860, y=52.517037), label="Depot")
        stops = [
            Stop(id=1, location=Point(x=13.397634, y=52.529407), label="Stop 1"),
            Stop(id=2, location=Point(x=13.428555, y=52.523219), label="Stop 2"),
        ]
        instance = DeliveryInstance(seed=42, depot=depot, stops=stops, n_stops=2)
        
        # Road distances (meters)
        road_matrix = np.array([
            [0.0, 2500.0, 3200.0],
            [2500.0, 0.0, 1800.0],
            [3200.0, 1800.0, 0.0]
        ])
        
        # Route with road distances
        road_router = FleetRouter(instance, num_drivers=1, distance_matrix=road_matrix)
        road_result = road_router.route_fleet_with_nearest_neighbor()
        road_distance = road_result.total_distance
        
        # Route with Euclidean (default)
        euclidean_router = FleetRouter(instance, num_drivers=1)
        euclidean_result = euclidean_router.route_fleet_with_nearest_neighbor()
        euclidean_distance = euclidean_result.total_distance
        
        # These MUST be different (Euclidean on lat/lon is meaningless)
        assert abs(road_distance - euclidean_distance) > 1.0, (
            f"Road distance ({road_distance}) and Euclidean distance ({euclidean_distance}) "
            f"are too similar. Road distances may not be used correctly!"
        )
        
        # Road distance should be in reasonable range (thousands of meters)
        assert 5000 < road_distance < 15000, (
            f"Road distance {road_distance} seems wrong for realistic Berlin coordinates"
        )
        
        # Euclidean on lat/lon should be tiny (wrong, but that's the point)
        assert euclidean_distance < 100, (
            f"Euclidean distance {euclidean_distance} on lat/lon coordinates should be small"
        )
