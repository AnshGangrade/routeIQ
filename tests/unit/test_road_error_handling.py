"""
Tests for road routing error handling and HTTP status preservation.

Ensures that:
1. HTTP 503 errors from OSRM are not converted to 500
2. Missing geometry is distinguished from OSRM failures
3. Distance matrices use correct mode (road vs Euclidean)
4. Frontend receives appropriate error messages
"""

import numpy as np
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException

from engine.road.models import RoadDistanceResult
from engine.instances.models import DeliveryInstance, Stop, Point


class TestHTTPStatusPreservation:
    """Test that HTTP status codes are preserved through exception handlers."""
    
    def test_osrm_success_creates_instance(self):
        """
        Test that successful OSRM response creates instance correctly.
        This is the success path that was previously broken.
        """
        from api.routers.instances import create_instance
        from api.models import GenerateInstanceRequest
        
        # Mock successful OSRM response
        with patch('engine.road.adapter.get_osrm_table') as mock_osrm:
            mock_osrm.return_value = RoadDistanceResult(
                provider="osrm",
                success=True,
                distances=[
                    [0.0, 1500.0, 2000.0, 2500.0, 3000.0, 1800.0],
                    [1500.0, 0.0, 800.0, 1200.0, 1600.0, 900.0],
                    [2000.0, 800.0, 0.0, 600.0, 1000.0, 700.0],
                    [2500.0, 1200.0, 600.0, 0.0, 500.0, 1100.0],
                    [3000.0, 1600.0, 1000.0, 500.0, 0.0, 1300.0],
                    [1800.0, 900.0, 700.0, 1100.0, 1300.0, 0.0]
                ],
                durations=[
                    [0.0, 120.0, 150.0, 180.0, 200.0, 130.0],
                    [120.0, 0.0, 60.0, 90.0, 120.0, 70.0],
                    [150.0, 60.0, 0.0, 45.0, 80.0, 55.0],
                    [180.0, 90.0, 45.0, 0.0, 40.0, 85.0],
                    [200.0, 120.0, 80.0, 40.0, 0.0, 100.0],
                    [130.0, 70.0, 55.0, 85.0, 100.0, 0.0]
                ],
                cache_hit=False,
                metadata={}
            )
            
            request = GenerateInstanceRequest(
                num_stops=5,
                num_drivers=2,
                mode="road",
                depot_coords=[13.388860, 52.517037],
                stop_coords=[
                    [13.397634, 52.529407],
                    [13.428555, 52.523219],
                    [13.404954, 52.520008],
                    [13.376116, 52.508441],
                    [13.415094, 52.515641],
                ]
            )
            
            # Should create instance successfully
            import asyncio
            response = asyncio.run(create_instance(request))
            
            assert response.mode == "road"
            assert response.num_stops == 5
            assert response.num_drivers == 2
            assert len(response.stops) == 5
            assert len(response.drivers) == 2
            assert response.road_routing_info is not None
            assert response.road_routing_info["provider"] == "osrm"
            assert "depot" in response.model_dump()
    
    def test_osrm_503_not_converted_to_500(self):
        """
        Critical: HTTP 503 from OSRM service failure must not be caught
        and converted to generic 500 by outer exception handlers.
        """
        from api.routers.instances import create_instance
        from api.models import GenerateInstanceRequest
        from engine.road import create_road_distance_matrix
        
        # Mock OSRM failure
        with patch('engine.road.adapter.get_osrm_table') as mock_osrm:
            mock_osrm.return_value = RoadDistanceResult(
                provider="osrm",
                error="Connection refused",
                success=False
            )
            
            request = GenerateInstanceRequest(
                num_stops=5,
                num_drivers=2,
                mode="road",
                depot_coords=[13.388860, 52.517037],
                stop_coords=[
                    [13.397634, 52.529407],
                    [13.428555, 52.523219],
                    [13.404954, 52.520008],
                    [13.376116, 52.508441],
                    [13.415094, 52.515641],
                ]
            )
            
            # Should raise HTTPException with status 503, not 500
            with pytest.raises(HTTPException) as exc_info:
                import asyncio
                asyncio.run(create_instance(request))
            
            assert exc_info.value.status_code == 503, (
                f"OSRM failure must raise 503, not {exc_info.value.status_code}"
            )
            assert "unavailable" in exc_info.value.detail.lower()
    
    def test_invalid_coordinates_raise_400(self):
        """Invalid coordinates should raise HTTP 400, not 500 or 503."""
        from api.routers.instances import create_instance
        from api.models import GenerateInstanceRequest
        
        request = GenerateInstanceRequest(
            num_stops=5,  # Must meet minimum of 5
            num_drivers=1,
            mode="road",
            depot_coords=[0, 0],  # Invalid: all zeros
            stop_coords=[[0, 0], [0, 0], [0, 0], [0, 0], [0, 0]]  # 5 stops
        )
        
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            asyncio.run(create_instance(request))
        
        assert exc_info.value.status_code == 400
        assert "coordinate" in exc_info.value.detail.lower()


