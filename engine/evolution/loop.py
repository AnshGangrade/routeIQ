"""Main evolutionary loop orchestrating generation, evaluation, and selection."""

import uuid
import math
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
from engine.evaluation.evaluator import HeuristicEvaluator
from engine.evaluation.fitness import FitnessFunction
from engine.instances.generator import InstanceGenerator


class EvolutionCancelled(Exception):
    """Cooperative cancellation at a candidate/generation boundary."""


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
        progress_callback=None,
        should_cancel=None,
    ):
        self.config = config
        self.llm_client = llm_client
        self.progress_callback = progress_callback
        self.should_cancel = should_cancel or (lambda: False)
        
        # Initialize components
        self.validator = HeuristicValidator()
        self.fitness_fn = FitnessFunction()
        
        # Will be set during run
        self.training_instances = []
        self.test_instances = []
        self.evaluator = None
        
        # Tracking
        self.run: Optional[EvolutionRun] = None
        self.best_candidate_id: Optional[str] = None
        self.best_candidate_code: Optional[str] = None
        self.best_fitness: Optional[float] = None
        self.retained_candidates: List[CandidateRecord] = []

    def _check_cancelled(self):
        if self.should_cancel():
            raise EvolutionCancelled("Cancelled at a safe boundary; in-flight calls are allowed to finish")

    def _progress(self, stage, generation=0, candidates_done=0, record=None):
        if self.progress_callback:
            self.progress_callback(stage, generation, candidates_done, record)
    
    def run_evolution(self) -> EvolutionRun:
        """Run complete evolution pipeline.
        
        Returns:
            EvolutionRun with complete tracking data
        """
        # Initialize run
        self.best_candidate_id = None
        self.best_candidate_code = None
        self.best_fitness = None
        self.retained_candidates = []
        run_id = self._generate_run_id()
        self.run = EvolutionRun(
            run_id=run_id,
            config=self.config.model_dump(),
            training_seed=self.config.seed,
            test_seed=self.config.seed + 1000,  # Different seed for test set
        )
        
        try:
            self._check_cancelled()
            self._progress("preparing")
            # Generate instances
            self._generate_instances()
            
            # Run generations
            for gen_num in range(1, self.config.num_generations + 1):
                print(f"\n=== Generation {gen_num}/{self.config.num_generations} ===")
                generation_record = self._run_generation(gen_num)
                self.run.add_generation(generation_record)
                self._progress("generation_completed", gen_num, len(generation_record.candidates), generation_record)
                
                # Print progress
                print(f"Valid: {generation_record.num_valid}/{len(generation_record.candidates)}")
                if generation_record.best_fitness is not None:
                    print(f"Best this gen: {generation_record.best_fitness:.2f}")
                if generation_record.best_so_far_fitness is not None:
                    print(f"Best so far: {generation_record.best_so_far_fitness:.2f}")
            
            # Evaluate best candidate on test set
            if self.best_candidate_code:
                self._check_cancelled()
                self._progress("held_out", self.config.num_generations)
                print("\n=== Held-Out Test Evaluation ===")
                test_eval = self._evaluate_on_test_set()
                self.run.test_evaluation = test_eval
                self._check_cancelled()
                
                # Update final results
                self.run.best_candidate_id = test_eval.candidate_id
                self.run.best_candidate_code = self.best_candidate_code
                self.run.best_training_fitness = self.best_fitness
                
                self.run.mark_completed()
                print(f"\nEvolution completed: {run_id}")
            else:
                # No valid candidates found across all generations
                self.run.mark_failed("No valid candidates produced across all generations")
                print("\nEvolution failed: No valid candidates")
            
        except EvolutionCancelled as e:
            self.run.status = "cancelled"
            self.run.error_message = str(e)
            return self.run
        except Exception as e:
            self.run.mark_failed(str(e))
            print(f"\nEvolution failed: {e}")
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
            self._check_cancelled()
            self._progress("evaluating_candidates", gen_num, i)
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
                print(f"  Failed: {e}")

            self._check_cancelled()
            self._progress("evaluating_candidates", gen_num, i + 1)
        
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
        
        # Use the existing evaluator and strict fitness policy. Partial
        # successes must not gain an advantage by omitting harder instances.
        result = self.evaluator.evaluate_candidate(
            candidate=candidate,
            instances=self.training_instances,
            candidate_id=candidate_id,
        )
        fitness_score = self.fitness_fn.calculate(result)
        if not math.isfinite(fitness_score):
            errors = [
                f"seed {r.instance_seed}: {r.error_message or r.status.value}"
                for r in result.per_instance_results if r.error_message or r.distance is None
            ]
            return CandidateRecord(
                candidate_id=candidate_id,
                generation=generation,
                source_code=source_code,
                is_valid=False,
                error_type="EvaluationError",
                error_message=(
                    f"Training evaluation requires success on every instance "
                    f"({result.successful_evaluations}/{result.instances_evaluated} succeeded): "
                    + "; ".join(errors)
                ),
                evaluation_time=result.total_execution_time,
            )
        
        return CandidateRecord(
            candidate_id=candidate_id,
            generation=generation,
            source_code=source_code,
            is_valid=True,
            fitness_score=fitness_score,
            avg_route_distance=result.mean_distance,
            evaluation_time=result.total_execution_time,
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
        valid_candidates = [
            c for c in candidates
            if c.is_valid and c.fitness_score is not None and math.isfinite(c.fitness_score)
        ]
        
        # Find best in this generation
        best_this_gen_id = None
        best_this_gen_fitness = None
        
        if valid_candidates:
            best = min(valid_candidates, key=lambda c: (c.fitness_score, c.candidate_id))
            best_this_gen_id = best.candidate_id
            best_this_gen_fitness = best.fitness_score
            
            # Update best-so-far
            if self.best_fitness is None or best.fitness_score < self.best_fitness:
                self.best_fitness = best.fitness_score
                self.best_candidate_id = best.candidate_id
                self.best_candidate_code = best.source_code

        # Retain measured elites across generations without duplicating them
        # in generation history or reducing the configured new-candidate count.
        pool = {c.candidate_id: c for c in self.retained_candidates + valid_candidates}
        self.retained_candidates = sorted(
            pool.values(), key=lambda c: (c.fitness_score, c.candidate_id)
        )[:self.config.retained_candidates]
        
        # Calculate statistics
        avg_fitness = None
        if valid_candidates:
            avg_fitness = sum(c.fitness_score for c in valid_candidates) / len(valid_candidates)
        
        return GenerationRecord(
            generation_number=gen_num,
            candidates=candidates,
            best_candidate_id=best_this_gen_id,
            best_fitness=best_this_gen_fitness,
            best_so_far_id=self.best_candidate_id,
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
        
        # Build feedback string
        feedback_lines = ["Fitness is mean route distance; lower is better."]
        if not valid_candidates:
            feedback_lines.append("All new candidates in the previous generation were invalid. Try simpler heuristics.")
        
        if last_gen.best_fitness is not None:
            feedback_lines.append(f"Best fitness in last generation: {last_gen.best_fitness:.2f}")
        
        if self.best_fitness is not None:
            feedback_lines.append(f"Best fitness so far: {self.best_fitness:.2f}")
        
        feedback_lines.append(f"Valid candidates: {last_gen.num_valid}/{len(last_gen.candidates)}")

        for candidate in self.retained_candidates:
            feedback_lines.append(
                f"Retained candidate {candidate.candidate_id}, mean distance "
                f"{candidate.fitness_score:.6f}. Refine or combine its scoring logic:\n"
                f"```python\n{candidate.source_code}\n```"
            )
        
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
        if not self.best_candidate_code or not self.best_candidate_id:
            raise ValueError("No valid candidate to evaluate on test set")

        from engine.sandbox.models import CandidateHeuristic

        # All three methods see the complete, identical held-out batch.
        evolved = self.evaluator.evaluate_candidate(
            candidate=CandidateHeuristic(source_code=self.best_candidate_code),
            instances=self.test_instances,
            candidate_id=self.best_candidate_id,
        )
        nn = self.evaluator.evaluate_baseline_nn(self.test_instances)
        two_opt = self.evaluator.evaluate_baseline_2opt(
            self.test_instances, max_2opt_iterations=1000
        )

        # The existing result schema represents complete comparisons only.
        # Fail the run explicitly rather than publish subset means or infinity.
        for result in (evolved, nn, two_opt):
            if not math.isfinite(self.fitness_fn.calculate(result)):
                errors = [
                    f"seed {r.instance_seed}: {r.error_message or r.status.value}"
                    for r in result.per_instance_results if r.error_message or r.distance is None
                ]
                raise ValueError(
                    f"Held-out evaluation failed for {result.candidate_id}: "
                    f"{result.successful_evaluations}/{result.instances_evaluated} succeeded; "
                    + "; ".join(errors)
                )

        evolved_avg = evolved.mean_distance
        baselines = [
            BaselineComparison(
                algorithm=name,
                avg_route_distance=result.mean_distance,
                evaluation_time=result.total_execution_time,
            )
            for name, result in (("nearest_neighbor", nn), ("two_opt", two_opt))
        ]

        # A positive candidate cost against a zero-cost baseline has no finite
        # percentage improvement; do not mislabel it as zero improvement.
        improvements = []
        for result in (nn, two_opt):
            if result.mean_distance == 0:
                if evolved_avg != 0:
                    raise ValueError("Improvement percentage is undefined for a zero-distance baseline")
                improvements.append(0.0)
            else:
                improvements.append((result.mean_distance - evolved_avg) / result.mean_distance * 100)
        
        return TestSetEvaluation(
            candidate_id=self.best_candidate_id,
            test_instances_count=len(self.test_instances),
            evolved_avg_distance=evolved_avg,
            evolved_evaluation_time=evolved.total_execution_time,
            baselines=baselines,
            improvement_vs_nn_percent=improvements[0],
            improvement_vs_2opt_percent=improvements[1],
        )
