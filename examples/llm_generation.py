"""
Demonstration of LLM heuristic generation with mock, replay, and live modes.

This example shows how to use the LLM client to generate candidate heuristics
for route optimization without making live API calls during development.

Usage:
    $env:PYTHONPATH="D:\routeIQ" ; py examples/llm_generation.py
"""

import numpy as np
from pathlib import Path

from engine.llm import (
    LLMProvider,
    LLMConfig,
    GenerationRequest,
    create_client,
    build_generation_prompt,
    parse_llm_response,
)
from engine.sandbox import HeuristicValidator, CandidateHeuristic
from engine.sandbox import HeuristicExecutor
from engine.heuristics import HeuristicContext
from engine.instances import DeliveryInstance, InstanceGenerator


def demo_mock_mode():
    """
    Demonstrate mock mode: predefined candidates without API calls.
    
    Mock mode is useful for:
    - Testing without API keys
    - Deterministic test runs
    - Quick validation of downstream processing
    """
    print("=" * 80)
    print("DEMO 1: Mock Mode (Predefined Candidates)")
    print("=" * 80)
    
    # Configure mock mode
    config = LLMConfig(
        provider=LLMProvider.MOCK,
        base_url="mock://local",
        model="mock-v1",
        temperature=0.7
    )
    
    print(f"\nConfig: {config}")
    
    # Create client
    with create_client(config) as client:
        print(f"Client: {client}")
        
        # Generate using specific mock candidate
        print("\n1. Generating 'nearest_distance' heuristic...")
        request = GenerationRequest(
            prompt="Generate a routing heuristic",
            generation_id="mock_demo_1",
            metadata={"candidate_key": "nearest_distance"}
        )
        
        response = client.generate(request)
        print(f"Response: {len(response.raw_content)} characters")
        print(f"Mock candidate: {response.metadata.get('mock_candidate')}")
        
        # Parse the response
        parse_result = parse_llm_response(response)
        print(f"\nParse result: {parse_result}")
        
        if parse_result.success:
            print(f"Function: {parse_result.function_name}")
            print(f"Source preview: {parse_result.source_code[:100]}...")
            
            # Validate
            candidate = CandidateHeuristic(
                source_code=parse_result.source_code,
                function_name=parse_result.function_name
            )
            
            validator = HeuristicValidator()
            validation = validator.validate(candidate)
            print(f"\nValidation: {validation}")
        else:
            print(f"Parse errors: {parse_result.errors}")
        
        # Generate another (will cycle to next candidate)
        print("\n2. Generating next candidate (auto-cycle)...")
        request = GenerationRequest(
            prompt="Generate another heuristic",
            generation_id="mock_demo_2"
        )
        
        response = client.generate(request)
        print(f"Mock candidate: {response.metadata.get('mock_candidate')}")


def demo_replay_mode():
    """
    Demonstrate replay mode: load from saved fixtures.
    
    Replay mode is useful for:
    - Testing with real LLM outputs without API calls
    - Reproducible test cases
    - Development without API credits
    """
    print("\n" + "=" * 80)
    print("DEMO 2: Replay Mode (Saved Fixtures)")
    print("=" * 80)
    
    # Configure replay mode
    config = LLMConfig(
        provider=LLMProvider.REPLAY,
        base_url="replay://local",
        model="replay-v1"
    )
    
    # Fixture directory
    fixture_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "llm_responses"
    
    print(f"\nConfig: {config}")
    print(f"Fixture dir: {fixture_dir}")
    
    # Create client
    with create_client(config) as client:
        # List available fixtures
        fixtures = client.list_fixtures()
        print(f"\nAvailable fixtures: {fixtures}")
        
        # Load specific fixture
        print("\n1. Loading 'simple_nearest' fixture...")
        request = GenerationRequest(
            prompt="ignored in replay mode",
            generation_id="simple_nearest"
        )
        
        response = client.generate(request)
        print(f"Response provider: {response.provider}")
        print(f"Response model: {response.model}")
        print(f"Mode: {response.metadata.get('mode')}")
        
        # Parse
        parse_result = parse_llm_response(response)
        print(f"\nParse result: {parse_result}")
        
        # Load another fixture
        print("\n2. Loading 'weighted_heuristic' fixture...")
        request = GenerationRequest(
            prompt="ignored",
            metadata={"fixture_name": "weighted_heuristic"}
        )
        
        response = client.generate(request)
        parse_result = parse_llm_response(response)
        print(f"Parse result: {parse_result}")
        
        if parse_result.success:
            print(f"Function: {parse_result.function_name}")
            print("Source preview:")
            print(parse_result.source_code[:200] + "...")


