"""Bounded application jobs around the unchanged trusted hybrid solver."""
from copy import deepcopy
import logging
import re
from threading import Event, RLock
import time
from typing import Literal
import uuid

import numpy as np
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import Field, model_validator
from api import storage
from api.models import DriverRouteResponse, RoutingResultResponse
from api.routers import routing, strategies
from engine.routing.search import SearchConfig, solve_hybrid
from engine.routing.validation import validate_fleet_solution
from engine.strategies.models import StrictModel, StrategyRecord
from engine.strategies.adaptive import AdaptiveController, ControllerUnavailable
from engine.strategies.adaptive_models import AdaptiveRequest

router = APIRouter()
jobs: dict = {}
lock = RLock()
MAX_JOBS = 50
MAX_ACTIVE = 2


class OptimizeRequest(StrictModel):
    instance_id: str = Field(min_length=1, max_length=100)
    method: Literal['portfolio', 'vnd', 'vnd_ils', 'strategy', 'adaptive'] = 'vnd'
    operations: int = Field(100000, strict=True, ge=0, le=500000)
    seconds: float = Field(10., ge=0, le=30)
    search_seed: int = Field(0, strict=True, ge=0, le=4294967295)
    strategy_job_id: str | None = Field(None, max_length=100)
    strategy_id: str | None = Field(None, max_length=200)
    adaptive: AdaptiveRequest | None = None

    @model_validator(mode='after')
    def strategy_identity(self):
        if (self.method=='adaptive') != (self.adaptive is not None):
            raise ValueError('Adaptive optimization requires explicit provider/controller configuration')
        if self.method == 'strategy' and not (self.strategy_job_id and self.strategy_id):
            raise ValueError('Select an evaluated strategy and its experiment')
        if self.method != 'strategy' and (self.strategy_job_id or self.strategy_id):
            raise ValueError('Strategy identifiers require the strategy method')
        return self


def resolve(request):
    stored = storage.instance_store.get(request.instance_id)
    if stored is None:
        raise HTTPException(404, 'Selected route plan not found; create a new plan after restarting the server')
    problem = stored.get('problem')
    instance = stored['instance']
    if (problem is None or not np.array_equal(stored.get('distance_matrix'), problem.matrix_array())
            or problem.num_drivers != stored['num_drivers']
            or tuple((p.x, p.y) for p in instance.get_all_locations()) != problem.coordinates
            or tuple(stop.id for stop in instance.stops) != problem.stop_ids or instance.depot.id != problem.depot_id):
        raise HTTPException(409, 'Stored plan and distance matrix disagree; create a new plan')
    config = SearchConfig(ils_iterations=8 if request.method == 'vnd_ils' else 0,
                          operators=() if request.method == 'portfolio' else tuple(SearchConfig().operators))
    constructor = 'portfolio'
    fingerprint = None
    if request.method == 'strategy':
        state = strategies.snapshot(request.strategy_job_id)
        if state['status'] not in ('completed', 'stopped'):
            raise HTTPException(409, 'Only an evaluated strategy from a terminal experiment can be applied')
        raw = state.get('records', {}).get(request.strategy_id)
        if raw is None:
            raise HTTPException(404, 'Strategy does not belong to this experiment')
        record = StrategyRecord.model_validate(raw)
        if not record.fitness.get('eligible') or not record.evaluation_history:
            raise HTTPException(409, 'Strategy has no valid complete development panel')
        config, constructor, fingerprint = record.config.search_config(), record.config.construction, record.configuration_fingerprint
    return stored, problem, config, constructor, fingerprint


