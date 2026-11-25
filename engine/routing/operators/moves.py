"""One bounded neighborhood pass per call, with directed deltas and verified costs.

No operator schedules other operators or repeats to a local optimum. Positions
include the opening depot at index zero. Relocation targets are insertion
positions AFTER removal for same-route moves, and before removal for cross-route
moves. Or-Opt-2 preserves the chain's orientation.
"""
import math
from dataclasses import dataclass, replace

from engine.baselines import two_opt as baseline_two_opt
from ..trusted import MatrixCosts, WorkCounters, bounded_integer, checked_plan

MAX_MOVES = 100_000
MAX_TWO_OPT_ITERATIONS = 100


@dataclass(frozen=True)
class Move:
    kind: str
    driver: int
    start: int
    other_driver: int
    target: int


def _delta_and_builder(problem, routes, move, cost):
    kind, driver, start, other, target = (
        move.kind, move.driver, move.start, move.other_driver, move.target)
    if kind not in ("relocate", "swap", "or_opt_2", "cross_relocate", "cross_exchange"):
        raise ValueError("Unknown move kind")
    if any(type(value) is not int for value in (driver, start, other, target)):
        raise ValueError("Move positions and driver slots must be integers")
    if not (0 <= driver < len(routes) and 0 <= other < len(routes)):
        raise ValueError("Invalid driver slot")
    cross = kind.startswith("cross_")
    if cross == (driver == other):
        raise ValueError("Move has incompatible driver slots")
    source, destination = routes[driver], routes[other]
    width = 2 if kind == "or_opt_2" else 1
    if not 1 <= start <= len(source) - 1 - width:
        raise ValueError("Move cannot include a depot or missing stop")

    if kind in ("swap", "cross_exchange"):
        if not 1 <= target < len(destination) - 1:
            raise ValueError("Swap cannot include a depot or missing stop")
        a, b = source[start], destination[target]
        if not cross:
            edges = sorted({start-1, start, target-1, target})

            def node(position):
                return b if position == start else a if position == target else source[position]

            delta = sum(cost(node(i), node(i+1)) - cost(source[i], source[i+1]) for i in edges)
        else:
            delta = (cost(source[start-1], b) + cost(b, source[start+1])
                     - cost(source[start-1], a) - cost(a, source[start+1])
                     + cost(destination[target-1], a) + cost(a, destination[target+1])
                     - cost(destination[target-1], b) - cost(b, destination[target+1]))

        def build():
            candidate = [list(route) for route in routes]
            candidate[driver][start], candidate[other][target] = b, a
            return candidate
    else:
        if cross and (len(source)-3 < problem.workload.minimum_stops[driver]
                      or len(destination)-1 > problem.workload.maximum_stops[other]):
            raise ValueError("Relocation violates workload bounds")
        reduced_length = len(destination) if cross else len(source) - width
        if not 1 <= target < reduced_length:
            raise ValueError("Invalid relocation insertion position")
        first, last = source[start], source[start+width-1]
        prev, following = source[start-1], source[start+width]

        def remaining_node(position):
            if cross:
                return destination[position]
            return source[position if position < start else position + width]

        left, right = remaining_node(target-1), remaining_node(target)
        # Internal chain arcs cancel; preserve orientation on directed matrices.
        delta = (cost(prev, following) - cost(prev, first) - cost(last, following)
                 + cost(left, first) + cost(last, right) - cost(left, right))

        def build():
            candidate = [list(route) for route in routes]
            chain = candidate[driver][start:start+width]
            del candidate[driver][start:start+width]
            candidate[other][target:target] = chain
            return candidate
    return delta, build


def apply_move(problem, routes, move: Move):
    """Validate an explicit move; return it only if actual fleet D strictly falls.

    Invalid inputs/positions/workloads raise ValueError. Equal/worse moves return
    an immutable snapshot of the original plan. No caller-owned data is modified.
    """
    initial = checked_plan(problem, routes, move.kind, WorkCounters())
    _, build = _delta_and_builder(problem, initial.routes, move, MatrixCosts(problem))
    proposal = checked_plan(problem, build(), move.kind, WorkCounters())
    improved = proposal.total_distance < initial.total_distance
    return replace(proposal if improved else initial,
                   work=WorkCounters(candidates_evaluated=1, full_validations=2,
                                     accepted_moves=int(improved)))


