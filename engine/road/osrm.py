"""
OSRM (Open Source Routing Machine) client for road distances.

Uses the public OSRM demo server by default, or can use self-hosted instance.
API documentation: http://project-osrm.org/docs/v5.24.0/api/
"""

import httpx
import numpy as np
from typing import List, Tuple, Optional
import time
import hashlib
import json
from pathlib import Path

from .models import RoadRoutingConfig, RoadDistanceResult


class OSRMClient:
    """
    Client for OSRM routing API.
    
    Uses the /table endpoint to get distance/duration matrices.
    """
    
    def __init__(self, config: RoadRoutingConfig):
        """
        Initialize OSRM client.
        
        Args:
            config: Road routing configuration
        """
        self.config = config
        self.client = httpx.Client(timeout=config.timeout)
        
        # Simple file-based cache
        if config.cache_enabled:
            self.cache_dir = Path("runs/.road_cache")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.cache_dir = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
    
    def close(self):
        """Close the HTTP client."""
        self.client.close()
    
    def _cache_key(self, coordinates: List[Tuple[float, float]]) -> str:
        """Generate cache key for coordinates."""
        coord_str = json.dumps([self.config.provider.value, self.config.base_url.rstrip('/'),
                               'driving', 'distance,duration', coordinates], sort_keys=True)
        return hashlib.sha256(coord_str.encode()).hexdigest()
    
    def _load_from_cache(self, cache_key: str) -> Optional[RoadDistanceResult]:
        """Load result from cache if available."""
        if not self.cache_dir:
            return None
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
            result = RoadDistanceResult(**data)
            result.cache_hit = True
            return result
        except Exception:
            return None
    
    def _save_to_cache(self, cache_key: str, result: RoadDistanceResult):
        """Save result to cache."""
        if not self.cache_dir:
            return
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(result.model_dump(), f)
        except Exception:
            pass  # Cache save failure is non-fatal
    
    def get_table(
        self,
        coordinates: List[Tuple[float, float]]
    ) -> RoadDistanceResult:
        """
        Get distance/duration table for coordinates.
        
        Args:
            coordinates: List of (longitude, latitude) tuples
            
        Returns:
            RoadDistanceResult with distance matrix
            
        Note:
            OSRM expects coordinates as (lon, lat), not (lat, lon)!
        """
        # Check cache first
        if self.config.cache_enabled:
            cache_key = self._cache_key(coordinates)
            cached = self._load_from_cache(cache_key)
            if cached:
                return cached
        
        # Validate input
        if len(coordinates) == 0:
            return RoadDistanceResult(
                provider=self.config.provider.value,
                error="Empty coordinates list"
            )
        
        if len(coordinates) > self.config.max_locations:
            return RoadDistanceResult(
                provider=self.config.provider.value,
                error=f"Too many locations: {len(coordinates)} > {self.config.max_locations}"
            )
        
        # Build OSRM table request
        # Format: /table/v1/driving/lon1,lat1;lon2,lat2;...
        coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coordinates)
        url = f"{self.config.base_url}/table/v1/driving/{coord_str}"
        
        # Request both distances and durations
        params = {
            "annotations": "distance,duration"
        }
        
        try:
            start_time = time.time()
            response = self.client.get(url, params=params)
            elapsed = time.time() - start_time
            
            response.raise_for_status()
            data = response.json()
            
            # Check OSRM response code
            if data.get("code") != "Ok":
                error_msg = ("Invalid OSRM query" if data.get("code") in ("InvalidQuery", "InvalidValue", "InvalidOptions")
                             else "Routing provider rejected the table request")
                return RoadDistanceResult(
                    provider=self.config.provider.value,
                    error=f"OSRM error: {error_msg}",
                    metadata={"osrm_code": data.get("code")}
                )
            
            # Extract matrices
            distances = data.get("distances")
            durations = data.get("durations")
            
            if not distances:
                return RoadDistanceResult(
                    provider=self.config.provider.value,
                    error="No distance matrix in OSRM response"
                )
            
            result = RoadDistanceResult(
                distances=distances,
                durations=durations,
                provider=self.config.provider.value,
                metadata={
                    "request_time_seconds": elapsed,
                    "num_locations": len(coordinates),
                    "osrm_code": data.get("code")
                }
            )
            
            # Cache successful result
            if self.config.cache_enabled:
                self._save_to_cache(cache_key, result)
            
            return result
            
        except httpx.HTTPStatusError as e:
            return RoadDistanceResult(
                provider=self.config.provider.value,
                error=f"HTTP {e.response.status_code}: Road routing request failed"
            )
        except httpx.RequestError as e:
            return RoadDistanceResult(
                provider=self.config.provider.value,
                error=f"Request failed: {type(e).__name__}"
            )
        except Exception as e:
            return RoadDistanceResult(
                provider=self.config.provider.value,
                error="Road routing connection failed or returned an invalid response"
            )


    def get_route(
        self,
        coordinates: List[Tuple[float, float]],
        overview: str = "full"
    ) -> dict:
        """
        Get route geometry for a sequence of coordinates.
        
        Args:
            coordinates: Ordered list of (longitude, latitude) tuples
            overview: 'full', 'simplified', or 'false'
            
        Returns:
            Dict with route geometry and metadata
        """
        if len(coordinates) < 2:
            return {"error": "Need at least 2 coordinates for a route"}
        
        # Build OSRM route request
        # Format: /route/v1/driving/lon1,lat1;lon2,lat2;...
        coord_str = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coordinates)
        url = f"{self.config.base_url}/route/v1/driving/{coord_str}"
        
        params = {
            "overview": overview,
            "geometries": "geojson"  # Get GeoJSON format
        }
        
        try:
            response = self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != "Ok":
                return {"error": "OSRM error: Routing provider rejected the route request"}
            
            routes = data.get("routes", [])
            if not routes:
                return {"error": "No route found"}
            
            route = routes[0]
            geometry = route.get("geometry", {}).get("coordinates", [])
            
            # Convert from [lon, lat] to [lat, lon] for Leaflet
            geometry_latlng = [[coord[1], coord[0]] for coord in geometry]
            
            return {
                "geometry": geometry_latlng,
                "distance": route.get("distance"),  # meters
                "duration": route.get("duration"),  # seconds
            }
            
        except Exception as e:
            return {"error": f"Route request failed: {type(e).__name__}"}


def get_osrm_table(
    coordinates: List[Tuple[float, float]],
    config: Optional[RoadRoutingConfig] = None
) -> RoadDistanceResult:
    """
    Convenience function to get OSRM distance table.
    
    Args:
        coordinates: List of (longitude, latitude) tuples
        config: Optional configuration (uses public OSRM by default)
        
    Returns:
        RoadDistanceResult with distances in meters
        
    Example:
        >>> coords = [(13.388860, 52.517037), (13.397634, 52.529407)]  # Berlin
        >>> result = get_osrm_table(coords)
        >>> if result.success:
        ...     print(f"Distance: {result.distances[0][1]:.0f} meters")
    """
    if config is None:
        config = RoadRoutingConfig()
    
    with OSRMClient(config) as client:
        return client.get_table(coordinates)
