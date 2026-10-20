"""Main evolutionary loop orchestrating generation, evaluation, and selection."""

import uuid
import time
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from engine.evolution.config import EvolutionConfig
from engine.evolution.models import (
    CandidateRecord,
    GenerationRecord,
    EvolutionRun,
    BaselineComparison,
    TestSetEvaluation,
)
from engine.llm.client import LLMClient
from engine.llm.models import GenerationRequest
from engine.llm.parser import parse_llm_response
from engine.llm.prompts import build_generation_prompt
from engine.sandbox.validator import HeuristicValidator
from engine.sandbox.adapter import create_scoring_function
from engine.evaluation.evaluator import HeuristicEvaluator
from engine.evaluation.fitness import FitnessFunction
from engine.evaluation.selection import CandidateSelector
from engine.evaluation.feedback import prepare_feedback
from engine.instances.generator import InstanceGenerator


class EvolutionLoop:
    """Orchestrates the complete evolution pipeline.
    
    Handles:
    - Training/test instance generation
    - Multiple generations with LLM feedback
    - Candidate validation and evaluation
    - Selection and fitness tracking
    - Best-so-far tracking
    - Held-out test set evaluation
    - Error handling without crashing
    """
    
    def __init__(
        self,
        config: EvolutionConfig,
        llm_client: LLMClient,
    ):
        self.config = config
        self.llm_client = llm_client
        
        # Initialize components
        self.validator = HeuristicValidator()
        self.fitness_fn = FitnessFunction()
        self.selector = CandidateSelector()
        
        # Will be set during run
        self.training_instances = []
        self.test_instances = []
        self.evaluator = None
        
        # Tracking
        self.run: Optional[EvolutionRun] = None
        self.best_candidate_code: Optional[str] = None
        self.best_fitness: Optional[float] = None
    
    def run_evolution(self) -> EvolutionRun:
        """Run complete evolution pipeline.
        
        Returns:
            EvolutionRun with complete tracking data
        """
        # Initialize run
        run_id = self._generate_run_id()
        self.run = EvolutionRun(
            run_id=run_id,
            config=self.config.model_dump(),
            training_seed=self.config.seed,
            test_seed=self.config.seed + 1000,  # Different seed for test set
        )
        
        try:
            # Generate instances
            self._generate_instances()
            
            # Run generations
            for gen_num in range(1, self.config.num_generations + 1):
                print(f"\n=== Generation {gen_num}/{self.config.num_generations} ===")
                generation_record = self._run_generation(gen_num)
                self.run.add_generation(generation_record)
                
                # Print progress
                print(f"Valid: {generation_record.num_valid}/{len(generation_record.candidates)}")
                if generation_record.best_fitness is not None:
                    print(f"Best this gen: {generation_record.best_fitness:.2f}")
                if generation_record.best_so_far_fitness is not None:
                    print(f"Best so far: {generation_record.best_so_far_fitness:.2f}")
            
            # Evaluate best candidate on test set
            if self.best_candidate_code:
                print("\n=== Held-Out Test Evaluation ===")
                test_eval = self._evaluate_on_test_set()
                self.run.test_evaluation = test_eval
                
                # Update final results
                self.run.best_candidate_id = test_eval.candidate_id
                self.run.best_candidate_code = self.best_candidate_code
                self.run.best_training_fitness = self.best_fitness
            
            self.run.mark_completed()
            print(f"\n✓ Evolution completed: {run_id}")
            
        except Exception as e:
            self.run.mark_failed(str(e))
            print(f"\n✗ Evolution failed: {e}")
            raise
        
        return self.run
    
    def _generate_run_id(self) -> str:
        """Generate unique run ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_uuid = str(uuid.uuid4())[:8]
        return f"run_{timestamp}_{short_uuid}"
    
    def _generate_instances(self):
        """Generate training and test instances."""
        generator = InstanceGenerator()
        
        # Training instances
        self.training_instances = generator.generate_batch(
            n_instances=self.config.training_instance_count,
            n_stops=self.config.num_stops,
            start_seed=self.config.seed,
        )
        print(f"Generated {len(self.training_instances)} training instances")
        
        # Test instances (different seed)
        self.test_instances = generator.generate_batch(
            n_instances=self.config.test_instance_count,
            n_stops=self.config.num_stops,
            start_seed=self.config.seed + 1000,
        )
        print(f"Generated {len(self.test_instances)} test instances")
        
        # Create evaluator
        self.evaluator = HeuristicEvaluator(
            timeout=self.config.evaluation_timeout,
        )
    
    def _run_generation(self, gen_num: int) -> GenerationRecord:
        """Run a single generation.
        
        Args:
            gen_num: Generation number (1-indexed)
        
        Returns:
            GenerationRecord with all candidate results
        """
        # Prepare feedback from previous generation
        feedback_data = self._prepare_feedback()
        
        # Build prompt
        prompt = build_generation_prompt(
            iteration=gen_num,
            feedback=feedback_data.get("feedback", ""),
            best_score=self.best_fitness,
            context=feedback_data.get("context", {}),
        )
        
        # Generate candidates
        candidate_records = []
        for i in range(self.config.candidates_per_generation):
            print(f"  Generating candidate {i+1}/{self.config.candidates_per_generation}...")
            candidate_id = f"gen{gen_num}_cand{i+1}"
            
            try:
                record = self._generate_and_evaluate_candidate(
                    candidate_id=candidate_id,
                    generation=gen_num,
                    prompt=prompt,
                )
                candidate_records.append(record)
                
            except Exception as e:
                # Record failure but don't crash
                error_record = CandidateRecord(
                    candidate_id=candidate_id,
                    generation=gen_num,
                    source_code="",
                    is_valid=False,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                candidate_records.append(error_record)
                
                self.run.add_failure({
                    "generation": gen_num,
                    "candidate_id": candidate_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                })
                print(f"  ✗ Failed: {e}")
        
        # Build generation record
        return self._build_generation_record(gen_num, candidate_records)
    
    def _generate_and_evaluate_candidate(
        self,
        candidate_id: str,
        generation: int,
        prompt: str,
    ) -> CandidateRecord:
        """Generate and evaluate a single candidate.
        
        Args:
            candidate_id: Unique candidate identifier
            generation: Generation number
            prompt: LLM prompt
        
        Returns:
            CandidateRecord with evaluation results
        """
        # Call LLM
        generation_request = GenerationRequest(
            prompt=prompt,
            generation_id=candidate_id,
            metadata={"generation": generation},
        )
        llm_response = self.llm_client.generate(generation_request)
        
        # Parse response
        parse_result = parse_llm_response(llm_response)
        
        if not parse_result.success:
            error_message = "; ".join(parse_result.errors) if parse_result.errors else "Unknown parse error"
            return CandidateRecord(
                candidate_id=candidate_id,
                generation=generation,
                source_code=llm_response.raw_content,
                is_valid=False,
                error_type="ParseError",
                error_message=error_message,
            )
        
        source_code = parse_result.source_code
        
        # Validate - create CandidateHeuristic object
        from engine.sandbox.models import CandidateHeuristic
        candidate = CandidateHeuristic(
            source_code=source_code,
            function_name=parse_result.function_name or "score_candidates",
            generation_id=candidate_id,
        )
        validation = self.validator.validate(candidate)
        
        if not validation.is_valid:
            error_message = "; ".join(validation.errors) if validation.errors else "Validation failed"
            return CandidateRecord(
                candidate_id=candidate_id,
                generation=generation,
                source_code=source_code,
                is_valid=False,
                error_type="ValidationError",
                error_message=error_message,
            )
        
        # Create scoring function
        try:
            scoring_fn = create_scoring_function(source_code)
        except Exception as e:
            return CandidateRecord(
                candidate_id=candidate_id,
                generation=generation,
                source_code=source_code,
                is_valid=False,
                error_type="AdapterError",
                error_message=str(e),
            )
        
        # Evaluate on training instances
        start_time = time.time()
        total_distance = 0.0
        successful_evals = 0
        evaluation_errors = []
        
        for instance in self.training_instances:
            try:
                # Use harness to build route
                from engine.heuristics import RouteHarness
                from engine.instances import compute_distance_matrix
                
                harness = RouteHarness()
                
                # Convert instance to distance matrix
                locations = instance.get_all_locations()
                distance_matrix = compute_distance_matrix(locations)
                
                # Build route using heuristic
                route_result = harness.build_route(
                    heuristic=scoring_fn,
                    distance_matrix=distance_matrix,
                    n_stops=instance.n_stops,
                    algorithm_name=candidate_id
                )
                
                total_distance += route_result.total_distance
                successful_evals += 1
                
            except Exception as e:
                # Record error but continue with other instances
                error_msg = f"{type(e).__name__}: {str(e)}"
                evaluation_errors.append(error_msg)
                continue
        
        eval_time = time.time() - start_time
        
        if successful_evals == 0:
            # All evaluations failed - report the errors
            error_summary = "; ".join(set(evaluation_errors[:3]))  # First 3 unique errors
            return CandidateRecord(
                candidate_id=candidate_id,
                generation=generation,
                source_code=source_code,
                is_valid=False,
                error_type="EvaluationError",
                error_message=f"All route evaluations failed: {error_summary}",
            )
        
        avg_distance = total_distance / successful_evals
        
        # Calculate fitness - for evolution, we use distance directly as fitness
        # (lower distance = better fitness)
        fitness_score = avg_distance
        
        return CandidateRecord(
            candidate_id=candidate_id,
            generation=generation,
            source_code=source_code,
            is_valid=True,
            fitness_score=fitness_score,
            avg_route_distance=avg_distance,
            evaluation_time=eval_time,
        )
    
    def _build_generation_record(
        self,
        gen_num: int,
        candidates: List[CandidateRecord],
    ) -> GenerationRecord:
        """Build generation record with statistics.
        
        Args:
            gen_num: Generation number
            candidates: List of candidate records
        
        Returns:
            Complete GenerationRecord
        """
        # Filter valid candidates
        valid_candidates = [c for c in candidates if c.is_valid]
        
        # Find best in this generation
        best_this_gen_id = None
        best_this_gen_fitness = None
        
        if valid_candidates:
            best = max(valid_candidates, key=lambda c: c.fitness_score)
            best_this_gen_id = best.candidate_id
            best_this_gen_fitness = best.fitness_score
            
            # Update best-so-far
            if self.best_fitness is None or best.fitness_score > self.best_fitness:
                self.best_fitness = best.fitness_score
                self.best_candidate_code = best.source_code
        
        # Calculate statistics
        avg_fitness = None
        if valid_candidates:
            avg_fitness = sum(c.fitness_score for c in valid_candidates) / len(valid_candidates)
        
        return GenerationRecord(
            generation_number=gen_num,
            candidates=candidates,
            best_candidate_id=best_this_gen_id,
            best_fitness=best_this_gen_fitness,
            best_so_far_id=f"gen{gen_num}_best" if self.best_candidate_code else None,
            best_so_far_fitness=self.best_fitness,
            num_valid=len(valid_candidates),
            num_invalid=len(candidates) - len(valid_candidates),
            avg_fitness=avg_fitness,
        )
    
    def _prepare_feedback(self) -> Dict[str, Any]:
        """Prepare feedback for next generation.
        
        Returns:
            Dictionary with feedback data for prompt
        """
        if not self.run.generations:
            return {"feedback": "", "context": {}}
        
        last_gen = self.run.generations[-1]
        
        # Get valid candidates from last generation
        valid_candidates = [c for c in last_gen.candidates if c.is_valid]
        
        if not valid_candidates:
            return {
                "feedback": "All candidates in previous generation were invalid. Try simpler heuristics.",
                "context": {"num_invalid": last_gen.num_invalid},
            }
        
        # Build feedback string
        feedback_lines = []
        
        if last_gen.best_fitness:
            feedback_lines.append(f"Best fitness in last generation: {last_gen.best_fitness:.2f}")
        
        if self.best_fitness:
            feedback_lines.append(f"Best fitness so far: {self.best_fitness:.2f}")
        
        feedback_lines.append(f"Valid candidates: {last_gen.num_valid}/{len(last_gen.candidates)}")
        
        return {
            "feedback": "\n".join(feedback_lines),
            "context": {
                "generation": last_gen.generation_number,
                "best_fitness": self.best_fitness,
            },
        }
    
    def _evaluate_on_test_set(self) -> TestSetEvaluation:
        """Evaluate best candidate on held-out test set.
        
        Returns:
            TestSetEvaluation with baseline comparisons
        """
        if not self.best_candidate_code:
            raise ValueError("No valid candidate to evaluate on test set")
        
        # Create test evaluator
        from engine.heuristics import RouteHarness
        from engine.baselines import nearest_neighbor, nearest_neighbor_with_2opt
        from engine.instances import compute_distance_matrix
        
        harness = RouteHarness()
        
        # Evaluate evolved candidate
        scoring_fn = create_scoring_function(self.best_candidate_code)
        start_time = time.time()
        
        evolved_distances = []
        for instance in self.test_instances:
            try:
                locations = instance.get_all_locations()
                distance_matrix = compute_distance_matrix(locations)
                
                route_result = harness.build_route(
                    heuristic=scoring_fn,
                    distance_matrix=distance_matrix,
                    n_stops=instance.n_stops
                )
                evolved_distances.append(route_result.total_distance)
            except Exception:
                continue
        
        evolved_time = time.time() - start_time
        evolved_avg = sum(evolved_distances) / len(evolved_distances) if evolved_distances else float('inf')
        
        print(f"Evolved: {evolved_avg:.2f}")
        
        # Compare with baselines
        baselines = []
        
        # Nearest Neighbor
        start_time = time.time()
        nn_distances = []
        for instance in self.test_instances:
            locations = instance.get_all_locations()
            distance_matrix = compute_distance_matrix(locations)
            route = nearest_neighbor(distance_matrix)
            nn_distances.append(route.total_distance)
        nn_time = time.time() - start_time
        nn_avg = sum(nn_distances) / len(nn_distances) if nn_distances else float('inf')
        
        baselines.append(BaselineComparison(
            algorithm="nearest_neighbor",
            avg_route_distance=nn_avg,
            evaluation_time=nn_time,
        ))
        print(f"Nearest Neighbor: {nn_avg:.2f}")
        
        # 2-Opt
        start_time = time.time()
        two_opt_distances = []
        for instance in self.test_instances:
            locations = instance.get_all_locations()
            distance_matrix = compute_distance_matrix(locations)
            route = nearest_neighbor_with_2opt(distance_matrix)
            two_opt_distances.append(route.total_distance)
        two_opt_time = time.time() - start_time
        two_opt_avg = sum(two_opt_distances) / len(two_opt_distances) if two_opt_distances else float('inf')
        
        baselines.append(BaselineComparison(
            algorithm="two_opt",
            avg_route_distance=two_opt_avg,
            evaluation_time=two_opt_time,
        ))
        print(f"2-Opt: {two_opt_avg:.2f}")
        
        # Calculate improvements (can be negative!)
        improvement_vs_nn = ((nn_avg - evolved_avg) / nn_avg) * 100 if nn_avg > 0 else 0
        improvement_vs_2opt = ((two_opt_avg - evolved_avg) / two_opt_avg) * 100 if two_opt_avg > 0 else 0
        
        print(f"Improvement vs NN: {improvement_vs_nn:+.1f}%")
        print(f"Improvement vs 2-Opt: {improvement_vs_2opt:+.1f}%")
        
        return TestSetEvaluation(
            candidate_id=self.run.run_id + "_best",
            test_instances_count=len(self.test_instances),
            evolved_avg_distance=evolved_avg,
            evolved_evaluation_time=evolved_time,
            baselines=baselines,
            improvement_vs_nn_percent=improvement_vs_nn,
            improvement_vs_2opt_percent=improvement_vs_2opt,
        )
