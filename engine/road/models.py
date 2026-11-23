"""
Data models for road routing.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class RoadProvider(str, Enum):
    """Supported road routing providers."""
    OSRM = "osrm"
    OSRM_PUBLIC = "osrm_public"  # public demo server
    MAPBOX = "mapbox"  # future


class RoadRoutingConfig(BaseModel):
    """
    Configuration for real road routing.
    
    Attributes:
        provider: Which routing engine to use
        base_url: API base URL (e.g., "http://router.project-osrm.org")
        api_key: API key if required (e.g., for Mapbox)
        timeout: Request timeout in seconds
        max_locations: Maximum locations per request
        cache_enabled: Whether to cache results
    """
    provider: RoadProvider = Field(RoadProvider.OSRM_PUBLIC, description="Routing provider")
    base_url: str = Field("https://router.project-osrm.org", description="API base URL")
    api_key: Optional[str] = Field(None, repr=False, description="API key if required")
    timeout: float = Field(30.0, ge=1.0, description="Request timeout in seconds")
    max_locations: int = Field(100, ge=2, description="Max locations per request")
    cache_enabled: bool = Field(True, description="Enable response caching")


class RoadDistanceResult(BaseModel):
    """
    Result from road routing API.
    
    Attributes:
        distances: Distance matrix (meters)
        durations: Duration matrix (seconds) if available
        provider: Which provider generated this
        cache_hit: Whether result came from cache
        error: Error message if request failed
    """
    distances: Optional[List[List[float]]] = None
    durations: Optional[List[List[float]]] = None
    provider: str
    cache_hit: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def success(self) -> bool:
        """Whether the request succeeded."""
        return self.distances is not None and self.error is None
