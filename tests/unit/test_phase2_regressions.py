"""Offline regressions for objective direction, trusted costs, and fair evaluation."""

import numpy as np
import pytest

from engine.baselines import nearest_neighbor, nearest_neighbor_with_2opt, two_opt
from engine.evaluation import HeuristicEvaluator
from engine.evolution import EvolutionConfig, EvolutionLoop
from engine.evolution.models import CandidateRecord, EvolutionRun
from engine.heuristics import RouteHarness
from engine.instances import InstanceGenerator, calculate_route_cost
from engine.llm.models import LLMResponse
from engine.sandbox import CandidateHeuristic, create_scoring_function


NEAREST = '''def score_candidates(context):
    return {"scores": {s: context.distance_matrix[context.current_location, s]
                       for s in context.candidate_stops}}
'''
PARTIAL_FAILURE = '''def score_candidates(context):
    if len(context.distance_matrix) > 3:
        return {"scores": {}}
    return {"scores": {s: context.distance_matrix[context.current_location, s]
                       for s in context.candidate_stops}}
'''


class FixedClient:
    def __init__(self, code=NEAREST):
        self.code = code

    def generate(self, request):
        return LLMResponse(
            raw_content=self.code, provider="mock", model="offline",
            generation_id=request.generation_id,
        )


def make_loop(**kwargs):
    loop = EvolutionLoop(EvolutionConfig(**kwargs), FixedClient())
    loop.run = EvolutionRun(run_id="offline", config={}, training_seed=1, test_seed=1001)
    loop.evaluator = HeuristicEvaluator()
    return loop


def record(candidate_id, distance, generation=1):
    return CandidateRecord(
        candidate_id=candidate_id, generation=generation,
        source_code=f"# {candidate_id}\n{NEAREST}",
        is_valid=True, fitness_score=distance,
    )


def instances():
    return [InstanceGenerator(seed=11).generate(2), InstanceGenerator(seed=12).generate(3)]


def test_minimum_and_real_winner_survive_worse_and_invalid_generations():
    loop = make_loop()
    first = loop._build_generation_record(1, [record("short", 100), record("long", 200)])
    assert first.best_candidate_id == first.best_so_far_id == "short"
    assert first.best_fitness == 100
    second = loop._build_generation_record(2, [record("worse", 150, 2)])
    assert second.best_candidate_id == "worse"
    assert second.best_so_far_id == "short"
    assert second.best_so_far_fitness == 100
    empty = loop._build_generation_record(3, [])
    assert empty.best_candidate_id is None
    assert empty.best_so_far_id == "short"
    better = loop._build_generation_record(4, [record("zero", 0, 4)])
    assert better.best_so_far_id == "zero"
    assert better.best_so_far_fitness == 0


def test_equal_fitness_keeps_incumbent_and_ties_are_deterministic():
    loop = make_loop()
    first = loop._build_generation_record(1, [record("b", 10), record("a", 10)])
    assert first.best_candidate_id == "a"
    second = loop._build_generation_record(2, [record("new", 10, 2)])
    assert second.best_so_far_id == "a"


@pytest.mark.parametrize("retained", [1, 2])
def test_retained_elite_code_reaches_later_prompts_even_after_invalid_generation(monkeypatch, retained):
    loop = make_loop(retained_candidates=retained, candidates_per_generation=1)
    first = loop._build_generation_record(1, [
        record("winner", 10), record("runner_up", 20), record("discarded", 30),
    ])
    loop.run.add_generation(first)
    prompts = []

    def invalid(candidate_id, generation, prompt):
        prompts.append(prompt)
        return CandidateRecord(candidate_id=candidate_id, generation=generation, source_code="", is_valid=False)

    monkeypatch.setattr(loop, "_generate_and_evaluate_candidate", invalid)
    loop.run.add_generation(loop._run_generation(2))
    loop._run_generation(3)
    assert len(loop.retained_candidates) == retained
    assert len(prompts) == 2
    for prompt in prompts:
        assert record("winner", 10).source_code in prompt
        assert (record("runner_up", 20).source_code in prompt) == (retained == 2)
        assert record("discarded", 30).source_code not in prompt
        assert "lower is better" in prompt


def test_candidate_matrix_assignment_is_rejected_and_reference_is_unchanged():
    matrix = np.array([[0., 10., 20.], [10., 0., 15.], [20., 15., 0.]])
    original = matrix.copy()
    code = '''def score_candidates(context):
    context.distance_matrix[:] = 0
    return {"scores": {s: 0 for s in context.candidate_stops}}
'''
    with pytest.raises(ValueError, match="read-only"):
        RouteHarness().build_route(create_scoring_function(code), matrix, 2)
    np.testing.assert_array_equal(matrix, original)