def _moves(problem, routes, kind, budget=None):
    for driver, route in enumerate(routes):
        if budget is not None and not budget.check():
            return
        if len(route) == 2:
            continue
        if kind in ("swap", "relocate", "or_opt_2"):
            width = 2 if kind == "or_opt_2" else 1
            for start in range(1, len(route)-width):
                targets = (range(start+1, len(route)-1) if kind == "swap"
                           else range(1, len(route)-width))
                for target in targets:
                    if target != start:
                        yield Move(kind, driver, start, driver, target)
        else:
            for other, destination in enumerate(routes):
                if budget is not None and not budget.check():
                    return
                if driver == other or (kind == "cross_exchange" and driver > other):
                    continue
                if kind == "cross_relocate" and (
                        len(route)-3 < problem.workload.minimum_stops[driver]
                        or len(destination)-1 > problem.workload.maximum_stops[other]):
                    continue
                for start in range(1, len(route)-1):
                    stop = len(destination) if kind == "cross_relocate" else len(destination)-1
                    for target in range(1, stop):
                        yield Move(kind, driver, start, other, target)


def _improve(problem, routes, kind, max_moves, budget=None):
    bounded_integer(max_moves, "max_moves", MAX_MOVES)
    initial = checked_plan(problem, routes, kind, WorkCounters())
    best, evaluated, validations, truncated = initial, 0, 1, False
    costs = MatrixCosts(problem)
    # Conservative roundoff guard: near-equal delta estimates get full checks.
    tolerance = math.ulp(initial.total_distance) * 32 * (problem.n_stops + problem.num_drivers + 1)
    for move in _moves(problem, initial.routes, kind, budget):
        if evaluated == max_moves:
            truncated = True
            break
        if budget is not None and not budget.consume(kind):
            truncated = True
            break
        delta, build = _delta_and_builder(problem, initial.routes, move, costs)
        evaluated += 1
        if initial.total_distance + delta > best.total_distance + tolerance:
            continue
        proposal = checked_plan(problem, build(), kind, WorkCounters())
        validations += 1
        if proposal.total_distance < best.total_distance:
            best = proposal
    return replace(best, work=WorkCounters(candidates_evaluated=evaluated,
                   full_validations=validations, truncated=truncated or (budget is not None and budget.reason is not None),
                   accepted_moves=int(best.total_distance < initial.total_distance)))


def improve_relocate(problem, routes, *, max_moves=10_000, budget=None):
    return _improve(problem, routes, "relocate", max_moves, budget)


def improve_swap(problem, routes, *, max_moves=10_000, budget=None):
    return _improve(problem, routes, "swap", max_moves, budget)


def improve_or_opt_2(problem, routes, *, max_moves=10_000, budget=None):
    return _improve(problem, routes, "or_opt_2", max_moves, budget)


def improve_cross_relocate(problem, routes, *, max_moves=10_000, budget=None):
    return _improve(problem, routes, "cross_relocate", max_moves, budget)


def improve_cross_exchange(problem, routes, *, max_moves=10_000, budget=None):
    return _improve(problem, routes, "cross_exchange", max_moves, budget)


def improve_two_opt(problem, routes, *, max_iterations=1, budget=None):
    """Wrap the unchanged directed-safe baseline, bounded per driver (1..100).

    Each driver proposal is checked against actual full-fleet cost. Baseline
    internals recompute route costs; baseline_calls counts calls, not edge tests.
    """
    bounded_integer(max_iterations, "max_iterations", MAX_TWO_OPT_ITERATIONS)
    initial = checked_plan(problem, routes, "two_opt", WorkCounters())
    current, calls, accepted = initial, 0, 0
    evaluated = reversals = 0
    def observe(improving):
        nonlocal evaluated, reversals
        evaluated += 1
        reversals += int(improving)
    indices = {node: i for i, node in enumerate(problem.node_ids)}
    matrix = problem.matrix_array()
    for driver, route in enumerate(initial.routes):
        if len(route) < 4:
            continue
        improved = baseline_two_opt([indices[node] for node in route], matrix,
                                     max_iterations=max_iterations,
                                     on_evaluation=observe,
                                     should_continue=(lambda: budget.consume("two_opt")) if budget is not None else None)
        calls += 1
        proposal = list(current.routes)
        proposal[driver] = tuple(problem.node_ids[i] for i in improved.route)
        measured = checked_plan(problem, proposal, "two_opt", WorkCounters())
        if measured.total_distance < current.total_distance:
            current = measured
            accepted += 1
        if budget is not None and budget.reason is not None:
            break
    return replace(current, work=WorkCounters(full_validations=1+calls,candidates_evaluated=evaluated,
                   candidate_acceptances=reversals,
                   baseline_calls=calls, accepted_moves=accepted,
                   truncated=budget is not None and budget.reason is not None))
