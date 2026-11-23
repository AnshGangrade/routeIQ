"""
Instance generation and retrieval endpoints.
"""
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool
import uuid
import logging
from api import storage
from typing import Dict

from api.models import GenerateInstanceRequest, InstanceResponse, StopResponse, DriverResponse
from engine.instances import InstanceGenerator
from engine.routing.adapters import problem_from_instance, problem_from_road_result
from engine.routing.problem import MatrixProvenance
from api.storage import instance_store

router = APIRouter()

# Predefined driver colors for visualization
DRIVER_COLORS = [
    "#2563eb",  # blue
    "#dc2626",  # red
    "#16a34a",  # green
    "#ca8a04",  # yellow
    "#9333ea",  # purple
    "#ea580c",  # orange
    "#0891b2",  # cyan
    "#be123c",  # rose
    "#65a30d",  # lime
    "#7c3aed",  # violet
]


@router.post("", response_model=InstanceResponse)
async def create_instance(request: GenerateInstanceRequest):
    with storage.expensive_request():
        return await run_in_threadpool(_create_instance, request)


def _create_instance(request: GenerateInstanceRequest):
    """
    Generate a new routing instance.
    
    Modes:
    - 'synthetic': Generate random coordinates in 0-100 space (default)
    - 'road': Use real geographic coordinates and road network distances
    
    For road mode, provide depot_coords and stop_coords as [lon, lat] pairs.
    """
    with storage.storage_lock:
        if len(instance_store) >= storage.MAX_INSTANCES:
            raise HTTPException(status_code=429, detail="Instance capacity reached; restart the local server to clear retained instances")
    try:
        mode = request.mode.lower()
        
        if mode == "synthetic":
            # Generate synthetic instance
            generator = InstanceGenerator(seed=request.seed)
            instance = generator.generate(
                n_stops=request.num_stops,
                distribution=request.layout
            )
            
            # Create instance ID
            instance_id = f"inst_{uuid.uuid4().hex}"
            
            # Convert stops to response format
            stops = [
                StopResponse(
                    stop_id=stop.id,
                    x=stop.location.x,
                    y=stop.location.y
                )
                for stop in instance.stops
            ]
            
            # Store using Euclidean distances
            from engine.instances import compute_distance_matrix
            distance_matrix = compute_distance_matrix(instance.get_all_locations())
            
            response_data = {
                "instance_id": instance_id,
                "seed": instance.seed,
                "num_stops": request.num_stops,
                "num_drivers": request.num_drivers,
                "layout": request.layout,
                "mode": "synthetic",
                "depot": {"x": instance.depot.location.x, "y": instance.depot.location.y},
                "stops": stops,
                "drivers": [],
                "road_routing_info": None
            }
            
        elif mode == "road":
            if request.num_stops > 99:
                raise HTTPException(status_code=400, detail="Road mode supports 5–99 stops (plus one depot)")
            # Validate road mode inputs
            if not request.depot_coords or not request.stop_coords:
                raise HTTPException(
                    status_code=400,
                    detail="Road mode requires depot_coords and stop_coords"
                )
            
            if len(request.stop_coords) != request.num_stops:
                raise HTTPException(
                    status_code=400,
                    detail=f"stop_coords length ({len(request.stop_coords)}) must match num_stops ({request.num_stops})"
                )
            
            # Validate coordinates
            from engine.road.adapter import validate_geographic_coordinates
            all_coords = [tuple(request.depot_coords)] + [tuple(c) for c in request.stop_coords]
            
            is_valid, error_msg = validate_geographic_coordinates(all_coords)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid coordinates: {error_msg}")
            
            # Get road distances
            from engine.road import create_road_distance_matrix
            
            distance_matrix, road_result = create_road_distance_matrix(all_coords)
            
            if not road_result.success:
                # Return HTTP 503 for service failures (OSRM unavailable, network issues)
                # This must not be caught by the outer exception handler
                raise HTTPException(
                    status_code=503,
                    detail="Road routing service unavailable or returned an invalid distance matrix"
                )
            
            # Road routing succeeded - create instance
            instance_id = f"road_{uuid.uuid4().hex}"
            
            # Convert stops to response format (use lon/lat)
            stops = [
                StopResponse(
                    stop_id=i + 1,
                    x=coord[0],  # longitude
                    y=coord[1]   # latitude
                )
                for i, coord in enumerate(request.stop_coords)
            ]
            
            # Create synthetic instance for storage (algorithms need it)
            from engine.instances.models import DeliveryInstance, Stop, Point
            depot_stop = Stop(id=0, location=Point(x=request.depot_coords[0], y=request.depot_coords[1]), label="Depot")
            stops_list = [
                Stop(id=i+1, location=Point(x=coord[0], y=coord[1]), label=f"Stop {i+1}")
                for i, coord in enumerate(request.stop_coords)
            ]
            instance = DeliveryInstance(
                seed=request.seed or 0,
                depot=depot_stop,
                stops=stops_list,
                n_stops=request.num_stops
            )
            
            response_data = {
                "instance_id": instance_id,
                "seed": request.seed or 0,
                "num_stops": request.num_stops,
                "num_drivers": request.num_drivers,
                "layout": "road",
                "mode": "road",
                "depot": {"lon": request.depot_coords[0], "lat": request.depot_coords[1]},
                "stops": stops,
                "drivers": [],
                "road_routing_info": {
                    "provider": road_result.provider,
                    "cache_hit": road_result.cache_hit,
                    "metadata": road_result.metadata
                }
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode '{mode}'. Must be 'synthetic' or 'road'"
            )
        
        problem = (problem_from_road_result(instance, request.num_drivers, road_result)
                   if mode == "road" else problem_from_instance(
                       instance, request.num_drivers, distance_matrix=distance_matrix,
                       provenance=MatrixProvenance(source="euclidean", provider="routeiq")))
        if request.workload is not None:
            try:
                problem = type(problem).model_validate({**problem.model_dump(), "workload": request.workload})
            except ValueError:
                raise HTTPException(422, "Workload must be feasible within floor(stops/drivers)..ceil(stops/drivers)") from None
        response_data.update(problem_fingerprint=problem.fingerprint, matrix_fingerprint=problem.matrix_fingerprint,
                             distance_units=problem.distance_units, workload=problem.workload)
        # Create drivers (common for both modes)
        drivers = [
            DriverResponse(
                driver_id=i,
                name=f"Driver {i+1}",
                color=DRIVER_COLORS[i % len(DRIVER_COLORS)],
                assigned_stops=[]
            )
            for i in range(request.num_drivers)
        ]
        response_data["drivers"] = drivers
        
        response = InstanceResponse(**response_data)
        
        # Store instance data for later retrieval
        storage_data = {
            "problem": problem,
            "instance": instance,
            "num_drivers": request.num_drivers,
            "response": response,
            "distance_matrix": problem.matrix_array(),
            "mode": mode
        }
        
        # Add coordinates for road mode (needed for geometry retrieval)
        if mode == "road":
            storage_data["depot_coords"] = request.depot_coords
            storage_data["stop_coords"] = request.stop_coords
        
        with storage.storage_lock:
            if len(instance_store) >= storage.MAX_INSTANCES:
                raise HTTPException(status_code=429, detail="Instance capacity reached")
            instance_store[response.instance_id] = storage_data
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).warning("instance_creation_failed", extra={"error_type": type(e).__name__})
        raise HTTPException(status_code=500, detail="Failed to create instance") from None


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(instance_id: str):
    """
    Retrieve a previously generated instance.
    """
    if instance_id not in instance_store:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    return instance_store[instance_id]["response"]
