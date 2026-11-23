"""Reproducible offline diagnostic; synthetic matrices only, no app/environment loading."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.instances import InstanceGenerator
from engine.routing import FleetProblem, validate_fleet_solution
from engine.routing.search import SearchConfig, solve_hybrid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='runs/hybrid-search-benchmark.json')
    parser.add_argument('--operations', type=int, default=1_000_000)
    parser.add_argument('--seconds', type=float, default=60)
    args = parser.parse_args()
    config = SearchConfig(max_operator_calls=1000, ils_iterations=5)
    rows = []
    for label, n, drivers in [('uniform', 20, 3), ('uniform', 50, 5),
                               ('uniform', 100, 5), ('zero_distance_control', 20, 3)]:
        problem = InstanceGenerator(seed=42).generate_problem(n, drivers, search_seed=0)
        if label == 'zero_distance_control':
            problem = FleetProblem.model_validate({**problem.model_dump(),
                'distance_matrix': [[0.]*(n+1)]*(n+1), 'coordinates': [(0., 0.)]*(n+1)})
        result = solve_hybrid(problem, config=config, operation_budget=args.operations,
                              time_limit_seconds=args.seconds)
        for plan in (result.initial_solution, result.final_solution):
            checked = validate_fleet_solution(problem, plan.routes)
            assert checked.total_distance == plan.total_distance
        assert result.final_solution.total_distance <= result.initial_solution.total_distance
        row = {
            'case': label, 'stops': n, 'drivers': drivers, 'instance_seed': 42, 'search_seed': 0,
            'problem_fingerprint': problem.fingerprint, 'distance_units': problem.distance_units,
            'initial_distance': result.initial_solution.total_distance,
            'final_distance': result.final_solution.total_distance,
            'longest_route_distance': result.final_solution.longest_route_distance,
            'improvement_percent': result.improvement_percent,
            'initial_method': result.initial_solution.method, 'final_method': result.final_solution.method,
            'initial_routes': result.initial_solution.routes, 'final_routes': result.final_solution.routes,
            'operator_calls': result.operator_calls, 'operator_call_counts': dict(Counter(result.operators_executed)),
            'accepted_moves': result.accepted_moves, 'ils_iterations': result.ils_iterations,
            'diversifications': result.diversifications, 'elapsed_seconds': result.elapsed_seconds,
            'operations_used': result.operations_used, 'operation_limit': result.operation_limit,
            'work_by_category': dict(result.work_by_category), 'termination_reason': result.termination_reason,
            'budget_exhausted': result.budget_exhausted, 'status': result.status,
            'construction_candidates': [{'method': c.method, 'status': c.status,
                'distance': c.plan.total_distance if c.plan else None} for c in result.construction_candidates],
        }
        rows.append(row)
        print(f"{label} n={n} k={drivers}: {row['initial_distance']:.6f} -> "
              f"{row['final_distance']:.6f} ({row['improvement_percent']:.3f}%), "
              f"calls={result.operator_calls}, accepted={result.accepted_moves}, "
              f"work={result.operations_used}/{result.operation_limit}, "
              f"time={result.elapsed_seconds:.3f}s, {result.termination_reason}, ILS={result.ils_iterations}", flush=True)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'config': {
        'operations': args.operations, 'seconds': args.seconds, 'operator_call_limit': 1000,
        'ils_iteration_limit': 5, 'perturbation_moves': config.perturbation_moves,
        'max_diversifications': config.max_diversifications}, 'results': rows}, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
