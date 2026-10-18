"""
Simple example demonstrating instance generation and distance calculations.

This script shows how to:
1. Generate a synthetic delivery instance
2. Compute the distance matrix
3. Calculate route costs

Run: py examples/simple_instance.py
"""

from engine.instances import (
    InstanceGenerator,
    compute_distance_matrix,
    calculate_route_cost,
)


def main():
    print("=" * 60)
    print("RouteIQ: Synthetic Instance Generation Example")
    print("=" * 60)
    print()
    
    # Generate a small instance with fixed seed for reproducibility
    print("1. Generating instance with 5 stops (seed=42)...")
    generator = InstanceGenerator(seed=42)
    instance = generator.generate(n_stops=5)
    
    print(f"   Depot: {instance.depot.location}")
    for stop in instance.stops:
        print(f"   {stop.label}: {stop.location}")
    print()
    
    # Compute distance matrix
    print("2. Computing distance matrix...")
    locations = instance.get_all_locations()
    distance_matrix = compute_distance_matrix(locations)
    
    print(f"   Matrix shape: {distance_matrix.shape}")
    print(f"   Depot to Stop 1: {distance_matrix[0, 1]:.2f}")
    print(f"   Stop 1 to Stop 2: {distance_matrix[1, 2]:.2f}")
    print()
    
    # Calculate route costs
    print("3. Calculating route costs...")
    
    # Simple round trip: depot -> stop1 -> stop2 -> depot
    route1 = [0, 1, 2, 0]
    cost1 = calculate_route_cost(route1, distance_matrix)
    print(f"   Route {route1}: {cost1:.2f}")
    
    # All stops in order
    route2 = [0, 1, 2, 3, 4, 5, 0]
    cost2 = calculate_route_cost(route2, distance_matrix)
    print(f"   Route {route2}: {cost2:.2f}")
    
    print()
    print("=" * 60)
    print("Done! Instance generation and distance calculations work.")
    print("=" * 60)


if __name__ == "__main__":
    main()
