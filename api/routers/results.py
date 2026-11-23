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
    methods = ["nearest_neighbor", "2opt", "portfolio", "vnd", "vnd_ils", "strategy", "evolved"]
    comparisons = []
    nn_distance = None
    
    for method in methods:
        key = (instance_id, method)
        if key in routing_results:
            result = routing_results[key]
            problem = stored.get("problem")
            if problem is not None and (
                    getattr(result, "problem_fingerprint", None) not in (None, problem.fingerprint)
                    or getattr(result, "matrix_fingerprint", None) not in (None, problem.matrix_fingerprint)):
                raise HTTPException(409, "Cached routes do not match the selected problem matrix; recalculate")
            
            # Track NN distance for improvement calculation
            if method == "nearest_neighbor":
                nn_distance = result.total_distance
            
            # Calculate improvement if NN result exists
            improvement = None
            if nn_distance is not None and method != "nearest_neighbor":
                if nn_distance > 0:
                    improvement = ((nn_distance - result.total_distance) / nn_distance) * 100
                elif result.total_distance == 0:
                    improvement = 0.0
            
            comparisons.append(
                MethodComparison(
                    method=method,
                    total_distance=result.total_distance,
                    longest_route_distance=result.longest_route_distance,
                    computation_time=result.computation_time,
                    improvement_vs_nn=improvement,
                    optimization=getattr(result, "optimization", None),
                    problem_fingerprint=getattr(result, "problem_fingerprint", None),
                    matrix_fingerprint=getattr(result, "matrix_fingerprint", None),
                    distance_units=getattr(result, "distance_units", None),
                    feasible=getattr(result, "feasible", None),
                    drivers=getattr(result, "drivers", []),
                    execution=getattr(result, "execution", None),
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
        comparisons=comparisons,
        problem_fingerprint=stored["problem"].fingerprint if stored.get("problem") else None,
        matrix_fingerprint=stored["problem"].matrix_fingerprint if stored.get("problem") else None,
    )