def test_reenabled_candidate_copy_cannot_falsify_reference_cost_or_next_context():
    matrix = np.array([[0., 10., 20.], [10., 0., 15.], [20., 15., 0.]])
    original = matrix.copy()
    code = '''def score_candidates(context):
    scale = context.distance_matrix[0, 1]
    context.distance_matrix.setflags(write=True)
    context.distance_matrix.fill(0)
    return {"scores": {s: s / scale for s in context.candidate_stops}}
'''
    result = RouteHarness().build_route(create_scoring_function(code), matrix, 2)
    assert result.total_distance == 45
    assert result.route == [0, 1, 2, 0]
    np.testing.assert_array_equal(matrix, original)


def test_directed_two_opt_never_accepts_a_more_expensive_reversal():
    matrix = np.array([
        [0, 93, 15, 72, 61], [21, 0, 87, 75, 75],
        [88, 24, 0, 22, 53], [2, 88, 30, 0, 2], [64, 60, 21, 33, 0],
    ], dtype=float)
    nn = nearest_neighbor(matrix)
    assert nn.total_distance == 120
    result = nearest_neighbor_with_2opt(matrix)
    assert result.total_distance <= nn.total_distance
    assert result.total_distance == calculate_route_cost(result.route, matrix, return_to_depot=False)
    assert sorted(result.route[1:-1]) == [1, 2, 3, 4]
    assert result.route[0] == result.route[-1] == 0

    # One accepted move at a time also has to improve the true directed cost.
    route = [0, 1, 2, 3, 4, 0]
    for _ in range(10):
        previous = calculate_route_cost(route, matrix, return_to_depot=False)
        step = two_opt(route, matrix, max_iterations=1)
        if step.route == route:
            break
        assert step.total_distance < previous
        route = step.route


def test_partial_training_failure_is_invalid_not_a_subset_fitness():
    loop = make_loop()
    loop.training_instances = instances()
    loop.llm_client = FixedClient(PARTIAL_FAILURE)
    candidate = loop._generate_and_evaluate_candidate("partial", 1, "offline")
    assert not candidate.is_valid
    assert candidate.fitness_score is None
    assert "1/2 succeeded" in candidate.error_message
    assert "seed 12" in candidate.error_message


@pytest.mark.parametrize("failure", ["candidate", "nearest_neighbor", "nearest_neighbor_with_2opt"])
def test_held_out_failure_fails_run_without_an_improvement_claim(monkeypatch, failure):
    import engine.evaluation.evaluator as evaluator_module

    loop = make_loop(num_generations=1, candidates_per_generation=1)
    loop.llm_client = FixedClient(PARTIAL_FAILURE if failure == "candidate" else NEAREST)

    def generate_instances():
        loop.training_instances = instances()[:1]
        loop.test_instances = instances()

    monkeypatch.setattr(loop, "_generate_instances", generate_instances)
    if failure != "candidate":
        original = getattr(evaluator_module, failure)

        def fail_on_second(matrix, *args, **kwargs):
            if len(matrix) == 4:
                raise ValueError("deliberate baseline failure")
            return original(matrix, *args, **kwargs)

        monkeypatch.setattr(evaluator_module, failure, fail_on_second)

    with pytest.raises(ValueError, match="Held-out evaluation failed.*1/2 succeeded.*seed 12"):
        loop.run_evolution()
    assert loop.run.status == "failed"
    assert loop.run.test_evaluation is None


def test_successful_test_evaluation_uses_same_batch_and_actual_winner(monkeypatch):
    loop = make_loop()
    loop.best_candidate_id = "gen1_cand1"
    loop.best_candidate_code = NEAREST
    loop.test_instances = instances()
    seen = []
    for name in ("evaluate_candidate", "evaluate_baseline_nn", "evaluate_baseline_2opt"):
        original = getattr(loop.evaluator, name)

        def observe(*args, _original=original, **kwargs):
            batch = kwargs["instances"] if "instances" in kwargs else args[0]
            seen.append(batch)
            return _original(*args, **kwargs)

        monkeypatch.setattr(loop.evaluator, name, observe)
    result = loop._evaluate_on_test_set()
    assert len(seen) == 3
    assert all(batch is loop.test_instances for batch in seen)
    assert result.candidate_id == "gen1_cand1"
    assert result.test_instances_count == 2
    assert result.improvement_vs_nn_percent == pytest.approx(0)
    assert result.improvement_vs_2opt_percent <= 0


def test_comparison_does_not_publish_partial_success_improvements():
    evaluator = HeuristicEvaluator()
    batch = instances()
    candidate = evaluator.evaluate_candidate(CandidateHeuristic(source_code=PARTIAL_FAILURE), batch, "partial")
    comparison = evaluator.compare_with_baselines(candidate, batch)
    assert comparison.candidate_result.failed_evaluations == 1
    assert comparison.improvement_vs_nn is None
    assert comparison.improvement_vs_2opt is None


def test_comparison_rejects_different_instance_order():
    evaluator = HeuristicEvaluator()
    batch = instances()
    candidate = evaluator.evaluate_candidate(CandidateHeuristic(source_code=NEAREST), batch, "nearest")
    with pytest.raises(ValueError, match="match the comparison instances"):
        evaluator.compare_with_baselines(candidate, list(reversed(batch)))
