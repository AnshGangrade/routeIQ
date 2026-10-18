"""
Example: Using baseline routing algorithms (Nearest Neighbor and 2-Opt).

This demonstrates:
1. Generating a delivery instance
2. Computing distance matrix
3. Running Nearest Neighbor construction
4. Improving with 2-Opt local search
5. Comparing results
"""

from engine.instances import InstanceGenerator, compute_distance_matrix
from engine.baselines import nearest_neighbor, two_opt, nearest_neighbor_with_2opt


def main():
    print("=" * 60)
    print("RouteIQ Baseline Routing Example")
    print("=" * 60)
    
    # Step 1: Generate a delivery instance
    print("\n1. Generating delivery instance...")
    generator = InstanceGenerator(seed=42)
    instance = generator.generate(n_stops=10)
    
    print(f"   Created instance with {len(instance.stops)} stops")
    print(f"   Depot: {instance.depot.location}")
    print(f"   First 3 stops: {[s.location for s in instance.stops[:3]]}")
    
    # Step 2: Compute distance matrix
    print("\n2. Computing distance matrix...")
    locations = instance.get_all_locations()
    dist_matrix = compute_distance_matrix(locations)
    print(f"   Distance matrix shape: {dist_matrix.shape}")
    
    # Step 3: Run Nearest Neighbor
    print("\n3. Running Nearest Neighbor construction...")
    nn_result = nearest_neighbor(dist_matrix)
    print(f"   Route: {nn_result.route}")
    print(f"   Total distance: {nn_result.total_distance:.2f}")
    print(f"   Algorithm: {nn_result.algorithm}")
    
    # Step 4: Improve with 2-Opt
    print("\n4. Improving with 2-Opt local search...")
    improved_result = two_opt(nn_result.route, dist_matrix, max_iterations=100)
    print(f"   Route: {improved_result.route}")
    print(f"   Total distance: {improved_result.total_distance:.2f}")
    print(f"   Algorithm: {improved_result.algorithm}")
    
    # Step 5: Run combined algorithm
    print("\n5. Running Nearest Neighbor + 2-Opt (combined)...")
    combined_result = nearest_neighbor_with_2opt(dist_matrix, max_2opt_iterations=100)
    print(f"   Route: {combined_result.route}")
    print(f"   Total distance: {combined_result.total_distance:.2f}")
    print(f"   Algorithm: {combined_result.algorithm}")
    
    # Step 6: Compare results
    print("\n6. Comparison:")
    improvement = nn_result.total_distance - improved_result.total_distance
    improvement_pct = (improvement / nn_result.total_distance) * 100
    print(f"   NN distance:        {nn_result.total_distance:.2f}")
    print(f"   NN + 2-Opt distance: {improved_result.total_distance:.2f}")
    print(f"   Improvement:         {improvement:.2f} ({improvement_pct:.1f}%)")
    
    # Verify all stops visited
    print("\n7. Verification:")
    visited = set(nn_result.route[1:-1])  # Exclude depot at start/end
    expected = set(range(1, len(instance.stops) + 1))
    print(f"   All stops visited: {visited == expected}")
    print(f"   Route starts at depot: {nn_result.route[0] == 0}")
    print(f"   Route ends at depot: {nn_result.route[-1] == 0}")
    
    print("\n" + "=" * 60)
    print("Baseline routing complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
