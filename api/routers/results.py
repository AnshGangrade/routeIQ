"""
Results and comparison endpoints.
"""
from fastapi import APIRouter, HTTPException

from api.models import ComparisonResponse, MethodComparison
from api.storage import instance_store, routing_results
import math
from engine.routing.validation import validate_fleet_solution

router = APIRouter()


def verified(problem, result):
    """Cached legacy measurements remain visible, but cannot establish savings."""
    if problem is None or result is None:
        return False
    if (getattr(result,'feasible',None) is not True or getattr(result,"problem_fingerprint",None) != problem.fingerprint
            or getattr(result,"matrix_fingerprint",None) != problem.matrix_fingerprint
            or getattr(result,"distance_units",None) != problem.distance_units
            or not math.isfinite(result.total_distance) or result.total_distance < 0
            or (getattr(result,"execution",None) or {}).get('status') not in ('completed', 'incomplete')):
        return False
    try:
        drivers=sorted(result.drivers,key=lambda d:d.driver_id)
        if [d.driver_id for d in drivers] != list(range(problem.num_drivers)): return False
        measured=validate_fleet_solution(problem,[d.route for d in drivers])
        return (math.isclose(measured.total_distance,result.total_distance,rel_tol=1e-9,abs_tol=1e-9)
                and math.isclose(measured.longest_route_distance,result.longest_route_distance,rel_tol=1e-9,abs_tol=1e-9)
                and all(math.isclose(a,b.distance,rel_tol=1e-9,abs_tol=1e-9) for a,b in zip(measured.route_distances,drivers)))
    except (ValueError,TypeError,KeyError):
        return False


def completed(problem, result):
    from engine.routing.status import COMPLETE_REASONS
    execution=getattr(result,'execution',None) or {}
    return (verified(problem,result) and execution.get('status')=='completed'
        and execution.get('termination') in COMPLETE_REASONS | {'historical_baseline_complete'}
        and execution.get('search_status','completed')=='completed'
        and execution.get('schedule_completed',True) is True
        and not execution.get('budget_exhausted') and not execution.get('neighborhoods_truncated'))


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
    methods = ["nearest_neighbor", "2opt", "portfolio", "vnd", "vnd_ils", "strategy", "adaptive", "evolved"]
    comparisons = []
    nn_distance = None
    
    for method in methods:
        key = (instance_id, method)
        if key in routing_results:
            result = routing_results[key]
            problem = stored.get("problem")
            # Retain mismatches as diagnostic evidence; never authorize them for selection.
            
            # Track NN distance for improvement calculation
            if method == "nearest_neighbor" and completed(problem,result):
                nn_distance = result.total_distance
            
            # Calculate improvement if NN result exists
            improvement = None
            if nn_distance is not None and method != "nearest_neighbor" and completed(problem,result):
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
                    server_verified=verified(problem,result),
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
