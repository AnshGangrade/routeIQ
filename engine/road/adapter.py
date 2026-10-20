"""
Adapter to convert road routing results to distance matrices.

Preserves the existing distance_matrix abstraction so all algorithms
work unchanged with road distances.
"""

import numpy as np
from typing import List, Tuple, Optional

from .osrm import get_osrm_table
from .models import RoadRoutingConfig, RoadDistanceResult


def create_road_distance_matrix(
    coordinates: List[Tuple[float, float]],
    config: Optional[RoadRoutingConfig] = None
) -> Tuple[np.ndarray, RoadDistanceResult]:
    """
    Create distance matrix from geographic coordinates using road routing.
    
    This function acts as a drop-in replacement for compute_distance_matrix
    but uses real road distances instead of Euclidean.
    
    Args:
        coordinates: List of (longitude, latitude) tuples
                    [depot, stop1, stop2, ...]
        config: Road routing configuration (optional)
        
    Returns:
        Tuple of (distance_matrix, result)
        - distance_matrix: NxN numpy array of distances in map units
        - result: RoadDistanceResult with metadata and errors
        
    Note:
        - Returns Euclidean fallback if road routing fails
        - Distances are returned in the same units as Euclidean (map units)
        - This allows fair comparison between synthetic and road modes
        
    Example:
        >>> # Berlin coordinates (lon, lat)
        >>> coords = [
        ...     (13.388860, 52.517037),  # Depot
        ...     (13.397634, 52.529407),  # Stop 1
        ...     (13.428555, 52.523219),  # Stop 2
        ... ]
        >>> matrix, result = create_road_distance_matrix(coords)
        >>> if result.success:
        ...     print(f"Road distance depot->stop1: {matrix[0,1]:.0f} meters")
    """
    result = get_osrm_table(coordinates, config)
    
    if not result.success:
        # Return error - caller must handle
        # Don't silently fall back to Euclidean
        n = len(coordinates)
        return np.zeros((n, n)), result
    
    # Convert OSRM distances (list of lists) to numpy array
    matrix = np.array(result.distances, dtype=float)
    
    # OSRM returns distances in meters
    # Keep them in meters for consistency with coordinates
    
    return matrix, result


def validate_geographic_coordinates(
    coordinates: List[Tuple[float, float]]
) -> Tuple[bool, Optional[str]]:
    """
    Validate that coordinates are reasonable geographic coordinates.
    
    Args:
        coordinates: List of (longitude, latitude) tuples
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Checks:
        - Longitude in range [-180, 180]
        - Latitude in range [-90, 90]
        - Not all zeros (common mistake)
        - Not synthetic coordinates (like 0-100 range)
    """
    if not coordinates:
        return False, "Empty coordinates list"
    
    for i, (lon, lat) in enumerate(coordinates):
        if not (-180 <= lon <= 180):
            return False, f"Invalid longitude at index {i}: {lon}"
        
        if not (-90 <= lat <= 90):
            return False, f"Invalid latitude at index {i}: {lat}"
    
    # Check if all coordinates are zeros (common mistake)
    if all(lon == 0 and lat == 0 for lon, lat in coordinates):
        return False, "All coordinates are (0, 0) - likely not real locations"
    
    # Check if coordinates look synthetic (e.g., all in 0-100 range)
    if all(-100 <= lon <= 100 and -100 <= lat <= 100 for lon, lat in coordinates):
        # Could be real (e.g., Europe), but warn if they look grid-like
        lons = [lon for lon, _ in coordinates]
        lats = [lat for _, lat in coordinates]
        
        # If all coordinates are integers, likely synthetic
        if all(lon == int(lon) and lat == int(lat) for lon, lat in coordinates):
            return False, "Coordinates appear to be synthetic (all integers in small range)"
    
    return True, None
