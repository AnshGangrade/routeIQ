"""Fleet-level routing orchestration."""

import numpy as np
from typing import List, Callable
from .models import DriverAssignment, DriverRoute, FleetResult
from .assignment import assign_stops_by_sweep, validate_assignment
from engine.instances.models import DeliveryInstance
from engine.instances.distance import compute_distance_matrix, calculate_route_cost
from engine.baselines import nearest_neighbor, nearest_neighbor_with_2opt
from engine.heuristics import RouteHarness


class FleetRouter:
    """
    Orchestrates multi-driver routing across a fleet.
    
    The FleetRouter:
    1. Assigns stops to drivers deterministically
    2. Routes each driver's subset independently
    3. Aggregates fleet-level metrics
    
    Key Property: All algorithms receive the **same stop assignments**
    for fair comparison.
    """
    
    def __init__(self, instance: DeliveryInstance, num_drivers: int):
        """
        Initialize fleet router.
        
        Args:
            instance: Delivery instance with stops and depot
            num_drivers: Number of drivers
            
        Raises:
            ValueError: If num_drivers < 1
        """
        if num_drivers < 1:
            raise ValueError("num_drivers must be >= 1")
        
        self.instance = instance
        self.num_drivers = num_drivers
        
        # Compute shared distance matrix once
        locations = instance.get_all_locations()
        self.distance_matrix = compute_distance_matrix(locations)
        
        # Assign stops deterministically
        self.assignments = assign_stops_by_sweep(instance, num_drivers)
        
        # Validate assignments
        validate_assignment(self.assignments, instance.n_stops)
    
    def route_fleet_with_nearest_neighbor(self) -> FleetResult:
        """
        Route each driver using Nearest Neighbor.
        
        Returns:
            FleetResult with all driver routes
        """
        return self._route_fleet_with_baseline(
            algorithm_name="Nearest Neighbor",
            route_fn=nearest_neighbor
        )
    
    def route_fleet_with_2opt(self) -> FleetResult:
        """
        Route each driver using Nearest Neighbor + 2-Opt.
        
        Returns:
            FleetResult with all driver routes
        """
        return self._route_fleet_with_baseline(
            algorithm_name="2-Opt",
            route_fn=nearest_neighbor_with_2opt
        )
    
    def route_fleet_with_heuristic(
        self,
        scoring_function: Callable,
        algorithm_name: str = "Heuristic"
    ) -> FleetResult:
        """
        Route each driver using a scoring heuristic.
        
        Args:
            scoring_function: Callable that implements ScoringHeuristic protocol
            algorithm_name: Name for the algorithm
            
        Returns:
            FleetResult with all driver routes
        """
        harness = RouteHarness()
        driver_routes = []
        
        for assignment in self.assignments:
            # Handle empty assignment
            if not assignment.stop_ids:
                driver_routes.append(DriverRoute(
                    driver_id=assignment.driver_id,
                    assigned_stops=[],
                    route=[0, 0],  # Depot only
                    distance=0.0,
                    algorithm=algorithm_name
                ))
                continue
            
            # Build sub-distance matrix for this driver's stops
            # Include depot (index 0) and assigned stops
            indices = [0] + assignment.stop_ids
            sub_matrix = self.distance_matrix[np.ix_(indices, indices)]
            
            # Route this driver's stops
            route_result = harness.build_route(
                heuristic=scoring_function,
                distance_matrix=sub_matrix,
                n_stops=len(assignment.stop_ids),
                algorithm_name=algorithm_name
            )
            
            # Map sub-matrix indices back to global stop IDs
            global_route = [indices[stop_idx] for stop_idx in route_result.route]
            
            driver_routes.append(DriverRoute(
                driver_id=assignment.driver_id,
                assigned_stops=assignment.stop_ids,
                route=global_route,
                distance=route_result.total_distance,
                algorithm=algorithm_name
            ))
        
        return self._aggregate_fleet_result(driver_routes, algorithm_name)
    
    def _route_fleet_with_baseline(
        self,
        algorithm_name: str,
        route_fn: Callable
    ) -> FleetResult:
        """
        Route each driver using a baseline algorithm.
        
        Args:
            algorithm_name: Name of the algorithm
            route_fn: Function that takes distance_matrix and returns RouteResult
            
        Returns:
            FleetResult with all driver routes
        """
        driver_routes = []
        
        for assignment in self.assignments:
            # Handle empty assignment
            if not assignment.stop_ids:
                driver_routes.append(DriverRoute(
                    driver_id=assignment.driver_id,
                    assigned_stops=[],
                    route=[0, 0],
                    distance=0.0,
                    algorithm=algorithm_name
                ))
                continue
            
            # Build sub-distance matrix for this driver's stops
            indices = [0] + assignment.stop_ids
            sub_matrix = self.distance_matrix[np.ix_(indices, indices)]
            
            # Route this driver's stops
            route_result = route_fn(sub_matrix)
            
            # Map sub-matrix indices back to global stop IDs
            global_route = [indices[stop_idx] for stop_idx in route_result.route]
            
            driver_routes.append(DriverRoute(
                driver_id=assignment.driver_id,
                assigned_stops=assignment.stop_ids,
                route=global_route,
                distance=route_result.total_distance,
                algorithm=algorithm_name
            ))
        
        return self._aggregate_fleet_result(driver_routes, algorithm_name)
    
    def _aggregate_fleet_result(
        self,
        driver_routes: List[DriverRoute],
        algorithm_name: str
    ) -> FleetResult:
        """
        Aggregate per-driver routes into fleet-level result.
        
        Args:
            driver_routes: List of driver route results
            algorithm_name: Algorithm name
            
        Returns:
            FleetResult with aggregated metrics
        """
        total_distance = sum(route.distance for route in driver_routes)
        
        # Longest route distance (not duration/ETA)
        longest_distance = max(
            (route.distance for route in driver_routes),
            default=0.0
        )
        
        num_stops_assigned = sum(
            len(route.assigned_stops) for route in driver_routes
        )
        
        # Count visited stops (all stops in routes except depot appearances)
        visited_stops = set()
        for route in driver_routes:
            for stop_id in route.route:
                if stop_id != 0:  # Exclude depot
                    visited_stops.add(stop_id)
        num_stops_visited = len(visited_stops)
        
        return FleetResult(
            driver_routes=driver_routes,
            total_distance=total_distance,
            longest_route_distance=longest_distance,
            num_drivers=self.num_drivers,
            num_stops_assigned=num_stops_assigned,
            num_stops_visited=num_stops_visited,
            algorithm=algorithm_name
        )
