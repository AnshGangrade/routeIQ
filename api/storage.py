"""
In-memory storage for API state.

Stores instances, evolution runs, and routing results.
For production, replace with a database.
"""
from typing import Dict, Any
from threading import RLock, BoundedSemaphore
from contextlib import contextmanager

# Single-process admission control. Reject rather than evict selected instances/runs.
storage_lock = RLock()
MAX_INSTANCES = 100
MAX_RUNS = 100
MAX_ACTIVE_RUNS = 2
_expensive_slots = BoundedSemaphore(4)


@contextmanager
def expensive_request():
    from fastapi import HTTPException
    if not _expensive_slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Server busy; retry after active requests finish")
    try:
        yield
    finally:
        _expensive_slots.release()

# Instance storage: instance_id -> {instance, num_drivers, response}
instance_store: Dict[str, Any] = {}

# Evolution run storage: run_id -> evolution state
evolution_runs: Dict[str, Any] = {}

# Routing results storage: (instance_id, method) -> result
routing_results: Dict[tuple, Any] = {}
