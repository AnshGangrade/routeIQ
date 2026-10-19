"""
Demonstration of heuristic evaluation, fitness scoring, and selection.

Shows the complete evaluation pipeline from candidate to selection.

Usage:
    $env:PYTHONPATH="D:\routeIQ" ; py examples/evaluation_demo.py
"""

from engine.instances import InstanceGenerator
from engine.sandbox import CandidateHeuristic
from engine.evaluation import (
    HeuristicEvaluator,
    FitnessFunction,
    CandidateSelector,
    prepare_feedback,
)


def demo_evaluate_candidate():
    """Demonstrate evaluating a single candidate."""
    print("=" * 80)
    print("DEMO 1: Evaluate Single Candidate")
    print("=" * 80)
    
    # Generate test instances
    print("\n1. Generating test instances...")
    generator = InstanceGenerator(seed=200)
    instances = generator.generate_batch(n_instances=5, n_stops=8, start_seed=200)
    print(f"Generated {len(instances)} instances with {instances[0].n_stops} stops each")
    
    # Create a valid candidate
    print("\n2. Creating candidate heuristic...")
    code = """
def score_candidates(context):
    '''Simple nearest-neighbor heuristic.'''
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
"""
    candidate = CandidateHeuristic(source_code=code, function_name="score_candidates")
    print("Candidate created: nearest-distance scoring")
    
    # Evaluate
    print("\n3. Evaluating candidate...")
    evaluator = HeuristicEvaluator()
    result = evaluator.evaluate_candidate(
        candidate=candidate,
        instances=instances,
        candidate_id="demo_001",
        algorithm_name="Demo Nearest Distance"
    )
    
    print(f"\nResults:")
    print(f"- Candidate ID: {result.candidate_id}")
    print(f"- Instances evaluated: {result.instances_evaluated}")
    print(f"- Successful: {result.successful_evaluations}")
    print(f"- Failed: {result.failed_evaluations}")
    print(f"- Success rate: {result.success_rate * 100:.1f}%")
    print(f"- Mean distance: {result.mean_distance:.2f}")
    print(f"- Median distance: {result.median_distance:.2f}")
    print(f"- Total time: {result.total_execution_time:.3f}s")


def demo_compare_with_baselines():
    """Demonstrate comparing candidate with baselines."""
    print("\n" + "=" * 80)
    print("DEMO 2: Compare with Baselines")
    print("=" * 80)
    
    # Generate instances
    print("\n1. Generating test instances...")
    generator = InstanceGenerator(seed=300)
    instances = generator.generate_batch(n_instances=3, n_stops=6, start_seed=300)
    print(f"Generated {len(instances)} instances")
    
    # Create candidate
    code = """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
"""
    candidate = CandidateHeuristic(source_code=code)
    
    # Evaluate
    print("\n2. Evaluating candidate and baselines...")
    evaluator = HeuristicEvaluator()
    
    candidate_result = evaluator.evaluate_candidate(
        candidate=candidate,
        instances=instances,
        candidate_id="demo_002"
    )
    
    comparison = evaluator.compare_with_baselines(
        candidate_result=candidate_result,
        instances=instances
    )
    
    print(f"\nComparison Results:")
    print(f"\n- Candidate mean distance: {comparison.candidate_result.mean_distance:.2f}")
    print(f"- NN baseline mean: {comparison.baseline_nn_result.mean_distance:.2f}")
    print(f"- NN+2-Opt baseline mean: {comparison.baseline_2opt_result.mean_distance:.2f}")
    
    if comparison.improvement_vs_nn is not None:
        sign = "better" if comparison.improvement_vs_nn > 0 else "worse"
        print(f"\n- vs Nearest Neighbor: {abs(comparison.improvement_vs_nn):.1f}% {sign}")
    
    if comparison.improvement_vs_2opt is not None:
        sign = "better" if comparison.improvement_vs_2opt > 0 else "worse"
        print(f"- vs NN+2-Opt: {abs(comparison.improvement_vs_2opt):.1f}% {sign}")


