"""Fleet-level routing orchestration."""

import numpy as np
from typing import List, Callable
from .models import DriverAssignment, DriverRoute, FleetResult
from .assignment import assign_stops_by_sweep, validate_assignment
from .problem import FleetProblem
from .adapters import problem_from_instance
from .validation import validate_fleet_solution
from engine.instances.models import DeliveryInstance
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
    
    def __init__(
        self,
        instance: DeliveryInstance | FleetProblem,
        num_drivers: int | None = None,
        distance_matrix: np.ndarray | None = None
    ):
        """
        Initialize fleet router.
        
        Args:
            instance: Canonical FleetProblem or legacy DeliveryInstance
            num_drivers: Required only for legacy instances
            distance_matrix: Pre-computed distance matrix (optional).
                           If None, computes Euclidean distances from coordinates.
                           If provided, must match instance size (n_stops + 1).
                           A FleetProblem already supplies drivers and matrix;
                           overrides are rejected.
            
        Raises:
            ValueError: If num_drivers < 1 or distance_matrix size mismatches
        """
        if isinstance(instance, FleetProblem):
            if num_drivers is not None or distance_matrix is not None:
                raise ValueError("A FleetProblem already defines drivers and its matrix")
            problem = instance
        else:
            if distance_matrix is not None and not isinstance(distance_matrix, np.ndarray):
                raise ValueError("Legacy distance matrix must be a NumPy array")
            problem = problem_from_instance(instance, num_drivers, distance_matrix=distance_matrix)
        self.problem = problem
        self.num_drivers = problem.num_drivers
        self.distance_matrix = problem.matrix_array()
        self._indices = {node: i for i, node in enumerate(problem.node_ids)}
        # Keep the historical angular round-robin assignment exactly as defined.
        # Its coordinate requirement is explicit; do not invent geometry for matrices.
        if problem.coordinates is not None:
            from engine.instances.models import Point, Stop
            points = [Point(x=x, y=y) for x, y in problem.coordinates]
            self.instance = DeliveryInstance(
                seed=problem.seed, depot=Stop(id=0, location=points[0]),
                stops=[Stop(id=i, location=point) for i, point in enumerate(points[1:], 1)],
                n_stops=problem.n_stops)
            assignments = assign_stops_by_sweep(self.instance, self.num_drivers)
            validate_assignment(assignments, problem.n_stops)
            self.assignments = [DriverAssignment(
                driver_id=a.driver_id, stop_ids=[problem.node_ids[i] for i in a.stop_ids])
                for a in assignments]
        elif self.num_drivers == 1 or problem.n_stops == 0:
            self.instance = None
            self.assignments = [DriverAssignment(driver_id=i,
                stop_ids=list(problem.stop_ids) if i == 0 else [])
                for i in range(self.num_drivers)]
        else:
            raise ValueError("Legacy multi-driver sweep assignment requires coordinates")

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
    
    def route_fleet_with_2opt(self, max_2opt_iterations: int = 1000) -> FleetResult:
        """
        Route each driver using Nearest Neighbor + 2-Opt.
        
        Returns:
            FleetResult with all driver routes
        """
        return self._route_fleet_with_baseline(
            algorithm_name="2-Opt",
            route_fn=lambda matrix: nearest_neighbor_with_2opt(matrix, max_2opt_iterations=max_2opt_iterations)
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
                    route=[self.problem.depot_id, self.problem.depot_id],  # Depot only
                    distance=0.0,
                    algorithm=algorithm_name
                ))
                continue
            
            # Build sub-distance matrix for this driver's stops
            # Include depot (index 0) and assigned stops
            indices = [self.problem.depot_id] + assignment.stop_ids
            matrix_indices = [self._indices[node] for node in indices]
            sub_matrix = self.distance_matrix[np.ix_(matrix_indices, matrix_indices)]
            
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
                    route=[self.problem.depot_id, self.problem.depot_id],
                    distance=0.0,
                    algorithm=algorithm_name
                ))
                continue
            
            # Build sub-distance matrix for this driver's stops
            indices = [self.problem.depot_id] + assignment.stop_ids
            matrix_indices = [self._indices[node] for node in indices]
            sub_matrix = self.distance_matrix[np.ix_(matrix_indices, matrix_indices)]
            
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
        if (len(driver_routes) != self.num_drivers
                or {r.driver_id for r in driver_routes} != set(range(self.num_drivers))):
            raise ValueError("Exactly one route per driver slot is required")
        ordered = sorted(driver_routes, key=lambda r: r.driver_id)
        measured = validate_fleet_solution(self.problem, [r.route for r in ordered])
        for route, cost in zip(ordered, measured.route_distances):
            route.distance = cost
        total_distance = measured.total_distance
        longest_distance = measured.longest_route_distance
        num_stops_assigned = sum(len(r.assigned_stops) for r in ordered)
        num_stops_visited = self.problem.n_stops

        return FleetResult(
            driver_routes=driver_routes,
            total_distance=total_distance,
            longest_route_distance=longest_distance,
            num_drivers=self.num_drivers,
            num_stops_assigned=num_stops_assigned,
            num_stops_visited=num_stops_visited,
            algorithm=algorithm_name
        )
