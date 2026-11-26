"""Deterministic portfolio + restart-on-improvement VND + bounded seeded ILS."""
import random
import time
from dataclasses import dataclass, replace
from .control import WorkSlice, StrategyController
from .status import search_status

from .budget import SearchBudget, SearchStopped
from .construction import (
    _target_counts, nearest_neighbor_starts, cheapest_insertion,
    contiguous_sweep, legacy_angular_round_robin,
)
from .operators import (
    improve_relocate, improve_swap, improve_or_opt_2, improve_two_opt,
    improve_cross_relocate, improve_cross_exchange,
)
from .trusted import TrustedPlan, WorkCounters, checked_plan

OPERATORS = {
    "relocate": improve_relocate, "swap": improve_swap, "or_opt_2": improve_or_opt_2,
    "two_opt": improve_two_opt, "cross_relocate": improve_cross_relocate,
    "cross_exchange": improve_cross_exchange,
}
CONSTRUCTORS = ("legacy_nn", "legacy_2opt", "nearest_neighbor_starts",
                "cheapest_insertion", "contiguous_sweep")


@dataclass(frozen=True)
class SearchConfig:
    operators: tuple[str, ...] = tuple(OPERATORS)
    nn_attempts: int = 4
    max_operator_calls: int = 500
    max_moves_per_operator: int = 10_000
    two_opt_iterations: int = 1
    ils_iterations: int = 8
    perturbation_moves: int = 2
    max_diversifications: int = 3

    def __post_init__(self):
        object.__setattr__(self, "operators", tuple(self.operators))
        if len(set(self.operators)) != len(self.operators) or any(op not in OPERATORS for op in self.operators):
            raise ValueError("Operators must be unique trusted operator names")
        limits = {"nn_attempts": (1, 16), "max_operator_calls": (0, 1000),
                  "max_moves_per_operator": (1, 100_000), "two_opt_iterations": (1, 100),
                  "ils_iterations": (0, 100), "perturbation_moves": (1, 8),
                  "max_diversifications": (0, 100)}
        for name, (minimum, maximum) in limits.items():
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be an integer in {minimum}..{maximum}")


@dataclass(frozen=True)
class CandidateReport:
    method: str
    status: str
    plan: TrustedPlan | None = None
    detail: str | None = None


@dataclass(frozen=True)
class SearchEvent:
    stage: str
    method: str
    raw_candidate: TrustedPlan | None
    accepted: bool
    best_distance: float
    operations_used: int
    status: str = "completed"


@dataclass(frozen=True)
class HybridResult:
    initial_solution: TrustedPlan
    final_solution: TrustedPlan
    improvement_percent: float
    construction_candidates: tuple[CandidateReport, ...]
    events: tuple[SearchEvent, ...]
    search_seed: int
    operators_executed: tuple[str, ...]
    accepted_moves: int
    operator_calls: int
    ils_iterations: int
    diversifications: int
    operations_used: int
    operation_limit: int
    work_by_category: tuple[tuple[str, int], ...]
    elapsed_seconds: float
    termination_reason: str
    budget_exhausted: bool
    neighborhoods_truncated: int
    status: str
    errors: tuple[str, ...] = ()
    operator_telemetry: tuple[tuple[str, dict], ...] = ()
    controller: dict | None = None

    @property
    def execution_contract(self):
        return search_status(self.termination_reason, truncated=self.neighborhoods_truncated, errors=self.errors)


def _bootstrap(problem):
    """Linear route assembly plus mandatory validation/problem fingerprinting.

    This enables zero-budget/pre-cancelled calls to return a validated plan.
    It is named explicitly and never presented as a measured baseline.
    """
    routes, offset = [], 0
    for count in _target_counts(problem):
        routes.append((problem.depot_id, *problem.stop_ids[offset:offset+count], problem.depot_id))
        offset += count
    return checked_plan(problem, routes, "ordered_feasible_seed", WorkCounters(full_validations=1))


