"""Fair, bounded adapters around existing methods. No optimization policy lives here."""
from dataclasses import asdict, dataclass, field, replace
import platform
import random
import subprocess
import time
from pathlib import Path

import numpy
import pydantic

from engine.routing.budget import SearchBudget, SearchStopped
from engine.routing.construction import cheapest_insertion, contiguous_sweep, legacy_angular_round_robin
from engine.routing.search import SearchConfig, solve_hybrid
from engine.routing.validation import validate_fleet_solution
from .fleet_dataset import DATASET_VERSION, catalog_fingerprint, digest

METHODS = ("historical_nn", "historical_nn_2opt", "cheapest_insertion", "sweep",
           "constructor_portfolio", "hybrid_vnd", "hybrid_ils")


@dataclass(frozen=True)
class BenchmarkConfig:
    operations: int = 1_000_000
    seconds: float = 60.
    search_seed: int = 0
    search: SearchConfig = field(default_factory=lambda: SearchConfig(max_operator_calls=1000, ils_iterations=5))
    random_trials: int = 0
    workers: int = 1

    def __post_init__(self):
        SearchBudget(self.operations, self.seconds)
        if type(self.search_seed) is not int:
            raise ValueError("search_seed must be an integer")
        if type(self.random_trials) is not int or not 0 <= self.random_trials <= 8:
            raise ValueError("random_trials must be in 0..8")
        if not isinstance(self.search, SearchConfig):
            raise ValueError("search must be a SearchConfig")
        if type(self.workers) is not int or not 1 <= self.workers <= 16:
            raise ValueError("workers must be in 1..16")

    @classmethod
    def from_dict(cls, value):
        return cls(**{**value, "search": SearchConfig(**value["search"])})

    @property
    def methods(self):
        return METHODS + (("random_config_search",) if self.random_trials else ())


def source_fingerprint(root):
    """Hash only implementation source, never environment/configuration secrets."""
    paths = sorted((root / "engine").rglob("*.py")) + [root / "scripts/run_fleet_benchmark.py",
        root / "scripts/run_fleet_campaign.py", root / "scripts/audit_fleet_benchmark.py"]
    return digest([(p.relative_to(root).as_posix(), digest(p.read_text(encoding="utf-8-sig")))
                   for p in paths])


def software_record(root):
    def git(*args):
        try:
            result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
        except OSError:
            return "unavailable"
        return result.stdout.strip() if result.returncode == 0 else "unavailable"
    return {"python": platform.python_version(), "numpy": numpy.__version__,
            "pydantic": pydantic.__version__, "platform": platform.platform(),
            "git_commit": git("rev-parse", "HEAD"),
            "working_tree_dirty": bool(git("status", "--porcelain")),
            "source_fingerprint": source_fingerprint(root)}


def protocol(config, root):
    content = {"schema": "fleet-benchmark-protocol/v1", "dataset_version": DATASET_VERSION,
               "catalog_fingerprint": catalog_fingerprint(), "config": asdict(config),
               "software": software_record(root)}
    return {**content, "protocol_fingerprint": digest(content)}


def verify_protocol(value, root):
    content = {k: v for k, v in value.items() if k != "protocol_fingerprint"}
    if value.get("protocol_fingerprint") != digest(content):
        raise ValueError("Protocol fingerprint mismatch")
    if (value.get("schema") != "fleet-benchmark-protocol/v1"
            or value.get("dataset_version") != DATASET_VERSION
            or value.get("catalog_fingerprint") != catalog_fingerprint()
            or value["software"] != software_record(root)):
        raise ValueError("Protocol software or dataset differs; use the original environment and source")
    return BenchmarkConfig.from_dict(value["config"])


