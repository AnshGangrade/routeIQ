"""
Example: Using the heuristic harness for route construction.

This demonstrates:
1. The heuristic contract (HeuristicContext → HeuristicResult)
2. Built-in nearest_distance_heuristic
3. Custom heuristic functions
4. RouteHarness for trusted route construction
5. Comparison with baseline algorithms
"""

from engine.instances import InstanceGenerator, compute_distance_matrix
from engine.heuristics import (
    RouteHarness,
    HeuristicContext,
    HeuristicResult,
    nearest_distance_heuristic
)
from engine.baselines import nearest_neighbor


def main():
    print("=" * 70)
    print("RouteIQ Heuristic Harness Example")
    print("=" * 70)
    
    # Step 1: Generate instance
    print("\n1. Generating delivery instance...")
    gen = InstanceGenerator(seed=42)
    instance = gen.generate(n_stops=8)
    locations = instance.get_all_locations()
    dist_matrix = compute_distance_matrix(locations)
    print(f"   Instance: {len(instance.stops)} delivery stops")
    
    # Step 2: Use built-in nearest distance heuristic
    print("\n2. Using nearest_distance_heuristic (built-in)...")
    harness = RouteHarness()
    
    nearest_result = harness.build_route(
        heuristic=nearest_distance_heuristic,
        distance_matrix=dist_matrix,
        n_stops=8,
        algorithm_name="Nearest Distance (Harness)"
    )
    print(f"   Route: {nearest_result.route}")
    print(f"   Distance: {nearest_result.total_distance:.2f}")
    
    # Step 3: Compare with Nearest Neighbor baseline
    print("\n3. Comparing with Nearest Neighbor baseline...")
    nn_result = nearest_neighbor(dist_matrix)
    print(f"   NN Route: {nn_result.route}")
    print(f"   NN Distance: {nn_result.total_distance:.2f}")
    print(f"   Routes match: {nearest_result.route == nn_result.route}")
    print(f"   Distances match: {abs(nearest_result.total_distance - nn_result.total_distance) < 1e-10}")
    
    # Step 4: Create custom heuristic (prefer farthest)
    print("\n4. Using custom 'farthest first' heuristic...")
    
    def farthest_heuristic(ctx: HeuristicContext) -> HeuristicResult:
        """
        Custom heuristic: prefer the farthest candidate.
        
        Lower scores = more preferred, so we negate distances.
        """
        scores = {
            stop: -ctx.distance_matrix[ctx.current_location, stop]
            for stop in ctx.candidate_stops
        }
        return HeuristicResult(scores=scores)
    
    farthest_result = harness.build_route(
        heuristic=farthest_heuristic,
        distance_matrix=dist_matrix,
        n_stops=8,
        algorithm_name="Farthest First (Custom)"
    )
    print(f"   Route: {farthest_result.route}")
    print(f"   Distance: {farthest_result.total_distance:.2f}")
    print(f"   Difference from NN: {farthest_result.total_distance - nn_result.total_distance:.2f}")
    
    # Step 5: Create heuristic using partial route info
    print("\n5. Using 'avoid backtracking' heuristic...")
    
    def avoid_backtracking_heuristic(ctx: HeuristicContext) -> HeuristicResult:
        """
        Heuristic that considers the partial route to avoid backtracking.
        
        If we have a partial route, prefer candidates in the same general
        direction as our previous move.
        """
        scores = {}
        
        for stop in ctx.candidate_stops:
            # Base score: distance from current location
            base_score = ctx.distance_matrix[ctx.current_location, stop]
            
            # If we have at least 2 locations in partial route, consider direction
            if len(ctx.partial_route) >= 2:
                # Previous location
                prev = ctx.partial_route[-2]
                
                # Distance from previous to current
                prev_dist = ctx.distance_matrix[prev, ctx.current_location]
                
                # Distance from previous to candidate (via current)
                via_current = prev_dist + ctx.distance_matrix[ctx.current_location, stop]
                
                # Direct distance from previous to candidate
                direct = ctx.distance_matrix[prev, stop]
                
                # Penalty if going via current is much longer (backtracking)
                if via_current > direct * 1.5:
                    base_score *= 1.2  # 20% penalty for backtracking
            
            scores[stop] = base_score
        
        return HeuristicResult(scores=scores)
    
    backtrack_result = harness.build_route(
        heuristic=avoid_backtracking_heuristic,
        distance_matrix=dist_matrix,
        n_stops=8,
        algorithm_name="Avoid Backtracking"
    )
    print(f"   Route: {backtrack_result.route}")
    print(f"   Distance: {backtrack_result.total_distance:.2f}")
    print(f"   Difference from NN: {backtrack_result.total_distance - nn_result.total_distance:.2f}")
    
    # Step 6: Summary comparison
    print("\n6. Summary Comparison:")
    print("   " + "-" * 60)
    print(f"   {'Algorithm':<30} {'Distance':>15} {'vs NN':>15}")
    print("   " + "-" * 60)
    
    results = [
        ("Nearest Neighbor (Baseline)", nn_result.total_distance, 0.0),
        ("Nearest Distance (Harness)", nearest_result.total_distance,
         nearest_result.total_distance - nn_result.total_distance),
        ("Farthest First (Custom)", farthest_result.total_distance,
         farthest_result.total_distance - nn_result.total_distance),
        ("Avoid Backtracking", backtrack_result.total_distance,
         backtrack_result.total_distance - nn_result.total_distance),
    ]
    
    for name, dist, diff in results:
        diff_str = f"+{diff:.2f}" if diff > 0 else f"{diff:.2f}"
        print(f"   {name:<30} {dist:>15.2f} {diff_str:>15}")
    
    print("   " + "-" * 60)
    
    # Step 7: Show heuristic contract
    print("\n7. Understanding the Heuristic Contract:")
    print("   " + "=" * 60)
    print("   Input (HeuristicContext):")
    print("     - current_location: Where we are now (0=depot, 1..N=stops)")
    print("     - candidate_stops: Unvisited stops that need scoring")
    print("     - distance_matrix: Full NxN distance matrix (read-only)")
    print("     - partial_route: Route built so far (read-only context)")
    print()
    print("   Output (HeuristicResult):")
    print("     - scores: Dict mapping each candidate → numeric score")
    print("     - Lower scores = more preferred candidates")
    print("     - Must provide exactly one finite score per candidate")
    print()
    print("   The harness:")
    print("     - Constructs routes by iteratively scoring candidates")
    print("     - Selects the candidate with the lowest score")
    print("     - Uses deterministic tie-breaking (lowest index)")
    print("     - Validates all heuristic outputs")
    print("     - Returns RouteResult with complete route and distance")
    print("   " + "=" * 60)
    
    print("\n" + "=" * 70)
    print("Heuristic harness demonstration complete!")
    print("=" * 70)
    print("\nKey takeaways:")
    print("  • Heuristics score candidates, harness constructs routes")
    print("  • Built-in nearest_distance reproduces Nearest Neighbor exactly")
    print("  • Custom heuristics can use any scoring logic")
    print("  • Partial route context enables sophisticated strategies")
    print("  • All heuristic outputs are validated for safety")


if __name__ == "__main__":
    main()
