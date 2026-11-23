"""
Routing endpoints for solving instances with different methods.
"""
import time
import logging
import math
import numpy as np
from api import storage
from typing import List, Tuple
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from api.models import SolveRoutingRequest, RoutingResultResponse, DriverRouteResponse
from api.storage import instance_store, routing_results, evolution_runs
from engine.routing.fleet import FleetRouter
from engine.routing.incumbent import select_incumbent
from engine.routing.adapters import problem_from_instance
from engine.routing.problem import MatrixProvenance
from engine.heuristics import nearest_distance_heuristic
from engine.sandbox import create_scoring_function
from engine.road.osrm import OSRMClient, RoadRoutingConfig

router = APIRouter()


def get_route_geometry_if_road(
    instance_data: dict,
    route_sequence: List[int]
) -> Tuple[List[List[float]] | None, float | None, str | None]:
    """
    Get OSRM route geometry for a route sequence if in road mode.
    
    Args:
        instance_data: Stored instance data
        route_sequence: List of stop IDs (0 = depot)
        
    Returns:
        (geometry, duration, error) tuple
        - geometry: List of [lat, lon] coordinates or None
        - duration: Time in seconds or None
        - error: Error message if geometry fetch failed, None if not road mode or success
    """
    if instance_data.get("mode") != "road":
        return None, None, None
    
    instance = instance_data["instance"]
    
    # Build coordinate sequence for OSRM route request
    coordinates: List[Tuple[float, float]] = []
    
    for stop_id in route_sequence:
        if stop_id == 0:
            # Depot
            depot_coords = instance_data.get("depot_coords")
            if depot_coords and len(depot_coords) >= 2:
                coordinates.append((depot_coords[0], depot_coords[1]))  # lon, lat
        else:
            # Find stop coordinates
            stop_coords = instance_data.get("stop_coords", [])
            if stop_id - 1 < len(stop_coords):
                coord = stop_coords[stop_id - 1]
                if len(coord) >= 2:
                    coordinates.append((coord[0], coord[1]))  # lon, lat
    
    if len(coordinates) < 2:
        return None, None, "Route has fewer than 2 coordinates"
    
    # Request route geometry from OSRM
    try:
        config = RoadRoutingConfig()
        with OSRMClient(config) as client:
            result = client.get_route(coordinates, overview="full")
            
            if "error" in result:
                error_msg = "OSRM route geometry error: service unavailable"
                logging.getLogger(__name__).warning("road_geometry_unavailable")
                return None, None, error_msg
            
            geometry = result.get("geometry")
            duration = result.get("duration")
            
            if not geometry:
                return None, None, "OSRM returned no geometry"
            if any(len(point) != 2 or not all(math.isfinite(value) for value in point)
                   or abs(point[0]) > 90 or abs(point[1]) > 180 for point in geometry):
                return None, None, "OSRM returned invalid geometry"
            if duration is not None and (not math.isfinite(duration) or duration < 0):
                return None, None, "OSRM returned invalid duration"
            
            return geometry, duration, None
    except Exception as e:
        error_msg = "Failed to get route geometry"
        logging.getLogger(__name__).warning("road_geometry_failed")
        return None, None, error_msg


@router.post("/solve", response_model=RoutingResultResponse)
async def solve_routing(request: SolveRoutingRequest):
    with storage.expensive_request():
        return await run_in_threadpool(_solve_routing, request)