def demo_fitness_and_selection():
    """Demonstrate fitness calculation and candidate selection."""
    print("\n" + "=" * 80)
    print("DEMO 3: Fitness Scoring and Selection")
    print("=" * 80)
    
    # Generate instances
    print("\n1. Generating test instances...")
    generator = InstanceGenerator(seed=400)
    instances = generator.generate_batch(n_instances=4, n_stops=5, start_seed=400)
    
    # Create multiple candidates with different behaviors
    candidates = {
        "good": """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
""",
        "mediocre": """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        # Add some noise to distances
        dist = context.distance_matrix[context.current_location, stop]
        scores[stop] = dist * 1.2  # Make it slightly worse
    return {"scores": scores}
""",
        "poor": """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        # Farthest first (usually bad)
        scores[stop] = -context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
""",
    }
    
    # Evaluate all candidates
    print("\n2. Evaluating candidates...")
    evaluator = HeuristicEvaluator()
    results = []
    
    for name, code in candidates.items():
        candidate = CandidateHeuristic(source_code=code)
        result = evaluator.evaluate_candidate(
            candidate=candidate,
            instances=instances,
            candidate_id=name,
            algorithm_name=f"Candidate {name.title()}"
        )
        results.append(result)
        print(f"- {name}: mean distance = {result.mean_distance:.2f}")
    
    # Calculate fitness
    print("\n3. Calculating fitness scores...")
    fitness_fn = FitnessFunction()
    fitness_scores = fitness_fn.calculate_batch(results)
    
    print("Fitness scores (lower is better):")
    for name, score in fitness_scores.items():
        if score == float('inf'):
            print(f"- {name}: inf (failed)")
        else:
            print(f"- {name}: {score:.2f}")
    
    # Select best
    print("\n4. Selecting best candidate...")
    selector = CandidateSelector(fitness_function=fitness_fn)
    selection = selector.select_best(results, n_select=1)
    
    best_id = selection.selected_candidates[0]
    best_fitness = selection.fitness_scores[best_id]
    print(f"\nSelected: {best_id}")
    print(f"Fitness: {best_fitness:.2f}")
    print(f"Rankings: {selection.rankings}")


def demo_feedback_preparation():
    """Demonstrate preparing feedback for LLM iteration."""
    print("\n" + "=" * 80)
    print("DEMO 4: Feedback Preparation")
    print("=" * 80)
    
    # Generate instances
    print("\n1. Generating test instances...")
    generator = InstanceGenerator(seed=500)
    instances = generator.generate_batch(n_instances=4, n_stops=6, start_seed=500)
    
    # Create and evaluate candidate
    code = """
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
"""
    candidate = CandidateHeuristic(source_code=code)
    
    print("\n2. Evaluating and comparing...")
    evaluator = HeuristicEvaluator()
    result = evaluator.evaluate_candidate(
        candidate=candidate,
        instances=instances,
        candidate_id="demo_005"
    )
    
    comparison = evaluator.compare_with_baselines(
        candidate_result=result,
        instances=instances
    )
    
    # Calculate fitness
    fitness_fn = FitnessFunction()
    fitness = fitness_fn.calculate(result)
    
    # Prepare feedback
    print("\n3. Preparing structured feedback...")
    feedback = prepare_feedback(comparison, fitness)
    
    print(f"\nStructured Feedback:")
    print(f"- Candidate ID: {feedback.candidate_id}")
    print(f"- Fitness: {feedback.fitness_score:.2f}")
    print(f"- Success rate: {feedback.success_rate * 100:.1f}%")
    print(f"- Mean distance: {feedback.mean_distance:.2f}")
    print(f"- Improvement vs NN: {feedback.improvement_vs_nn:+.1f}%")
    print(f"- Improvement vs NN+2-Opt: {feedback.improvement_vs_2opt:+.1f}%")
    
    # Convert to text for LLM prompt
    print("\n4. Converting to feedback text...")
    feedback_text = feedback.to_feedback_text()
    print("\n" + "-" * 80)
    print(feedback_text)
    print("-" * 80)


def main():
    """Run all demonstrations."""
    print("\n")
    print("=" * 80)
    print(" " * 20 + "Evaluation System Demo")
    print("=" * 80)
    print()
    print("This demo shows:")
    print("  1. Evaluating a candidate on benchmark instances")
    print("  2. Comparing with baseline algorithms")
    print("  3. Fitness scoring and candidate selection")
    print("  4. Feedback preparation for LLM iteration")
    print("=" * 80)
    
    try:
        demo_evaluate_candidate()
        demo_compare_with_baselines()
        demo_fitness_and_selection()
        demo_feedback_preparation()
        
        print("\n" + "=" * 80)
        print("All demos completed successfully!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
