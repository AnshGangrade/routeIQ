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
        - distance_matrix: NxN numpy array of distances in meters
        - result: RoadDistanceResult with metadata and errors
        
    Note:
        - Failure returns an unsuccessful result; callers must not use its placeholder matrix.
        - Road distances are meters; synthetic distances remain map units.
        
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
    try:
        matrix = np.array(result.distances, dtype=float)
        if (matrix.shape != (len(coordinates), len(coordinates))
                or not np.isfinite(matrix).all() or (matrix < 0).any()):
            raise ValueError("Road distance matrix must be square, finite and non-negative")
    except (ValueError, TypeError) as exc:
        return np.zeros((len(coordinates), len(coordinates))), RoadDistanceResult(
            provider=result.provider, error=f"Invalid road distance matrix: {exc}"
        )
    
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
    
    for i, coord in enumerate(coordinates):
        if len(coord) != 2:
            return False, f"Coordinate at index {i} must contain exactly longitude and latitude"
        lon, lat = coord
        if not (-180 <= lon <= 180):
            return False, f"Invalid longitude at index {i}: {lon}"
        
        if not (-90 <= lat <= 90):
            return False, f"Invalid latitude at index {i}: {lat}"
    
    # Check if all coordinates are zeros (common mistake)
    if all(lon == 0 and lat == 0 for lon, lat in coordinates):
        return False, "All coordinates are (0, 0) - likely not real locations"
    
    return True, None