class TestGeometryErrorDistinction:
    """Test that missing geometry is properly distinguished from errors."""
    
    def test_geometry_error_included_in_response(self):
        """When OSRM geometry fetch fails, error message should be in response."""
        from api.routers.routing import get_route_geometry_if_road
        
        # Create instance data in road mode
        instance_data = {
            "mode": "road",
            "depot_coords": [13.388860, 52.517037],
            "stop_coords": [[13.397634, 52.529407]],
            "instance": Mock()
        }
        
        route_sequence = [0, 1, 0]
        
        # Patch both the config and the client creation in routing module
        with patch('api.routers.routing.RoadRoutingConfig') as mock_config_class:
            with patch('api.routers.routing.OSRMClient') as mock_client_class:
                # Setup config mock
                mock_config = Mock()
                mock_config.cache_enabled = False
                mock_config_class.return_value = mock_config
                
                # Setup client mock
                mock_client_instance = Mock()
                mock_client_instance.get_route.return_value = {
                    "error": "No route found"
                }
                mock_client_class.return_value.__enter__.return_value = mock_client_instance
                
                geometry, duration, error = get_route_geometry_if_road(
                    instance_data,
                    route_sequence
                )
                
                assert geometry is None
                assert duration is None
                assert error is not None
                assert "error" in error.lower()
    
    def test_synthetic_mode_returns_no_error(self):
        """In synthetic mode, geometry functions should return None without error."""
        from api.routers.routing import get_route_geometry_if_road
        
        instance_data = {
            "mode": "synthetic",
            "instance": Mock()
        }
        
        geometry, duration, error = get_route_geometry_if_road(
            instance_data,
            [0, 1, 0]
        )
        
        assert geometry is None
        assert duration is None
        assert error is None  # No error for synthetic mode
    
    def test_missing_geometry_vs_osrm_failure(self):
        """Frontend should distinguish between 'no geometry needed' and 'geometry failed'."""
        from api.routers.routing import get_route_geometry_if_road
        
        # Case 1: Synthetic mode - no geometry needed
        synthetic_data = {"mode": "synthetic"}
        geo1, dur1, err1 = get_route_geometry_if_road(synthetic_data, [0, 1, 0])
        assert geo1 is None and err1 is None
        
        # Case 2: Road mode but OSRM fails
        with patch('api.routers.routing.RoadRoutingConfig') as mock_config_class:
            with patch('api.routers.routing.OSRMClient') as mock_client_class:
                # Setup config
                mock_config = Mock()
                mock_config.cache_enabled = False
                mock_config_class.return_value = mock_config
                
                # Setup client to raise exception
                mock_client_instance = Mock()
                mock_client_instance.get_route.side_effect = Exception("Network error")
                mock_client_class.return_value.__enter__.return_value = mock_client_instance
                
                road_data = {
                    "mode": "road",
                    "depot_coords": [13.388860, 52.517037],
                    "stop_coords": [[13.397634, 52.529407]],
                    "instance": Mock()
                }
                
                geo2, dur2, err2 = get_route_geometry_if_road(road_data, [0, 1, 0])
                assert geo2 is None and err2 is not None
                assert "error" in err2.lower() or "failed" in err2.lower()