def _random_control(problem, config):
    """Bounded host configuration sampling, with one total shared allocation.

    Each trial gets floor(total operations / trials); unused work is not donated.
    No validation/held-out feedback, population, new operator or solver changes.
    """
    rng, results, trials = random.Random(config.search_seed), [], []
    started = time.perf_counter()
    for index in range(config.random_trials):
        names = list(config.search.operators)
        rng.shuffle(names)
        sampled = replace(config.search, operators=tuple(names), nn_attempts=rng.randint(1, 4),
                          perturbation_moves=rng.randint(1, 3),
                          ils_iterations=rng.randint(0, config.search.ils_iterations))
        seconds = max(0., config.seconds - (time.perf_counter() - started))
        if seconds == 0:
            break
        result = solve_hybrid(problem, config=sampled, search_seed=config.search_seed,
            operation_budget=config.operations // config.random_trials, time_limit_seconds=seconds)
        results.append(result)
        trials.append({"trial": index, "config": asdict(sampled), "status": result.status,
                       "termination_reason": result.termination_reason,
                       "operations": result.operations_used, "runtime_seconds": result.elapsed_seconds,
                       "total_distance": result.final_solution.total_distance})
    return results, trials


def search_diagnostics(result):
    """Observe existing immutable events; never instrument or alter search decisions.

    Core ils_iterations counts attempts, including an interrupted final iteration.
    A completed cycle requires its existing ils_acceptance event.
    """
    previous = result.initial_solution.total_distance
    in_ils, before_ils, global_bests, finished = False, None, 0, 0
    gains, events = {}, []
    previous_work = 0
    ils_start_work = None
    for event in result.events:
        if event.stage == "perturbation" and not in_ils:
            in_ils, before_ils, ils_start_work = True, previous, previous_work
        drop = max(0., previous-event.best_distance) if event.stage != "construction" else 0.
        if event.stage != "construction":
            key = ("ils/" if in_ils else "vnd/") + event.method
            gains[key] = gains.get(key, 0.) + drop
            if in_ils and drop > 0:
                global_bests += 1
        if event.stage == "ils_acceptance":
            finished += 1
        if event.stage != "construction":
            previous = event.best_distance
        previous_work = event.operations_used
        # Persist evidence of gains/ILS transitions, not thousands of unchanged
        # neighborhood scans per case. Aggregate work still includes every scan.
        if drop > 0 or event.stage in ("perturbation", "ils_acceptance"):
            events.append({"stage": event.stage, "method": event.method, "status": event.status,
                           "accepted": event.accepted, "best_distance": event.best_distance,
                           "operations_used": event.operations_used, "global_best_drop": drop})
    return {"ils_entered": in_ils, "ils_iterations_completed": finished,
            "ils_iterations_attempted": result.ils_iterations,
            "pre_ils_best_distance": before_ils, "ils_global_best_updates": global_bests,
            "ils_found_new_global_best": bool(global_bests),
            "ils_operations": result.operations_used-ils_start_work if in_ils else 0,
            "budget_exhausted_before_ils": result.budget_exhausted and not in_ils,
            "budget_exhausted_during_ils": result.budget_exhausted and in_ils,
            "global_best_distance_drop_by_operator": gains, "events": events}


def run_method(problem, method, config):
    if method not in config.methods:
        raise ValueError("Unknown benchmark method")
    if problem.search_seed != config.search_seed:
        raise ValueError("Build the shared problem with the protocol search seed")
    start = time.perf_counter()
    before = problem.fingerprint
    row = {"method": method, "problem_fingerprint": before,
           "matrix_fingerprint": problem.matrix_fingerprint, "search_seed": config.search_seed,
           "distance_units": problem.distance_units, "status": "completed", "termination_reason": "completed",
           "feasible": False, "evaluation_failure": False, "error_type": None,
           "total_distance": None, "longest_route_distance": None, "routes": None,
           "runtime_seconds": 0., "operations_used": 0, "operation_limit": config.operations,
           "time_limit_seconds": config.seconds, "work_by_category": {},
           "operator_calls": 0, "accepted_moves": None if method == "historical_nn_2opt" else 0,
           "ils_iterations": 0, "diversifications": 0, "neighborhoods_truncated": 0,
           "initial_distance": None, "initial_method": None, "final_method": None,
           "budget_exhausted": False,
           "timeout": False, "construction_candidates": [], "random_trials": [], "errors": []}
    row["search_diagnostics"] = []
    plan, budget = None, None
    try:
        if method == "sweep" and (problem.directed or problem.coordinates is None
                or problem.coordinate_system != "cartesian" or problem.matrix_provenance.source != "euclidean"):
            row.update(status="not_applicable", termination_reason="requires_symmetric_euclidean")
        elif method in ("historical_nn", "historical_nn_2opt", "cheapest_insertion", "sweep"):
            budget = SearchBudget(config.operations, config.seconds)
            budget.require("constructor_call")
            if method.startswith("historical_"):
                plan = legacy_angular_round_robin(problem, budget=budget,
                    method="nearest_neighbor" if method == "historical_nn" else "2opt")
            else:
                plan = (cheapest_insertion if method == "cheapest_insertion" else contiguous_sweep)(problem, budget=budget)
            if budget.reason:
                row.update(status="incomplete", termination_reason=budget.reason, budget_exhausted=True)
            # Historical 2-Opt does not expose accepted reversal counts. Null is
            # deliberate: a wrapper's plan.work.accepted_moves=0 is not evidence.
            row["accepted_moves"] = None if method == "historical_nn_2opt" else 0
            row["constructor_work"] = asdict(plan.work)
        else:
            search = config.search
            if method == "constructor_portfolio":
                search = replace(search, operators=(), ils_iterations=0)
            elif method == "hybrid_vnd":
                search = replace(search, ils_iterations=0)
            if method == "random_config_search":
                results, row["random_trials"] = _random_control(problem, config)
            else:
                results = [solve_hybrid(problem, config=search, search_seed=config.search_seed,
                    operation_budget=config.operations, time_limit_seconds=config.seconds)]
            if results:
                winner = min(results, key=lambda result: result.final_solution.total_distance)
                plan = winner.final_solution
                row.update(initial_distance=winner.initial_solution.total_distance,
                           initial_method=winner.initial_solution.method,
                           initial_routes=winner.initial_solution.routes)
                for result in results:
                    row["search_diagnostics"].append(search_diagnostics(result))
                    row["operations_used"] += result.operations_used
                    row["operator_calls"] += result.operator_calls
                    row["accepted_moves"] += result.accepted_moves
                    row["ils_iterations"] += result.ils_iterations
                    row["diversifications"] += result.diversifications
                    row["neighborhoods_truncated"] += result.neighborhoods_truncated
                    row["budget_exhausted"] |= result.budget_exhausted
                    row["timeout"] |= result.termination_reason == "deadline"
                    row["errors"].extend(result.errors)
                    for category, count in result.work_by_category:
                        row["work_by_category"][category] = row["work_by_category"].get(category, 0) + count
                row["construction_candidates"] = [{"method": c.method, "status": c.status,
                    "distance": c.plan.total_distance if c.plan else None, "detail": c.detail,
                    "routes": c.plan.routes if c.plan else None}
                    for c in winner.construction_candidates]
                # Do not lose failures merely because another trial returned a plan.
                row["evaluation_failure"] = bool(row["errors"]) or any(r.status == "failed" for r in results)
                row["status"] = ("failed" if row["evaluation_failure"] else
                    "completed" if all(r.status == "completed" for r in results) else "incomplete")
                row["termination_reason"] = (results[0].termination_reason if len(results) == 1
                                               else "random_trials_finished")
            if not results or (method == "random_config_search" and len(results) < config.random_trials):
                row.update(status="failed" if row["evaluation_failure"] else "incomplete",
                           termination_reason="deadline", timeout=True, budget_exhausted=True)
    except SearchStopped as exc:
        plan = exc.best
        row.update(status="incomplete", termination_reason=budget.reason or "interrupted", budget_exhausted=True)
    except Exception as exc:
        # Exception type only: no arbitrary exception text, matrix dump or traceback.
        row.update(status="failed", termination_reason="exception", evaluation_failure=True,
                   error_type=type(exc).__name__)
    finally:
        if budget:
            row.update(operations_used=budget.used, work_by_category=dict(budget.counts),
                       timeout=budget.reason == "deadline")
    if plan is not None:
        try:
            checked = validate_fleet_solution(problem, plan.routes)
            row.update(feasible=True, total_distance=checked.total_distance,
                       longest_route_distance=checked.longest_route_distance, routes=plan.routes,
                       final_method=getattr(plan, "method", method))
        except Exception as exc:
            row.update(status="failed", termination_reason="invalid_solution", evaluation_failure=True,
                       error_type=type(exc).__name__)
    if problem.fingerprint != before:
        raise RuntimeError("Benchmark method mutated the shared problem")
    row["runtime_seconds"] = time.perf_counter() - start
    return row


def run_case(case, config):
    problem = case.problem(config.search_seed)
    # One object, one matrix, one constraint/objective definition for every method.
    rows = [run_method(problem, method, config) for method in config.methods]
    return {"case_id": case.id, "case": asdict(case), "problem": problem.model_dump(mode="json"),
            "problem_fingerprint": problem.fingerprint, "matrix_fingerprint": problem.matrix_fingerprint,
            "results": rows}