class _Search:
    def __init__(self, problem, config, budget, seed):
        self.problem, self.config, self.budget = problem, config, budget
        self.rng = random.Random(seed)
        self.best = _bootstrap(problem)
        self.events, self.errors, self.executed = [], [], []
        self.calls = self.accepted = self.truncated = 0
        self.iterations = self.diversifications = 0
        self.reason = None
        self.operator_stats = {name:{'calls':0,'attempts':0,'accepted_improvements':0,
            'rejected_moves':0,'operations':0,'distance_reduction':0.,'failures':0} for name in OPERATORS}

    def record(self, stage, method, proposal, accepted, status="completed"):
        # Recompute independently even if an operator supplied plausible metrics.
        plan = checked_plan(self.problem, proposal.routes, proposal.method, proposal.work)
        selected = plan.total_distance < self.best.total_distance or (
            stage == "construction" and method.startswith("legacy_")
            and self.best.method == "ordered_feasible_seed"
            and plan.total_distance == self.best.total_distance)
        if selected:
            self.best = plan
        self.events.append(SearchEvent(stage, method, plan, selected if accepted is None else accepted,
                                       self.best.total_distance, self.budget.used, status))
        return plan

    def vnd(self, initial):
        current, index = initial, 0
        while index < len(self.config.operators):
            if not self.budget.check():
                break
            if self.calls == self.config.max_operator_calls:
                self.reason = "operator_call_limit"
                break
            if not self.budget.consume("operator_call"):
                break
            method = self.config.operators[index]
            self.calls += 1
            self.executed.append(method)
            stats=self.operator_stats[method]
            stats['calls']+=1
            before_work=self.budget.used-1  # Include the charged operator invocation.
            try:
                kwargs = ({"max_iterations": self.config.two_opt_iterations} if method == "two_opt"
                          else {"max_moves": self.config.max_moves_per_operator})
                raw = OPERATORS[method](self.problem, current.routes, budget=self.budget, **kwargs)
                verified = checked_plan(self.problem, raw.routes, raw.method, raw.work)
                accepted = verified.total_distance < current.total_distance
                accepts=raw.work.candidate_acceptances if raw.work.candidate_acceptances is not None else raw.work.accepted_moves
                stats['attempts']+=raw.work.candidates_evaluated
                stats['accepted_improvements']+=accepts
                stats['rejected_moves']+=max(0,raw.work.candidates_evaluated-accepts)
                # Credit only a new global best, not recovering a diversification loss.
                stats['distance_reduction']+=max(0.,self.best.total_distance-verified.total_distance)
                self.record("vnd", method, verified, accepted,
                            "interrupted" if self.budget.reason else "truncated" if raw.work.truncated else "completed")
                self.truncated += int(raw.work.truncated and self.budget.reason is None)
                if accepted:
                    current = verified
                    self.accepted += verified.work.accepted_moves or 1
                    index = 0  # VND restarts after each strict improvement.
                else:
                    index += 1
            except Exception as exc:
                stats['failures']+=1
                self.reason = "operator_error"
                self.errors.append(f"{method}: {type(exc).__name__}")
                self.events.append(SearchEvent("vnd", method, None, False,
                    self.best.total_distance, self.budget.used, "failed"))
                break
            finally:
                stats['operations']+=self.budget.used-before_work
        return current

    def adaptive(self, controller, allocation):
        """Checkpointed scheduling of the same VND/perturbation primitives.

        Unlike the static portfolio walk, adaptive scheduling starts at the best
        constructor and uses explicit work slices. It never resets the budget.
        """
        parent=self.budget
        current=self.best
        previous=self.best.total_distance
        for checkpoint in range(controller.max_checkpoints+1):
            if self.reason or not parent.check(): break
            # Reserve real work after feedback, even when a proposal asks for the
            # entire remaining allowance. The parent alone owns the global cap.
            share=max(1,(parent.limit-parent.used)//(controller.max_checkpoints-checkpoint+1))
            self.budget=WorkSlice(parent,min(allocation,share)) if checkpoint<controller.max_checkpoints else parent
            try: current=self.vnd(current)
            finally: self.budget=parent
            if self.reason or not parent.check() or checkpoint==controller.max_checkpoints: break
            stats={k:{**v,'improvement_per_operation':v['distance_reduction']/v['operations'] if v['operations'] else None}
                   for k,v in self.operator_stats.items()}
            delta=previous-self.best.total_distance
            telemetry={'checkpoint':checkpoint+1,'best_distance':self.best.total_distance,
                'improvement_since_checkpoint':delta,'stagnated':delta==0,
                'operations':parent.used,'operator_calls':self.calls,'elapsed_seconds':parent.elapsed,
                'remaining_operations':parent.limit-parent.used,'remaining_seconds':max(0.,parent.deadline-parent.clock()),
                'operator_statistics':stats,'operator_order':list(self.config.operators),
                'diversifications_remaining':max(0,min(self.config.ils_iterations,self.config.max_diversifications)-self.diversifications),
                'counter_definition':'attempts are scanned candidates; rejections include candidates not retained by best-scan operators; two_opt counts actual reversal decisions'}
            action=controller.checkpoint(telemetry,parent)
            previous=self.best.total_distance
            if not parent.check(): break
            # Validate again at the optimizer boundary; controllers cannot raise host caps.
            if action.action not in ('continue','reorder','diversify','stop'):
                raise ValueError('Unsupported controller action')
            if type(action.operation_slice) is not int or not 100<=action.operation_slice<=20000:
                raise ValueError('Invalid checkpoint allocation')
            applied={'action':action.action,'status':'applied','host_decision':'accepted',
                     'schedule_changed':False,'remaining_operations':parent.limit-parent.used}
            if action.action=='stop':
                if hasattr(controller,'applied'): controller.applied(applied)
                self.reason='controller_stop'; break
            if action.action=='reorder':
                applied['schedule_changed']=tuple(action.operators)!=self.config.operators
                self.config=replace(self.config,operators=action.operators)
            if action.max_moves is not None:
                applied['schedule_changed'] |= action.max_moves!=self.config.max_moves_per_operator
                self.config=replace(self.config,max_moves_per_operator=action.max_moves)
            allocation=action.operation_slice
            current=self.best
            if action.action=='diversify' and telemetry['diversifications_remaining']>0 and telemetry['stagnated']:
                proposal=self.perturb(current)
                if proposal is not None:
                    self.diversifications+=1
                    self.iterations+=1
                    current=proposal
                    applied['schedule_changed']=True
                else: applied.update(status='not_applied',host_decision='denied',reason='no_valid_perturbation')
            elif action.action=='diversify':
                applied.update(status='not_applied',host_decision='denied',reason='no_stagnation_or_diversification_allowance')
            if action.action=='reorder' and not applied['schedule_changed']:
                applied['effect']='ineffective: requested schedule already active'
            if hasattr(controller,'applied'): controller.applied(applied)

    def perturb(self, current):
        positions = [(driver, position) for driver, route in enumerate(current.routes)
                     for position in range(1, len(route)-1)]
        if len(positions) < 2:
            return None
        candidate = current
        previous_pair = None
        for _ in range(self.config.perturbation_moves):
            if not self.budget.consume("perturbation"):
                break
            a, b = sorted(self.rng.sample(range(len(positions)), 2))
            # Avoid immediately undoing the preceding swap when another pair exists.
            if (a, b) == previous_pair and len(positions) > 2:
                b = (b + 1) % len(positions)
                if b == a:
                    b = (b + 1) % len(positions)
                a, b = sorted((a, b))
            previous_pair = (a, b)
            driver, start = positions[a]
            other, target = positions[b]
            routes = [list(route) for route in candidate.routes]
            routes[driver][start], routes[other][target] = routes[other][target], routes[driver][start]
            candidate = checked_plan(self.problem, routes, "ils_perturbation", WorkCounters(full_validations=1))
            # Perturbations may worsen the walk, but never replace a better global incumbent.
            candidate = self.record("perturbation", "swap", candidate, False)
        return candidate

    def ils(self):
        current = self.best
        for _ in range(self.config.ils_iterations):
            if self.reason or not self.budget.check():
                return
            candidate = self.perturb(current)
            if candidate is None:
                self.reason = "no_perturbation_available"
                return
            candidate = self.vnd(candidate)
            self.iterations += 1
            if self.reason or self.budget.reason:
                return
            improving = candidate.total_distance < current.total_distance
            accepted = improving
            if not accepted and candidate.routes != current.routes and self.diversifications < self.config.max_diversifications:
                self.diversifications += 1
                accepted = True
            current = candidate if accepted else self.best
            self.record("ils_acceptance", "improvement" if improving else "diversification" if accepted
                        else "restart_best", candidate, accepted)
        if self.config.ils_iterations:
            self.reason = "ils_iteration_limit"


def _solve_hybrid(problem, *, construction_strategy="portfolio", config=None,
                 search_seed=None, operation_budget=100_000, time_limit_seconds=10.0,
                 should_cancel=None, clock=time.monotonic, controller=None):
    """Return a validated incumbent plus honest raw results and termination metadata.

    Search work is bounded by candidate evaluations and call/iteration caps.
    Deadline/cancellation are cooperative inside scans. Bootstrap and final
    validation always finish, so even an immediate stop has a feasible result.
    """
    config = config or SearchConfig()
    if construction_strategy != "portfolio" and construction_strategy not in CONSTRUCTORS:
        raise ValueError("Unknown construction strategy")
    seed = search_seed if search_seed is not None else problem.search_seed
    seed = 0 if seed is None else seed
    if type(seed) is not int:
        raise ValueError("search_seed must be an integer")
    # Separate search randomness from problem identity; never modify caller's model.
    budget = SearchBudget(operation_budget, time_limit_seconds, should_cancel, clock=clock)
    seeded_problem = type(problem).model_validate({**problem.model_dump(), "search_seed": seed})
    search = _Search(seeded_problem, config, budget, seed)
    if controller is not None:
        if not 0<=controller.max_checkpoints<=8: raise ValueError('Invalid checkpoint cap')
        choice=controller.initialize(seeded_problem,budget,seed)
        config=SearchConfig(**choice.config.__dict__)
        if choice.construction not in ('portfolio',*CONSTRUCTORS): raise ValueError('Unknown controller construction')
        if type(choice.operation_slice) is not int or not 100<=choice.operation_slice<=20000: raise ValueError('Invalid initial allocation')
        construction_strategy=choice.construction
        search.config=config
    candidates = [CandidateReport("ordered_feasible_seed", "completed", search.best)]
    methods = CONSTRUCTORS if construction_strategy == "portfolio" else tuple(dict.fromkeys(
        ("legacy_nn", "legacy_2opt", construction_strategy)))
    optional_budget = None
    for method in methods:
        if not budget.check():
            candidates.append(CandidateReport(method, "not_started"))
            continue
        if method == "contiguous_sweep" and (seeded_problem.coordinates is None
                or seeded_problem.coordinate_system != "cartesian" or seeded_problem.directed
                or seeded_problem.matrix_provenance.source != "euclidean"):
            candidates.append(CandidateReport(method, "not_applicable"))
            continue
        if method.startswith("legacy_") and seeded_problem.coordinates is None and seeded_problem.num_drivers > 1 and seeded_problem.n_stops:
            candidates.append(CandidateReport(method, "not_applicable", detail="Legacy assignment requires coordinates"))
            continue
        try:
            # Mandatory comparators retain their historical full traversal. Only
            # optional constructors share at most one third of remaining work.
            # Their interrupted candidates remain explicit, never full baselines.
            if controller is not None and not method.startswith('legacy_'):
                if optional_budget is None:
                    optional_budget=WorkSlice(budget,max(0,(budget.limit-budget.used)//3))
                constructor_budget=optional_budget
            else:
                constructor_budget=budget
            constructor_budget.require("constructor_call")
            if method.startswith("legacy_"):
                raw = legacy_angular_round_robin(seeded_problem,
                    method="nearest_neighbor" if method == "legacy_nn" else "2opt", budget=constructor_budget)
            elif method == "nearest_neighbor_starts":
                raw = nearest_neighbor_starts(seeded_problem, attempts=config.nn_attempts, budget=constructor_budget)
            elif method == "cheapest_insertion":
                raw = cheapest_insertion(seeded_problem, budget=constructor_budget)
            else:
                raw = contiguous_sweep(seeded_problem, budget=constructor_budget)
            status = "interrupted" if constructor_budget.reason else "completed"
            plan = search.record("construction", method, raw, None, status)
            candidates.append(CandidateReport(method, status, plan))
        except SearchStopped as exc:
            plan = search.record("construction", method, exc.best, None, "interrupted") if exc.best else None
            candidates.append(CandidateReport(method, "interrupted", plan))
        except Exception as exc:
            candidates.append(CandidateReport(method, "failed", detail=type(exc).__name__))
            search.errors.append(f"{method}: {type(exc).__name__}")
    initial = search.best
    # Improve each distinct constructed plan, shortest first, retaining all global gains.
    if controller is not None:
        search.adaptive(controller,choice.operation_slice)
    else:
        seen = set()
        for candidate in sorted((c.plan for c in candidates if c.plan), key=lambda p: p.total_distance):
            if candidate.routes in seen:
                continue
            seen.add(candidate.routes)
            if search.reason or not budget.check():
                break
            search.vnd(candidate)
        if not search.reason and budget.check():
            search.ils()
    reason = budget.reason or search.reason or ("neighborhood_limit" if search.truncated else "local_search_complete")
    if search.errors and reason == "local_search_complete":
        reason = "completed_with_errors"
    final = checked_plan(seeded_problem, search.best.routes, search.best.method, search.best.work)
    improvement = (initial.total_distance - final.total_distance) / initial.total_distance * 100 if initial.total_distance else 0.0
    contract=search_status(reason,truncated=search.truncated,errors=search.errors)
    exhausted=contract['budget_exhausted']
    status=contract['search_status'] if contract['search_status'] in ('failed','completed') else 'stopped'
    evidence=controller.snapshot() if controller is not None else None
    if evidence is not None:
        evidence.update(termination=reason,final_distance=final.total_distance,operations_used=budget.used,
                        final_routes_fingerprint=problem._digest(final.routes))
    return HybridResult(initial, final, improvement, tuple(candidates), tuple(search.events), seed,
        tuple(search.executed), search.accepted, search.calls, search.iterations, search.diversifications,
        budget.used, budget.limit, tuple(sorted(budget.counts.items())), budget.elapsed, reason,
        exhausted, search.truncated, status, tuple(search.errors),tuple(search.operator_stats.items()),
        evidence)


def solve_hybrid(problem, *, construction_strategy="portfolio", config=None,
                 search_seed=None, operation_budget=100_000, time_limit_seconds=10.0,
                 should_cancel=None, clock=time.monotonic, controller: StrategyController | None=None):
    try:
        result=_solve_hybrid(problem,construction_strategy=construction_strategy,config=config,search_seed=search_seed,
            operation_budget=operation_budget,time_limit_seconds=time_limit_seconds,should_cancel=should_cancel,
            clock=clock,controller=controller)
        if controller is not None and hasattr(controller,'verify_result'): controller.verify_result(result)
        return result
    finally:
        if controller is not None: controller.close()
