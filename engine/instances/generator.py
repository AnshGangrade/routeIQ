"""
Synthetic delivery instance generator.

Generates reproducible instances with configurable characteristics.
"""

import numpy as np
from typing import Optional, Tuple
from .models import DeliveryInstance, Stop, Point


class InstanceGenerator:
    """
    Generate synthetic delivery routing instances.
    
    Features:
    - Reproducible generation via random seeds
    - Configurable number of stops
    - Uniform or clustered spatial distributions
    - Euclidean 2D coordinate space
    
    Example:
        >>> generator = InstanceGenerator(seed=42)
        >>> instance = generator.generate(n_stops=10)
        >>> print(instance.n_stops)
        10
    """
    
    # Default coordinate bounds for uniform distribution
    DEFAULT_X_RANGE = (0.0, 100.0)
    DEFAULT_Y_RANGE = (0.0, 100.0)
    
    def __init__(
        self,
        seed: Optional[int] = None,
        x_range: Tuple[float, float] = DEFAULT_X_RANGE,
        y_range: Tuple[float, float] = DEFAULT_Y_RANGE
    ):
        """
        Initialize the instance generator.
        
        Args:
            seed: Random seed for reproducibility (None = random)
            x_range: (min, max) for X coordinates
            y_range: (min, max) for Y coordinates
            
        Raises:
            ValueError: If ranges are invalid
        """
        if x_range[0] >= x_range[1]:
            raise ValueError(f"Invalid x_range: {x_range}")
        if y_range[0] >= y_range[1]:
            raise ValueError(f"Invalid y_range: {y_range}")
        
        self.seed = seed
        self.x_range = x_range
        self.y_range = y_range
        self._rng = np.random.RandomState(seed)
    
    def generate(
        self,
        n_stops: int,
        depot_location: Optional[Point] = None,
        distribution: str = "uniform"
    ) -> DeliveryInstance:
        """
        Generate a delivery instance with specified number of stops.
        
        Args:
            n_stops: Number of delivery stops (must be >= 0)
            depot_location: Fixed depot location (None = random within bounds)
            distribution: Spatial distribution: "uniform" or "clustered"
            
        Returns:
            DeliveryInstance with depot and n_stops delivery stops
            
        Raises:
            ValueError: If n_stops is negative or distribution is invalid
            
        Example:
            >>> gen = InstanceGenerator(seed=42)
            >>> instance = gen.generate(n_stops=5)
            >>> instance.n_stops
            5
            >>> instance.depot.id
            0
        """
        if n_stops < 0:
            raise ValueError(f"n_stops must be non-negative, got {n_stops}")
        
        if distribution not in ("uniform", "clustered"):
            raise ValueError(
                f"distribution must be 'uniform' or 'clustered', got '{distribution}'"
            )
        
        # Generate or use provided depot
        if depot_location is None:
            depot_location = self._generate_point()
        
        depot = Stop(
            id=0,
            location=depot_location,
            label="Depot"
        )
        
        # Generate delivery stops
        if distribution == "uniform":
            stop_locations = [self._generate_point() for _ in range(n_stops)]
        else:  # clustered
            stop_locations = self._generate_clustered_points(n_stops)
        
        stops = [
            Stop(
                id=i + 1,
                location=loc,
                label=f"Stop {i + 1}"
            )
            for i, loc in enumerate(stop_locations)
        ]
        
        return DeliveryInstance(
            seed=self.seed if self.seed is not None else -1,
            depot=depot,
            stops=stops,
            n_stops=n_stops
        )
    
    def generate_problem(self, n_stops: int, num_drivers: int = 1, *,
                         search_seed: int | None = None, **kwargs):
        """Canonical synthetic problem; legacy generate() still returns DeliveryInstance."""
        from engine.routing.adapters import problem_from_instance
        return problem_from_instance(self.generate(n_stops, **kwargs), num_drivers,
                                     search_seed=search_seed)

    def _generate_point(self) -> Point:
        """Generate a random point within the configured bounds."""
        x = self._rng.uniform(self.x_range[0], self.x_range[1])
        y = self._rng.uniform(self.y_range[0], self.y_range[1])
        return Point(x=x, y=y)
    
    def _generate_clustered_points(
        self,
        n_points: int,
        n_clusters: Optional[int] = None
    ) -> list[Point]:
        """
        Generate clustered points for more realistic urban delivery patterns.
        
        Args:
            n_points: Number of points to generate
            n_clusters: Number of clusters (None = auto-select based on n_points)
            
        Returns:
            List of Point objects with clustering
        """
        if n_points == 0:
            return []
        
        # Auto-select cluster count if not specified
        if n_clusters is None:
            n_clusters = max(1, min(5, n_points // 3))
        
        # Generate cluster centers
        cluster_centers = [self._generate_point() for _ in range(n_clusters)]
        
        # Cluster radius as fraction of coordinate space
        x_span = self.x_range[1] - self.x_range[0]
        y_span = self.y_range[1] - self.y_range[0]
        cluster_radius_x = x_span * 0.15  # 15% of range
        cluster_radius_y = y_span * 0.15
        
        # Assign points to clusters and generate with offset from center
        points = []
        for i in range(n_points):
            cluster_idx = i % n_clusters
            center = cluster_centers[cluster_idx]
            
            # Generate point near cluster center (normal distribution)
            offset_x = self._rng.normal(0, cluster_radius_x / 2)
            offset_y = self._rng.normal(0, cluster_radius_y / 2)
            
            # Clamp to bounds
            x = np.clip(
                center.x + offset_x,
                self.x_range[0],
                self.x_range[1]
            )
            y = np.clip(
                center.y + offset_y,
                self.y_range[0],
                self.y_range[1]
            )
            
            points.append(Point(x=x, y=y))
        
        return points
    
    def generate_batch(
        self,
        n_instances: int,
        n_stops: int,
        start_seed: Optional[int] = None
    ) -> list[DeliveryInstance]:
        """
        Generate multiple instances with sequential seeds.
        
        Useful for creating test/train/validation sets.
        
        Args:
            n_instances: Number of instances to generate
            n_stops: Number of stops per instance
            start_seed: Starting seed (None = use current seed)
            
        Returns:
            List of DeliveryInstance objects
            
        Example:
            >>> gen = InstanceGenerator()
            >>> instances = gen.generate_batch(
            ...     n_instances=10,
            ...     n_stops=20,
            ...     start_seed=100
            ... )
            >>> len(instances)
            10
        """
        if start_seed is None:
            start_seed = self.seed if self.seed is not None else 0
        
        instances = []
        for i in range(n_instances):
            gen = InstanceGenerator(seed=start_seed + i)
            instance = gen.generate(n_stops=n_stops)
            instances.append(instance)
        
        return instances
