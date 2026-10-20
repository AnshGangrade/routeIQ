"""Data models for multi-driver routing."""

from typing import List, Optional
from pydantic import BaseModel, Field


class DriverAssignment(BaseModel):
    """Assignment of stops to a single driver.
    
    Attributes:
        driver_id: Driver identifier (0-indexed)
        stop_ids: List of delivery stop IDs assigned to this driver (excludes depot)
    """
    driver_id: int = Field(..., ge=0, description="Driver identifier")
    stop_ids: List[int] = Field(default_factory=list, description="Assigned stop IDs")
    
    def __repr__(self) -> str:
        return f"DriverAssignment(driver={self.driver_id}, stops={self.stop_ids})"


class DriverRoute(BaseModel):
    """Result of routing for a single driver.
    
    Attributes:
        driver_id: Driver identifier
        assigned_stops: Stop IDs originally assigned to this driver
        route: Complete route [0, ..., 0] including depot
        distance: Total distance traveled by this driver
        algorithm: Algorithm used for this route
    """
    driver_id: int = Field(..., ge=0, description="Driver identifier")
    assigned_stops: List[int] = Field(..., description="Assigned stop IDs")
    route: List[int] = Field(..., description="Complete route with depot")
    distance: float = Field(..., ge=0, description="Total route distance")
    algorithm: str = Field(..., description="Algorithm name")
    
    def __repr__(self) -> str:
        return (
            f"DriverRoute(driver={self.driver_id}, "
            f"stops={len(self.assigned_stops)}, "
            f"distance={self.distance:.2f})"
        )


class FleetResult(BaseModel):
    """Result of multi-driver fleet routing.
    
    Attributes:
        driver_routes: Route for each driver
        total_distance: Sum of all driver distances
        longest_route_distance: Maximum distance among all drivers
        num_drivers: Number of drivers
        num_stops_assigned: Total stops assigned across all drivers
        num_stops_visited: Total stops actually visited
        algorithm: Algorithm used
    """
    driver_routes: List[DriverRoute] = Field(..., description="Per-driver routes")
    total_distance: float = Field(..., ge=0, description="Total fleet distance")
    longest_route_distance: float = Field(..., ge=0, description="Longest single route")
    num_drivers: int = Field(..., ge=0, description="Number of drivers")
    num_stops_assigned: int = Field(..., ge=0, description="Stops assigned")
    num_stops_visited: int = Field(..., ge=0, description="Stops visited")
    algorithm: str = Field(..., description="Algorithm name")
    
    def __repr__(self) -> str:
        return (
            f"FleetResult(algorithm='{self.algorithm}', "
            f"drivers={self.num_drivers}, "
            f"total_dist={self.total_distance:.2f}, "
            f"longest={self.longest_route_distance:.2f})"
        )
