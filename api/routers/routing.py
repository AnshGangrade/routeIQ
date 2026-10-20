"""
Routing endpoints for solving instances with different methods.
"""
import time
from fastapi import APIRouter, HTTPException

from api.models import SolveRoutingRequest, RoutingResultResponse, DriverRouteResponse
from api.storage import instance_store, routing_results
from engine.routing.fleet import FleetRouter
from engine.heuristics import nearest_distance_heuristic
from engine.sandbox import create_scoring_function

router = APIRouter()


@router.post("/solve", response_model=RoutingResultResponse)
async def solve_routing(request: SolveRoutingRequest):
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
        if not request.heuristic_code:
            raise HTTPException(
                status_code=400,
                detail="heuristic_code is required for 'evolved' method"
            )
        
        # Validate and create scoring function
        try:
            heuristic_func = create_scoring_function(
                source_code=request.heuristic_code,
                function_name="score_candidates",
                validate_first=True
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid heuristic: {str(e)}"
            )
    
    try:
        # Create fleet router
        fleet_router = FleetRouter(instance, num_drivers)
        
        # Time the routing
        start_time = time.time()
        
        # Route based on method
        if request.method == "nearest_neighbor":
            result = fleet_router.route_fleet_with_nearest_neighbor()
        elif request.method == "2opt":
            result = fleet_router.route_fleet_with_2opt()
        elif request.method == "evolved":
            result = fleet_router.route_fleet_with_heuristic(heuristic_func)
        
        computation_time = time.time() - start_time
        
        # Convert to response format
        driver_routes = [
            DriverRouteResponse(
                driver_id=dr.driver_id,
                route=dr.route,
                distance=dr.distance
            )
            for dr in result.driver_routes
        ]
        
        response = RoutingResultResponse(
            instance_id=request.instance_id,
            method=request.method,
            drivers=driver_routes,
            total_distance=result.total_distance,
            longest_route_distance=result.longest_route_distance,
            computation_time=computation_time
        )
        
        # Store result for comparison
        routing_results[(request.instance_id, request.method)] = response
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Routing failed: {str(e)}")