def _solve_routing(request: SolveRoutingRequest):
    """
    Solve routing for an instance using the specified method.
    
    Methods:
    - 'nearest_neighbor': Nearest neighbor construction
    - '2opt': Nearest neighbor + 2-Opt improvement
    - 'evolved': Use a custom evolved heuristic (requires heuristic_code)
    """
    # Retrieve instance
    if request.instance_id not in instance_store:
        raise HTTPException(status_code=404, detail=f"Instance {request.instance_id} not found")
    
    stored = instance_store[request.instance_id]
    instance = stored["instance"]
    num_drivers = stored["num_drivers"]
    
    # Validate method
    valid_methods = ["nearest_neighbor", "2opt", "evolved"]
    if request.method not in valid_methods:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid method '{request.method}'. Must be one of: {valid_methods}"
        )
    
    # For evolved method, validate and create heuristic
    heuristic_func = None
    if request.method == "evolved":
        code = request.heuristic_code
        if request.run_id:
            run = evolution_runs.get(request.run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="Evolution run not found")
            if run["status"] != "completed":
                raise HTTPException(status_code=409, detail="Only a completed evolution winner can be applied")
            code = run.get("best_code")
        if not code:
            raise HTTPException(
                status_code=400,
                detail="heuristic_code is required for 'evolved' method"
            )
        
        # Delay validation until baselines exist so invalid candidates fall back
        # transparently instead of discarding a usable route plan.
        def heuristic_func():
            return create_scoring_function(
                source_code=code,
                function_name="score_candidates",
                validate_first=True
            )
    
    try:
        # Create fleet router with stored distance matrix
        distance_matrix = stored.get("distance_matrix")
        if distance_matrix is None:
            raise ValueError("Distance matrix not found in stored instance")
        
        problem = stored.get("problem")
        if problem is not None and (
                instance.depot.id != problem.depot_id
                or tuple(stop.id for stop in instance.stops) != problem.stop_ids
                or instance.n_stops != problem.n_stops or num_drivers != problem.num_drivers
                or not np.array_equal(distance_matrix, problem.matrix_array())
                or tuple((p.x, p.y) for p in instance.get_all_locations()) != problem.coordinates):
            raise ValueError("Stored instance does not match its canonical problem")
        if problem is None:
            # Explicit compatibility adapter for pre-contract in-memory records.
            road = stored.get("mode") == "road"
            problem = problem_from_instance(
                instance, num_drivers, distance_matrix=distance_matrix,
                distance_units="meters" if road else "map_units",
                coordinate_system="lon_lat" if road else "cartesian",
                directed=True if road else None,
                provenance=MatrixProvenance(source="road" if road else "provided"))
        fleet_router = FleetRouter(problem)
        
        # Time the routing
        start_time = time.time()
        optimization = None
        
        # Route based on method
        if request.method == "nearest_neighbor":
            result = fleet_router.route_fleet_with_nearest_neighbor()
        elif request.method == "2opt":
            result = fleet_router.route_fleet_with_2opt()
        elif request.method == "evolved":
            result, optimization = select_incumbent(fleet_router, heuristic_func)
        
        computation_time = time.time() - start_time
        
        # Get route geometry if in road mode
        driver_routes = []
        geometry_errors = []
        
        for dr in result.driver_routes:
            geometry, duration, geo_error = (None, None, None) if request.preview else get_route_geometry_if_road(stored, dr.route)
            
            if geo_error:
                geometry_errors.append(f"Driver {dr.driver_id}: {geo_error}")
            
            driver_routes.append(
                DriverRouteResponse(
                    driver_id=dr.driver_id,
                    route=dr.route,
                    distance=dr.distance,
                    duration=duration,
                    geometry=geometry,
                    geometry_error=geo_error
                )
            )
        
        # If in road mode but geometry fetch failed, include warning
        if stored.get("mode") == "road" and geometry_errors:
            logging.getLogger(__name__).warning("road_geometry_incomplete")
            # Continue with distance-based routes but log the issue
        
        response = RoutingResultResponse(
            instance_id=request.instance_id,
            method=request.method,
            drivers=driver_routes,
            total_distance=result.total_distance,
            longest_route_distance=result.longest_route_distance,
            computation_time=computation_time,
            optimization=optimization,
            run_id=request.run_id if request.method == "evolved" else None,
            problem_fingerprint=problem.fingerprint,
            matrix_fingerprint=problem.matrix_fingerprint,
            distance_units=problem.distance_units,
            feasible=True,
            execution={"status": "completed", "termination": "historical_baseline_complete" if request.method != "evolved" else "legacy_selection_complete",
                       "operations": None, "budget_exhausted": False},
        )
        
        # Store result for comparison
        if not request.preview:
            routing_results[(request.instance_id, request.method)] = response
        
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Routing failed: invalid matrix, instance, or heuristic result")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Routing failed: invalid matrix, instance, or heuristic result")
