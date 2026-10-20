"""
Results and comparison endpoints.
"""
from fastapi import APIRouter, HTTPException

from api.models import ComparisonResponse, MethodComparison
from api.storage import instance_store, routing_results

router = APIRouter()


@router.get("/{instance_id}/comparison", response_model=ComparisonResponse)
async def get_comparison(instance_id: str):
    """
    Get comparison of all routing methods for an instance.
    
    Returns results for all methods that have been run on this instance.
    """
    if instance_id not in instance_store:
        raise HTTPException(status_code=404, detail=f"Instance {instance_id} not found")
    
    stored = instance_store[instance_id]
    
    # Find all results for this instance
    methods = ["nearest_neighbor", "2opt", "evolved"]
    comparisons = []
    nn_distance = None
    
    for method in methods:
        key = (instance_id, method)
        if key in routing_results:
            result = routing_results[key]
            
            # Track NN distance for improvement calculation
            if method == "nearest_neighbor":
                nn_distance = result.total_distance
            
            # Calculate improvement if NN result exists
            improvement = None
            if nn_distance is not None and method != "nearest_neighbor":
                improvement = ((nn_distance - result.total_distance) / nn_distance) * 100
            
            comparisons.append(
                MethodComparison(
                    method=method,
                    total_distance=result.total_distance,
                    longest_route_distance=result.longest_route_distance,
                    computation_time=result.computation_time,
                    improvement_vs_nn=improvement
                )
            )
    
    if not comparisons:
        raise HTTPException(
            status_code=404,
            detail=f"No routing results found for instance {instance_id}"
        )
    
    return ComparisonResponse(
        instance_id=instance_id,
        num_stops=stored["response"].num_stops,
        num_drivers=stored["response"].num_drivers,
        comparisons=comparisons
    )
