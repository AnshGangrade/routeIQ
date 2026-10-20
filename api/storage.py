"""
In-memory storage for API state.

Stores instances, evolution runs, and routing results.
For production, replace with a database.
"""
from typing import Dict, Any

# Instance storage: instance_id -> {instance, num_drivers, response}
instance_store: Dict[str, Any] = {}

# Evolution run storage: run_id -> evolution state
evolution_runs: Dict[str, Any] = {}

# Routing results storage: (instance_id, method) -> result
routing_results: Dict[tuple, Any] = {}
