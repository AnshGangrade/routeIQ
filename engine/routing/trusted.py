"""Shared immutable output for trusted constructors and independent operators."""
from dataclasses import dataclass

from .problem import FleetProblem
from .validation import validate_fleet_solution

Routes = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class WorkCounters:
    candidates_evaluated: int = 0
    full_validations: int = 0
    attempts: int = 0
    baseline_calls: int = 0
    accepted_moves: int = 0
    truncated: bool = False
    candidate_acceptances: int | None = None


@dataclass(frozen=True)
class TrustedPlan:
    routes: Routes
    route_distances: tuple[float, ...]
    total_distance: float
    longest_route_distance: float
    problem_fingerprint: str
    method: str
    work: WorkCounters


def checked_plan(problem: FleetProblem, routes, method: str, work: WorkCounters) -> TrustedPlan:
    frozen = tuple(tuple(route) for route in routes)
    measured = validate_fleet_solution(problem, frozen)
    return TrustedPlan(frozen, measured.route_distances, measured.total_distance,
                       measured.longest_route_distance, problem.fingerprint, method, work)


def bounded_integer(value, name, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in 1..{maximum}")


class MatrixCosts:
    """ID-aware directed arc access, including the contract's idle-route convention."""
    def __init__(self, problem):
        self.indices = {node: i for i, node in enumerate(problem.node_ids)}
        self.matrix = problem.distance_matrix
        self.depot = problem.depot_id

    def __call__(self, a, b):
        if a == b == self.depot:
            return 0.0
        return self.matrix[self.indices[a]][self.indices[b]]
