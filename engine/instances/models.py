"""
Data models for delivery instances.

Conventions:
- Stop indices: 0 = depot, 1..N = delivery stops
- All coordinates are 2D Euclidean (x, y)
- Instances are immutable after creation for reproducibility
"""

from typing import List, Tuple
from pydantic import BaseModel, Field, field_validator


class Point(BaseModel):
    """
    A 2D point in Euclidean space.
    
    Attributes:
        x: X coordinate
        y: Y coordinate
    """
    x: float
    y: float
    
    def to_tuple(self) -> Tuple[float, float]:
        """Return point as (x, y) tuple."""
        return (self.x, self.y)
    
    def __repr__(self) -> str:
        return f"Point(x={self.x:.2f}, y={self.y:.2f})"


class Stop(BaseModel):
    """
    A delivery stop with unique identifier and location.
    
    Attributes:
        id: Unique stop identifier (0 = depot)
        location: 2D coordinates
        label: Human-readable label (e.g., "Depot", "Stop 1")
    """
    id: int = Field(..., ge=0, description="Stop identifier (0=depot, 1+=stops)")
    location: Point
    label: str = Field(default="", description="Human-readable label")
    
    def __repr__(self) -> str:
        return f"Stop(id={self.id}, label='{self.label}', location={self.location})"


class DeliveryInstance(BaseModel):
    """
    A complete delivery routing instance.
    
    Index Convention:
        - Index 0: Depot (always present)
        - Index 1 to n_stops: Delivery stops
    
    Attributes:
        seed: Random seed used for generation (for reproducibility)
        depot: The depot location (index 0)
        stops: List of delivery stops (indices 1 to n_stops)
        n_stops: Number of delivery stops (excludes depot)
    """
    seed: int = Field(..., description="Random seed for reproducibility")
    depot: Stop
    stops: List[Stop] = Field(default_factory=list)
    n_stops: int = Field(..., ge=0, description="Number of delivery stops")
    
    @field_validator('depot')
    @classmethod
    def validate_depot_id(cls, v: Stop) -> Stop:
        """Ensure depot has id=0."""
        if v.id != 0:
            raise ValueError("Depot must have id=0")
        return v
    
    @field_validator('stops')
    @classmethod
    def validate_stop_ids(cls, v: List[Stop]) -> List[Stop]:
        """Ensure stops have sequential IDs starting from 1."""
        for i, stop in enumerate(v, start=1):
            if stop.id != i:
                raise ValueError(f"Stop at position {i-1} must have id={i}, got id={stop.id}")
        return v
    
    @field_validator('n_stops')
    @classmethod
    def validate_n_stops_matches_list(cls, v: int, info) -> int:
        """Ensure n_stops matches the length of stops list."""
        if 'stops' in info.data:
            actual_stops = len(info.data['stops'])
            if v != actual_stops:
                raise ValueError(
                    f"n_stops={v} does not match actual stops count={actual_stops}"
                )
        return v
    
    def get_all_locations(self) -> List[Point]:
        """
        Return all locations in index order: [depot, stop1, stop2, ...].
        
        Returns:
            List of Point objects, depot first, then all stops in order
        """
        return [self.depot.location] + [stop.location for stop in self.stops]
    
    def get_stop_by_id(self, stop_id: int) -> Stop:
        """
        Get a stop by its ID.
        
        Args:
            stop_id: Stop identifier (0=depot, 1+=delivery stops)
            
        Returns:
            Stop object
            
        Raises:
            IndexError: If stop_id is invalid
        """
        if stop_id == 0:
            return self.depot
        elif 1 <= stop_id <= self.n_stops:
            return self.stops[stop_id - 1]
        else:
            raise IndexError(
                f"Invalid stop_id={stop_id}. Valid range: 0 to {self.n_stops}"
            )
    
    def __repr__(self) -> str:
        return (
            f"DeliveryInstance(seed={self.seed}, n_stops={self.n_stops}, "
            f"depot={self.depot.location})"
        )
