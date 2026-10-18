"""
Example: Validating and executing candidate heuristics.

This demonstrates:
1. Creating candidate heuristics from source code
2. Static AST validation (allowlist-based)
3. Controlled execution with timeout
4. Integration with RouteHarness
5. Error handling for invalid candidates
"""

from engine.sandbox import (
    CandidateHeuristic,
    HeuristicValidator,
    HeuristicExecutor,
    CandidateAdapter,
    create_scoring_function,
)
from engine.instances import InstanceGenerator, compute_distance_matrix
from engine.heuristics import RouteHarness
from engine.baselines import nearest_neighbor


def main():
    print("=" * 70)
    print("RouteIQ Candidate Validation Example")
    print("=" * 70)
    
    # Step 1: Create a valid candidate heuristic
    print("\n1. Creating valid candidate heuristic...")
    
    valid_code = """
def score_candidates(context):
    '''Score by distance from current location.'''
    scores = {}
    for stop in context.candidate_stops:
        dist = context.distance_matrix[context.current_location, stop]
        scores[stop] = float(dist)
    return {"scores": scores}
"""
    
    candidate = CandidateHeuristic(source_code=valid_code)
    print(f"   Created: {candidate}")
    
    # Step 2: Validate the candidate
    print("\n2. Validating candidate heuristic...")
    validator = HeuristicValidator()
    validation = validator.validate(candidate)
    
    print(f"   Status: {validation.status.value}")
    print(f"   Errors: {len(validation.errors)}")
    print(f"   Warnings: {len(validation.warnings)}")
    
    if not validation.is_valid:
        print("   Validation failed!")
        for error in validation.errors:
            print(f"     - {error}")
        return
    
    print("   ✓ Validation passed!")
    
    # Step 3: Execute the candidate
    print("\n3. Executing candidate heuristic...")
    
    # Generate test instance
    gen = InstanceGenerator(seed=42)
    instance = gen.generate(n_stops=10)
    locations = instance.get_all_locations()
    dist_matrix = compute_distance_matrix(locations)
    
    # Use adapter to integrate with harness
    adapter = CandidateAdapter(candidate)
    adapter.validate()  # Already validated, but adapter tracks this
    
    harness = RouteHarness()
    result = harness.build_route(
        heuristic=adapter.create_callable(),
        distance_matrix=dist_matrix,
        n_stops=10,
        algorithm_name="Valid Candidate"
    )
    
    print(f"   Route: {result.route}")
    print(f"   Distance: {result.total_distance:.2f}")
    
    # Compare with baseline
    nn_result = nearest_neighbor(dist_matrix)
    print(f"   NN Distance: {nn_result.total_distance:.2f}")
    print(f"   Match: {result.route == nn_result.route}")
    
    # Step 4: Demonstrate validation rejection
    print("\n4. Testing validation rejection...")
    print("   " + "-" * 60)
    
    invalid_examples = [
        ("Import statement", """
import os
def score_candidates(context):
    return {"scores": {}}
"""),
        ("File I/O", """
def score_candidates(context):
    with open('/etc/passwd') as f:
        data = f.read()
    return {"scores": {}}
"""),
        ("Forbidden eval", """
def score_candidates(context):
    x = eval("1 + 1")
    return {"scores": {}}
"""),
        ("Underscore attribute", """
def score_candidates(context):
    x = context.__dict__
    return {"scores": {}}
"""),
        ("Context modification", """
def score_candidates(context):
    context.current_location = 999
    return {"scores": {}}
"""),
        ("Nested function", """
def score_candidates(context):
    def helper():
        return 5
    return {"scores": {}}
"""),
    ]
    
    for name, code in invalid_examples:
        candidate = CandidateHeuristic(source_code=code)
        validation = validator.validate(candidate)
        status = "✗ REJECTED" if not validation.is_valid else "✓ ACCEPTED"
        print(f"   {name:<25} {status}")
        if not validation.is_valid and validation.errors:
            print(f"     → {validation.errors[0][:60]}...")
    
    print("   " + "-" * 60)
    
    # Step 5: Demonstrate execution error handling
    print("\n5. Testing execution error handling...")
    print("   " + "-" * 60)
    
    # Runtime error
    runtime_error_code = """
def score_candidates(context):
    x = 1 / 0  # Division by zero
    return {"scores": {}}
"""
    
    candidate = CandidateHeuristic(source_code=runtime_error_code)
    validation = validator.validate(candidate)
    print(f"   Runtime error - Validation: {'PASS' if validation.is_valid else 'FAIL'}")
    
    if validation.is_valid:
        executor = HeuristicExecutor(timeout=5.0)
        from engine.heuristics import HeuristicContext
        import numpy as np
        
        test_ctx = HeuristicContext(
            current_location=0,
            candidate_stops=[1],
            distance_matrix=np.array([[0, 10], [10, 0]], dtype=float),
            partial_route=[0]
        )
        
        exec_result = executor.execute(candidate, test_ctx)
        print(f"   Runtime error - Execution: {exec_result.status.value}")
        print(f"     → {exec_result.error}")
    
    # Invalid output
    invalid_output_code = """
def score_candidates(context):
    return "not a dict"
"""
    
    candidate = CandidateHeuristic(source_code=invalid_output_code)
    validation = validator.validate(candidate)
    print(f"\n   Invalid output - Validation: {'PASS' if validation.is_valid else 'FAIL'}")
    
    if validation.is_valid:
        executor = HeuristicExecutor(timeout=5.0)
        exec_result = executor.execute(candidate, test_ctx)
        print(f"   Invalid output - Execution: {exec_result.status.value}")
        print(f"     → {exec_result.error}")
    
    print("   " + "-" * 60)
    
    # Step 6: Demonstrate convenience function
    print("\n6. Using convenience function...")
    
    convenience_code = """
def score_candidates(context):
    '''Prefer stops closer to depot.'''
    scores = {}
    for stop in context.candidate_stops:
        current_dist = context.distance_matrix[context.current_location, stop]
        depot_dist = context.distance_matrix[stop, 0]
        scores[stop] = current_dist * 0.7 + depot_dist * 0.3
    return {"scores": scores}
"""
    
    try:
        scorer = create_scoring_function(convenience_code, timeout=5.0)
        result = harness.build_route(
            heuristic=scorer,
            distance_matrix=dist_matrix,
            n_stops=10,
            algorithm_name="Depot-Aware"
        )
        print(f"   ✓ Created scoring function successfully")
        print(f"   Route distance: {result.total_distance:.2f}")
        diff = result.total_distance - nn_result.total_distance
        print(f"   vs NN: {diff:+.2f}")
    except ValueError as e:
        print(f"   ✗ Failed: {e}")
    
    # Step 7: Summary
    print("\n7. Security & Limitations:")
    print("   " + "=" * 60)
    print("   Safety features:")
    print("     • Static AST validation (allowlist-based)")
    print("     • Restricted namespace (minimal built-ins)")
    print("     • Timeout enforcement")
    print("     • Structured error handling")
    print()
    print("   Limitations (by design):")
    print("     • This is defense-in-depth, NOT a security boundary")
    print("     • Suitable for academic demo, not production use")
    print("     • Do not execute truly malicious code")
    print("     • Do not run on public servers without additional isolation")
    print("   " + "=" * 60)
    
    print("\n" + "=" * 70)
    print("Candidate validation demonstration complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