def execute(job_id, request, resolved):
    stored, problem, config, constructor, fingerprint = resolved
    entry = jobs[job_id]
    cancel = entry['cancel']
    def update(**values):
        with lock:
            entry['state'].update(values)
    controller=None
    try:
        if cancel.is_set():
            update(status='cancelled', stage='finished', termination='cancelled')
            return
        update(status='running', stage='optimizing')
        if request.adaptive is not None:
            experience=[strategies.snapshot(i) for i in request.adaptive.experience_job_ids]
            controller=AdaptiveController(request.adaptive,experience=experience,
                progress=lambda evidence:update(stage='adaptive_search',controller=evidence))
        with storage.expensive_request():
            outcome = solve_hybrid(problem, construction_strategy=constructor, config=config,
                search_seed=request.search_seed, operation_budget=request.operations,
                time_limit_seconds=request.seconds, should_cancel=cancel.is_set,**({'controller':controller} if controller else {}))
            measured = validate_fleet_solution(problem, outcome.final_solution.routes)
            execution = {
                **outcome.execution_contract,
                'status': 'failed' if outcome.errors or outcome.status == 'failed' else
                          'completed' if outcome.status == 'completed' else 'incomplete',
                'termination': outcome.termination_reason, 'initial_distance': outcome.initial_solution.total_distance,
                'final_distance': measured.total_distance, 'improvement_percent': outcome.improvement_percent,
                'initial_definition': 'best validated constructor within this budget',
                'operations': outcome.operations_used, 'operation_limit': outcome.operation_limit,
                'search_seed': outcome.search_seed, 'budget_exhausted': outcome.budget_exhausted,
                'operator_calls': outcome.operator_calls, 'accepted_moves': outcome.accepted_moves,
                'ils_iterations': outcome.ils_iterations, 'selected_source': outcome.final_solution.method,
                'work_by_category': dict(outcome.work_by_category), 'errors': list(outcome.errors),
                'strategy_job_id': request.strategy_job_id, 'strategy_id': request.strategy_id,
                'strategy_fingerprint': fingerprint,
                'controller':outcome.controller,
                'operator_telemetry':dict(outcome.operator_telemetry),
                'constructors': [{'method': c.method, 'status': c.status,
                    'distance': c.plan.total_distance if c.plan else None} for c in outcome.construction_candidates],
                'raw_events': [{'stage': e.stage, 'method': e.method, 'status': e.status,
                    'raw_distance': e.raw_candidate.total_distance if e.raw_candidate else None,
                    'retained_distance': e.best_distance, 'accepted': e.accepted} for e in outcome.events],
            }
            if cancel.is_set() or outcome.termination_reason == 'cancelled':
                update(status='cancelled', stage='finished', termination='cancelled', execution=execution)
                return
            if execution['status'] == 'failed':
                update(status='failed', stage='finished', termination=outcome.termination_reason,
                       error='Optimization failed; no result was published.', execution=execution)
                return
            update(stage='road_geometry' if stored['mode'] == 'road' else 'validating')
            drivers = []
            for index, route in enumerate(outcome.final_solution.routes):
                if cancel.is_set():
                    update(status='cancelled', stage='finished', termination='cancelled', execution=execution)
                    return
                geometry, duration, error = ((None, None, None) if len(route) == 2 else
                    routing.get_route_geometry_if_road(stored, list(route)))
                drivers.append(DriverRouteResponse(driver_id=index, route=list(route), distance=measured.route_distances[index],
                    geometry=geometry, duration=duration, geometry_error=error))
            response = RoutingResultResponse(instance_id=request.instance_id, method=request.method, drivers=drivers,
                total_distance=measured.total_distance, longest_route_distance=measured.longest_route_distance,
                computation_time=outcome.elapsed_seconds, problem_fingerprint=problem.fingerprint,
                matrix_fingerprint=problem.matrix_fingerprint, distance_units=problem.distance_units,
                feasible=True, execution=execution)
            with lock:
                if cancel.is_set():
                    update(status='cancelled', stage='finished', termination='cancelled', execution=execution)
                    return
                with storage.storage_lock:
                    storage.routing_results[(request.instance_id, request.method)] = response
                update(status=execution['status'], stage='finished', termination=outcome.termination_reason,
                       result=response.model_dump(mode='json'), execution=execution)
    except ControllerUnavailable:
        update(status='cancelled' if cancel.is_set() else 'failed',stage='finished',
               termination='cancelled' if cancel.is_set() else 'controller_unavailable',
               error=None if cancel.is_set() else 'AI strategy selection failed or exceeded its budget. Previous routes remain available; no random search was substituted.')
    except Exception as exc:
        logging.getLogger(__name__).warning('application_optimization_failed', extra={'job_id': job_id, 'error_type': type(exc).__name__})
        update(status='cancelled' if cancel.is_set() else 'failed', stage='finished',
               termination='cancelled' if cancel.is_set() else 'request_failure',
               error=None if cancel.is_set() else 'Optimization unavailable. Retry with the same plan or a smaller budget.')
    finally:
        if controller is not None: controller.close()


@router.post('/jobs', status_code=202)
def start(request: OptimizeRequest, tasks: BackgroundTasks):
    resolved = resolve(request)
    if request.adaptive is not None:
        check=strategies.check_provider(request.adaptive.provider)
        if not check.get('available'):
            raise HTTPException(503,check['message'])
        from engine.strategies.experience import development_experience
        try:
            development_experience([strategies.snapshot(i) for i in request.adaptive.experience_job_ids],resolved[1])
        except (ValueError,KeyError,TypeError):
            raise HTTPException(422,'Selected experience is not verified terminal development evidence') from None
    with lock:
        if len(jobs) >= MAX_JOBS or sum(j['state']['status'] in ('pending', 'running', 'cancelling') for j in jobs.values()) >= MAX_ACTIVE:
            raise HTTPException(429, 'Optimization capacity reached; finish active jobs or restart the local server to clear retained jobs')
        if any(j['state']['instance_id'] == request.instance_id and j['state']['status'] in ('pending', 'running', 'cancelling') for j in jobs.values()):
            raise HTTPException(409, 'This plan already has an active optimization')
        job_id = uuid.uuid4().hex
        jobs[job_id] = {'cancel': Event(), 'started': time.monotonic(), 'state': {
            'job_id': job_id, 'instance_id': request.instance_id, 'method': request.method,
            'problem_fingerprint': resolved[1].fingerprint, 'matrix_fingerprint': resolved[1].matrix_fingerprint,
            'status': 'pending', 'stage': 'queued', 'result': None, 'error': None,
            'request': request.model_dump(mode='json')}}
    tasks.add_task(execute, job_id, request, resolved)
    return deepcopy(jobs[job_id]['state'])


def find(job_id):
    if not re.fullmatch('[0-9a-f]{32}', job_id) or job_id not in jobs:
        raise HTTPException(404, 'Optimization job not found')
    return jobs[job_id]


@router.get('/jobs/{job_id}')
def status(job_id: str):
    with lock:
        entry = find(job_id)
        return deepcopy(entry['state'])


@router.post('/jobs/{job_id}/cancel')
def cancel(job_id: str):
    with lock:
        entry = find(job_id)
        if entry['state']['status'] in ('pending', 'running', 'cancelling'):
            entry['cancel'].set()
            entry['state']['status'] = 'cancelling'
        return {'job_id': job_id, 'instance_id': entry['state']['instance_id'], 'status': entry['state']['status']}
