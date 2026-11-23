"""Extend source provenance without changing Phase 5B's frozen guard."""
from engine.evaluation.fleet_benchmark import software_record as benchmark_software
from engine.evaluation.fleet_dataset import digest


def software_record(root):
    paths=('scripts/run_strategy_evolution.py','api/routers/strategies.py','api/main.py')
    return {**benchmark_software(root),'strategy_entrypoints':
        digest([(name,(root/name).read_text(encoding='utf-8-sig')) for name in paths])}
