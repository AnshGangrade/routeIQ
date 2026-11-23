#!/usr/bin/env python
"""CLI script to run evolution pipeline.

Usage:
    py scripts/run_evolution.py              # Run with defaults (mock mode)
    py scripts/run_evolution.py --live       # Run with live LLM calls
    py scripts/run_evolution.py --replay     # Run with replay mode
    py scripts/run_evolution.py --gens 10    # Custom number of generations
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.evolution import EvolutionConfig, EvolutionLoop, EvolutionPersistence
from engine.llm import create_client, load_config_from_env
from engine.llm.mock import MockLLMClient
from engine.llm.models import LLMConfig, LLMProvider


def parse_args(argv=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run RouteIQ evolution pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # LLM mode
    parser.add_argument(
        "--mode",
        choices=["mock", "replay", "live"],
        default="mock",
        help="LLM client mode",
    )
    parser.add_argument(
        "--live",
        action="store_const",
        const="live",
        dest="mode",
        help="Shortcut for --mode live",
    )
    parser.add_argument(
        "--replay",
        action="store_const",
        const="replay",
        dest="mode",
        help="Shortcut for --mode replay",
    )
    
    # Evolution parameters
    parser.add_argument(
        "--gens",
        "--generations",
        type=int,
        default=5,
        metavar="N",
        help="Number of generations",
    )
    parser.add_argument(
        "--candidates",
        type=int,
        default=3,
        metavar="N",
        help="Candidates per generation",
    )
    parser.add_argument(
        "--retain",
        type=int,
        default=2,
        metavar="N",
        help="Retained candidates",
    )
    
    # Instance parameters
    parser.add_argument(
        "--train-count",
        type=int,
        default=3,
        metavar="N",
        help="Number of training instances",
    )
    parser.add_argument(
        "--test-count",
        type=int,
        default=2,
        metavar="N",
        help="Number of test instances",
    )
    parser.add_argument(
        "--stops",
        type=int,
        default=15,
        metavar="N",
        help="Number of stops per instance",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        metavar="N",
        help="Random seed",
    )
    
    # Output
    parser.add_argument(
        "--runs-dir",
        default="runs",
        metavar="DIR",
        help="Directory for saving runs",
    )
    
    return parser.parse_args(argv)


def main(argv=None):
    """Main entry point."""
    args = parse_args(argv)
    
    try:
        return run(args)
    except (ValueError, RuntimeError):
        print("Invalid evolution configuration or unavailable client.")
        return 2


def run(args):
    # Create configuration
    config = EvolutionConfig(
        num_generations=args.gens,
        candidates_per_generation=args.candidates,
        retained_candidates=args.retain,
        training_instance_count=args.train_count,
        test_instance_count=args.test_count,
        num_stops=args.stops,
        seed=args.seed,
        llm_mode=args.mode,
    )
    
    # Print configuration
    print("=" * 60)
    print("RouteIQ Evolution Pipeline")
    print("=" * 60)
    print(f"Mode: {config.llm_mode}")
    print(f"Generations: {config.num_generations}")
    print(f"Candidates per generation: {config.candidates_per_generation}")
    print(f"Training instances: {config.training_instance_count} ({config.num_stops} stops)")
    print(f"Test instances: {config.test_instance_count} ({config.num_stops} stops)")
    print(f"Seed: {config.seed}")
    print("=" * 60)
    
    # Create LLM client
    if config.llm_mode == "mock":
        print("Using mock LLM client (no API calls)")
        llm_config = LLMConfig(
            provider=LLMProvider.MOCK,
            base_url="mock://local",
            model="mock-v1",
        )
        llm_client = MockLLMClient(llm_config)
    elif config.llm_mode == "replay":
        print("Using replay LLM client (cached responses)")
        llm_client = create_client(LLMConfig(provider=LLMProvider.REPLAY, base_url="replay://local", model="replay-v1", replay_fixtures=["simple_nearest", "weighted_heuristic"]))
    else:
        print("Using live LLM client (requires API key)")
        llm_client = create_client(load_config_from_env())
    
    # Run evolution
    print("\nStarting evolution...\n")
    try:
        loop = EvolutionLoop(config=config, llm_client=llm_client)
        run = loop.run_evolution()
        
        # Save results
        persistence = EvolutionPersistence(runs_dir=args.runs_dir)
        persistence.save_run(run)
        
        # Print summary
        print("\n" + "=" * 60)
        print("Evolution Complete")
        print("=" * 60)
        print(f"Run ID: {run.run_id}")
        print(f"Status: {run.status}")
        print(f"Generations: {len(run.generations)}")
        
        summary = run.get_generation_summary()
        print(f"Total candidates: {summary['total_candidates']}")
        print(f"Valid: {summary['total_valid']} ({summary['validity_rate']:.1%})")
        print(f"Invalid: {summary['total_invalid']}")
        
        if run.best_training_fitness is not None:
            print(f"\nBest training fitness: {run.best_training_fitness:.2f}")
        
        if run.test_evaluation:
            print("\nTest Set Results:")
            print(f"  Evolved: {run.test_evaluation.evolved_avg_distance:.2f}")
            print(f"  Nearest Neighbor: {run.test_evaluation.baselines[0].avg_route_distance:.2f}")
            print(f"  2-Opt: {run.test_evaluation.baselines[1].avg_route_distance:.2f}")
            print(f"  Improvement vs NN: {run.test_evaluation.improvement_vs_nn_percent:+.1f}%")
            print(f"  Improvement vs 2-Opt: {run.test_evaluation.improvement_vs_2opt_percent:+.1f}%")
        
        print(f"\nRun saved to: {args.runs_dir}/{run.run_id}.json")
        print("=" * 60)
        
        return 0 if run.status == "completed" else 1
        
    except KeyboardInterrupt:
        print("\n\nEvolution interrupted by user")
        return 1
    except Exception as e:
        print("\n\nEvolution failed; check configuration and candidate validity.")
        return 1

    finally:
        llm_client.close()


if __name__ == "__main__":
    sys.exit(main())