class TestDistanceMatrixSelection:
    """Test that correct distance matrix is used based on mode."""
    
    def test_road_mode_uses_road_distances(self):
        """
        In road mode, FleetRouter must use the provided road distance matrix,
        not compute Euclidean from coordinates.
        """
        from engine.routing.fleet import FleetRouter
        
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
        
        router = FleetRouter(instance, num_drivers=1, distance_matrix=road_matrix)
        
        # Verify router uses road matrix
        assert np.array_equal(router.distance_matrix, road_matrix)
        
        # Route and check distances are from road matrix
        result = router.route_fleet_with_nearest_neighbor()
        route_distance = result.total_distance
        
        # Distance should be in thousands (meters), not tiny (Euclidean on lat/lon)
        assert route_distance > 1000, (
            f"Route distance {route_distance} too small - may be using Euclidean instead of road"
        )
    
    def test_synthetic_mode_uses_euclidean_distances(self):
        """In synthetic mode, FleetRouter should use Euclidean distances."""
        from engine.routing.fleet import FleetRouter
        
        # Create instance with synthetic coordinates
        depot = Stop(id=0, location=Point(x=0, y=0), label="Depot")
        stops = [
            Stop(id=1, location=Point(x=3, y=4), label="Stop 1"),  # Distance 5
            Stop(id=2, location=Point(x=6, y=8), label="Stop 2"),  # Distance 10
        ]
        instance = DeliveryInstance(seed=42, depot=depot, stops=stops, n_stops=2)
        
        # No distance matrix provided - should compute Euclidean
        router = FleetRouter(instance, num_drivers=1)
        
        # Check Euclidean distances
        assert abs(router.distance_matrix[0, 1] - 5.0) < 0.01
        assert abs(router.distance_matrix[0, 2] - 10.0) < 0.01
    
    def test_euclidean_fallback_rejected_for_road_mode(self):
        """
        Critical: System must NOT silently fall back to Euclidean when
        road distance fetch fails. Must return error to user.
        """
        from engine.road.adapter import create_road_distance_matrix
        
        coords = [
            (13.388860, 52.517037),
            (13.397634, 52.529407),
        ]
        
        with patch('engine.road.adapter.get_osrm_table') as mock_osrm:
            mock_osrm.return_value = RoadDistanceResult(
                provider="osrm",
                error="Service unavailable",
                success=False
            )
            
            matrix, result = create_road_distance_matrix(coords)
            
            # Should return error result, not Euclidean fallback
            assert not result.success
            assert result.error is not None
            
            # Matrix should be zeros or empty, not Euclidean distances
            assert np.all(matrix == 0) or matrix.size == 0


class TestOSRMErrorTypes:
    """Test different types of OSRM errors are handled correctly."""
    
    def test_network_error_handling(self):
        """Network errors should be captured with descriptive messages."""
        from engine.road.osrm import OSRMClient, RoadRoutingConfig
        
        config = RoadRoutingConfig()
        config.cache_enabled = False  # Disable cache for this test
        client = OSRMClient(config)
        
        with patch.object(client.client, 'get') as mock_get:
            mock_get.side_effect = Exception("Connection timeout")
            
            result = client.get_table([(13.388860, 52.517037), (13.397634, 52.529407)])
            
            assert not result.success
            assert "timeout" in result.error.lower() or "connection" in result.error.lower()
    
    def test_malformed_response_handling(self):
        """Malformed OSRM responses should be handled gracefully."""
        from engine.road.osrm import OSRMClient, RoadRoutingConfig
        
        config = RoadRoutingConfig()
        config.cache_enabled = False  # Disable cache for this test
        client = OSRMClient(config)
        
        with patch.object(client.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": "InvalidQuery",
                "message": "Coordinates are invalid"
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            result = client.get_table([(13.388860, 52.517037), (13.397634, 52.529407)])
            
            assert not result.success
            assert "invalid" in result.error.lower()
    
    def test_missing_geometry_in_route_response(self):
        """Route requests with missing geometry should return clear error."""
        from engine.road.osrm import OSRMClient, RoadRoutingConfig
        
        config = RoadRoutingConfig()
        client = OSRMClient(config)
        
        with patch.object(client.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = {
                "code": "Ok",
                "routes": [{
                    "distance": 1000,
                    "duration": 100,
                    "geometry": {}  # Empty geometry object
                }]
            }
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response
            
            result = client.get_route([(13.388860, 52.517037), (13.397634, 52.529407)])
            
            # Should still work but with empty coordinates
            assert result.get("distance") == 1000
            assert result.get("geometry") == []  # Converted empty dict to empty list


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