def demo_end_to_end():
    """
    Demonstrate end-to-end: generate -> parse -> validate -> execute.
    
    Shows the complete pipeline from LLM generation to evaluation.
    """
    print("\n" + "=" * 80)
    print("DEMO 3: End-to-End Pipeline (Mock Mode)")
    print("=" * 80)
    
    # Generate a small test instance
    print("\n1. Creating test instance...")
    generator = InstanceGenerator(seed=42, x_range=(0, 100), y_range=(0, 100))
    instance = generator.generate(n_stops=5)
    print(f"Instance: {instance.n_stops} stops")
    
    # Configure mock client
    config = LLMConfig(
        provider=LLMProvider.MOCK,
        base_url="mock://local",
        model="mock-v1"
    )
    
    # Generate heuristic
    print("\n2. Generating heuristic with LLM (mock mode)...")
    with create_client(config) as client:
        prompt = build_generation_prompt(
            iteration=0,
            context={
                "num_stops": instance.n_stops,
                "num_drivers": 1
            }
        )
        
        request = GenerationRequest(
            prompt=prompt,
            generation_id="e2e_demo",
            metadata={"candidate_key": "nearest_distance"}
        )
        
        response = client.generate(request)
    
    # Parse
    print("\n3. Parsing response...")
    parse_result = parse_llm_response(response)
    print(f"Parse result: {parse_result}")
    
    if not parse_result.success:
        print(f"Parse failed: {parse_result.errors}")
        return
    
    # Create candidate
    candidate = CandidateHeuristic(
        source_code=parse_result.source_code,
        function_name=parse_result.function_name,
        metadata={"generation_id": "e2e_demo"}
    )
    
    # Validate
    print("\n4. Validating candidate...")
    validator = HeuristicValidator()
    validation = validator.validate(candidate)
    print(f"Validation: {validation}")
    
    if not validation.is_valid:
        print(f"Validation errors: {validation.errors}")
        return
    
    # Execute
    print("\n5. Executing heuristic...")
    executor = HeuristicExecutor(timeout=5.0)
    
    # Compute distance matrix
    from engine.instances import compute_distance_matrix
    distance_matrix = compute_distance_matrix(instance.get_all_locations())
    
    # Create test context
    context = HeuristicContext(
        current_location=0,
        candidate_stops=[1, 2, 3],
        distance_matrix=distance_matrix,
        partial_route=[0]
    )
    
    execution = executor.execute(candidate, context)
    print(f"Execution: {execution}")
    
    if execution.is_success:
        scores = execution.output.get("scores", {})
        print(f"\nScores for candidates {context.candidate_stops}:")
        for stop, score in scores.items():
            print(f"  Stop {stop}: {score:.2f}")
        
        # Find best stop
        best_stop = min(scores.items(), key=lambda x: x[1])[0]
        print(f"\nBest next stop: {best_stop} (score: {scores[best_stop]:.2f})")
    else:
        print(f"Execution failed: {execution.error}")


def demo_prompt_building():
    """
    Demonstrate prompt building with different configurations.
    """
    print("\n" + "=" * 80)
    print("DEMO 4: Prompt Building")
    print("=" * 80)
    
    # Initial prompt
    print("\n1. Initial generation prompt (iteration 0):")
    print("-" * 80)
    prompt = build_generation_prompt(iteration=0)
    print(prompt[:500] + "...")
    print(f"\nTotal length: {len(prompt)} characters")
    
    # Prompt with feedback
    print("\n2. Prompt with feedback (iteration 3):")
    print("-" * 80)
    from engine.llm import build_feedback_prompt
    
    feedback = build_feedback_prompt(
        fitness_score=125.5,
        comparison="15% worse than nearest neighbor baseline",
        suggestions="Consider both distance and route position. Early stops should be nearby."
    )
    
    prompt = build_generation_prompt(
        iteration=3,
        feedback=feedback,
        best_score=120.0,
        context={"num_stops": 20, "num_drivers": 3}
    )
    
    # Show the feedback section
    lines = prompt.split('\n')
    feedback_start = next(i for i, line in enumerate(lines) if 'Feedback' in line)
    print('\n'.join(lines[feedback_start:feedback_start+10]))


def main():
    """Run all demonstrations."""
    print("\n")
    print("=" * 80)
    print(" " * 20 + "LLM Heuristic Generation Demo")
    print("=" * 80)
    print()
    print("This demo shows three modes for LLM heuristic generation:")
    print("  1. Mock mode: Predefined candidates without API calls")
    print("  2. Replay mode: Load from saved fixtures")
    print("  3. Live mode: Real API calls (not shown - requires API key)")
    print()
    print("All modes use the same validation and execution pipeline.")
    print("=" * 80)
    
    try:
        demo_mock_mode()
        demo_replay_mode()
        demo_end_to_end()
        demo_prompt_building()
        
        print("\n" + "=" * 80)
        print("All demos completed successfully!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
