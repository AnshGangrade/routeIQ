"""Multi-driver routing demonstration.

This example shows:
- Deterministic stop assignment to drivers
- Per-driver route optimization
- Fleet-level metrics aggregation
- Comparison across algorithms
"""

from engine.instances import InstanceGenerator
from engine.routing import FleetRouter
from engine.heuristics.builtin import nearest_distance_heuristic


def main():
    """Demonstrate multi-driver routing."""
    
    print("Multi-Driver Routing Demo")
    print("=" * 60)
    
    # Generate an instance
    generator = InstanceGenerator(seed=42)
    instance = generator.generate(n_stops=12)
    num_drivers = 3
    
    print(f"Instance: {instance.n_stops} stops")
    print(f"Drivers: {num_drivers}")
    print("=" * 60)
    
    # Create fleet router
    router = FleetRouter(instance, num_drivers=num_drivers)
    
    # Show stop assignments
    print("\nStop Assignments (Sweep Strategy):")
    for assignment in router.assignments:
        print(f"  Driver {assignment.driver_id}: stops {assignment.stop_ids}")
    
    # Route with Nearest Neighbor
    print("\n" + "=" * 60)
    print("Nearest Neighbor Results:")
    print("=" * 60)
    nn_result = router.route_fleet_with_nearest_neighbor()
    
    for route in nn_result.driver_routes:
        print(f"  Driver {route.driver_id}:")
        print(f"    Route: {route.route}")
        print(f"    Distance: {route.distance:.2f}")
    
    print(f"\nFleet Metrics:")
    print(f"  Total Distance: {nn_result.total_distance:.2f}")
    print(f"  Longest Route: {nn_result.longest_route_distance:.2f}")
    print(f"  Stops Visited: {nn_result.num_stops_visited}/{nn_result.num_stops_assigned}")
    
    # Route with 2-Opt
    print("\n" + "=" * 60)
    print("2-Opt Results:")
    print("=" * 60)
    opt_result = router.route_fleet_with_2opt()
    
    for route in opt_result.driver_routes:
        print(f"  Driver {route.driver_id}:")
        print(f"    Route: {route.route}")
        print(f"    Distance: {route.distance:.2f}")
    
    print(f"\nFleet Metrics:")
    print(f"  Total Distance: {opt_result.total_distance:.2f}")
    print(f"  Longest Route: {opt_result.longest_route_distance:.2f}")
    
    # Route with heuristic
    print("\n" + "=" * 60)
    print("Heuristic Results (Nearest Distance):")
    print("=" * 60)
    heur_result = router.route_fleet_with_heuristic(
        nearest_distance_heuristic,
        "Nearest Distance"
    )
    
    for route in heur_result.driver_routes:
        print(f"  Driver {route.driver_id}:")
        print(f"    Route: {route.route}")
        print(f"    Distance: {route.distance:.2f}")
    
    print(f"\nFleet Metrics:")
    print(f"  Total Distance: {heur_result.total_distance:.2f}")
    print(f"  Longest Route: {heur_result.longest_route_distance:.2f}")
    
    # Compare results
    print("\n" + "=" * 60)
    print("Comparison:")
    print("=" * 60)
    print(f"Nearest Neighbor: {nn_result.total_distance:.2f}")
    print(f"2-Opt:            {opt_result.total_distance:.2f}")
    print(f"Heuristic:        {heur_result.total_distance:.2f}")
    
    improvement_vs_nn = ((nn_result.total_distance - heur_result.total_distance) / nn_result.total_distance) * 100
    improvement_vs_opt = ((opt_result.total_distance - heur_result.total_distance) / opt_result.total_distance) * 100
    
    print(f"\nHeuristic vs NN:   {improvement_vs_nn:+.1f}%")
    print(f"Heuristic vs 2-Opt: {improvement_vs_opt:+.1f}%")
    
    print("\n" + "=" * 60)
    print("Note: All algorithms use the SAME stop assignments")
    print("=" * 60)


if __name__ == "__main__":
    main()
