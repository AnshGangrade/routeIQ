"""Simple evolution demo showing basic usage.

This example demonstrates:
- Creating an evolution configuration
- Running the evolution loop in mock mode
- Accessing results and metrics
- Multi-driver routing support
- No API key required
"""

from engine.evolution import EvolutionConfig, EvolutionLoop, EvolutionPersistence
from engine.llm.mock import MockLLMClient
from engine.llm.models import LLMConfig, LLMProvider


def main():
    """Run a simple evolution demo."""
    
    # Create conservative configuration for demo
    # Try with multiple drivers to demonstrate fleet routing
    config = EvolutionConfig(
        num_generations=3,
        candidates_per_generation=2,
        retained_candidates=1,
        training_instance_count=2,
        test_instance_count=2,
        num_stops=10,
        num_drivers=2,  # Multi-driver mode
        seed=42,
        llm_mode="mock",
    )
    
    print("Evolution Demo")
    print("=" * 60)
    print(f"Generations: {config.num_generations}")
    print(f"Candidates per generation: {config.candidates_per_generation}")
    print(f"Training instances: {config.training_instance_count}")
    print(f"Test instances: {config.test_instance_count}")
    print(f"Stops per instance: {config.num_stops}")
    print(f"Drivers: {config.num_drivers}")
    print("=" * 60)
    
    # Create mock LLM client (no API calls)
    llm_config = LLMConfig(
        provider=LLMProvider.MOCK,
        base_url="mock://local",
        model="mock-v1",
    )
    llm_client = MockLLMClient(llm_config)
    
    # Create and run evolution loop
    loop = EvolutionLoop(config=config, llm_client=llm_client)
    run = loop.run_evolution()
    
    # Print results
    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)
    
    print(f"Run ID: {run.run_id}")
    print(f"Status: {run.status}")
    
    # Generation summary
    summary = run.get_generation_summary()
    print(f"\nTotal candidates: {summary['total_candidates']}")
    print(f"Valid: {summary['total_valid']} ({summary['validity_rate']:.1%})")
    print(f"Invalid: {summary['total_invalid']}")
    
    # Best candidate
    if run.best_training_fitness:
        print(f"\nBest training fitness: {run.best_training_fitness:.2f}")
    
    # Test set comparison
    if run.test_evaluation:
        test = run.test_evaluation
        print("\nTest Set Comparison:")
        print(f"  Evolved:          {test.evolved_avg_distance:.2f}")
        print(f"  Nearest Neighbor: {test.baselines[0].avg_route_distance:.2f}")
        print(f"  2-Opt:            {test.baselines[1].avg_route_distance:.2f}")
        print(f"\n  Improvement vs NN:    {test.improvement_vs_nn_percent:+.1f}%")
        print(f"  Improvement vs 2-Opt: {test.improvement_vs_2opt_percent:+.1f}%")
    
    # Convergence history
    convergence = run.get_convergence_history()
    if convergence:
        print("\nConvergence History:")
        for i, fitness in enumerate(convergence, 1):
            print(f"  Generation {i}: {fitness:.2f}")
    
    # Save run
    persistence = EvolutionPersistence()
    persistence.save_run(run)
    print(f"\nRun saved to: runs/{run.run_id}.json")
    
    print("=" * 60)
    print("Demo complete!")


if __name__ == "__main__":
    main()
