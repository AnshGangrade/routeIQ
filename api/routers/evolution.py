"""
Evolution endpoints for LLM-guided heuristic discovery.
"""
import uuid
import logging
from api import storage
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.models import (
    StartEvolutionRequest, 
    EvolutionRunResponse, 
    EvolutionProgressResponse,
    BestHeuristicResponse,
    GenerationResult,
    HeuristicInfo
)
from api.storage import evolution_runs
from engine.evolution.config import EvolutionConfig
from engine.evolution.loop import EvolutionLoop
from engine.llm import create_client, LLMConfig, LLMProvider

router = APIRouter()


def run_evolution_background(run_id: str, config: Dict[str, Any]):
    """
    Run evolution in the background using the genuine evolution engine.
    
    Connects to engine.evolution.loop.EvolutionLoop for real evolution.
    """
    client = None
    try:
        with storage.storage_lock:
            if evolution_runs[run_id].get("cancel_requested"):
                evolution_runs[run_id].update(status="cancelled", stage="cancelled")
                return
            evolution_runs[run_id].update(status="running", current_generation=0)
        
        mode = config["mode"]
        
        # Create evolution config
        evo_config = EvolutionConfig(
            num_generations=config["num_generations"],
            candidates_per_generation=config["candidates_per_generation"],
            retained_candidates=config["elites_kept"],
            training_instance_count=config["num_instances"],
            test_instance_count=max(2, config["num_instances"] // 2),
            num_stops=config["num_stops"],
            seed=config["seed"] if config["seed"] is not None else 42,
            llm_mode=mode,
        )
        
        # Create LLM client based on mode
        if mode == "live":
            # Load configuration from environment variables
            from engine.llm import load_config_from_env
            try:
                llm_config = load_config_from_env(model_override=config.get("llm_model"), temperature_override=config.get("temperature"))
            except ValueError as e:
                evolution_runs[run_id]["status"] = "failed"
                evolution_runs[run_id]["error"] = "Live mode configuration is invalid."
                return
        elif mode == "mock":
            # Mock mode - use minimal config
            llm_config = LLMConfig(
                provider=LLMProvider.MOCK,
                base_url="mock://localhost",
                model="mock-model",
                temperature=0.7,
            )
        elif mode == "replay":
            # Replay mode - use minimal config
            llm_config = LLMConfig(
                provider=LLMProvider.REPLAY,
                base_url="replay://localhost",
                model="replay-model",
                replay_fixtures=["simple_nearest", "weighted_heuristic"],
                temperature=0.7,
            )
        else:
            evolution_runs[run_id]["status"] = "failed"
            evolution_runs[run_id]["error"] = f"Unknown mode: {mode}"
            return
        
        overrides = {}
        if config.get("llm_model"):
            overrides["model"] = config["llm_model"]
        if config.get("temperature") is not None:
            overrides["temperature"] = config["temperature"]
        llm_config = LLMConfig(**{**llm_config.model_dump(), **overrides})
        client = create_client(llm_config)
        
        def progress(stage, generation, candidates_done, record):
            state = evolution_runs[run_id]
            state.update(stage="cancelling" if state.get("cancel_requested") else stage, current_generation=generation, candidates_done=candidates_done)
            if record is None:
                return
            generation_result = {
                "generation": record.generation_number,
                "candidates": [
                    {
                        "heuristic_id": cand.candidate_id,
                        "generation": record.generation_number,
                        "parent_id": None,  # TODO: Track parent IDs
                        "code": cand.source_code,
                        "rationale": "",  # MockLLM doesn't provide rationale
                        "is_valid": cand.is_valid,
                        "rejection_reason": "Candidate validation or evaluation failed" if not cand.is_valid else None,
                        "fitness": cand.fitness_score,
                    }
                    for cand in record.candidates
                ],
                "best_fitness": record.best_fitness,
                "valid_count": record.num_valid,
                "invalid_count": record.num_invalid,
            }
            
            state["generations"] = [*state["generations"], generation_result]

        evolution = EvolutionLoop(
            config=evo_config, llm_client=client, progress_callback=progress,
            should_cancel=lambda: evolution_runs[run_id].get("cancel_requested", False),
        )
        run_result = evolution.run_evolution()
        with storage.storage_lock:
            if run_result.status == "cancelled" or evolution_runs[run_id].get("cancel_requested"):
                evolution_runs[run_id].update(status="cancelled", stage="cancelled")
                return
            evolution_runs[run_id]["test_evaluation"] = (
                run_result.test_evaluation.model_dump(mode="json") if run_result.test_evaluation else None
            )
    
            # Mark as completed
            if run_result.status == "completed" and run_result.best_candidate_code:
                evolution_runs[run_id]["best_heuristic_id"] = run_result.best_candidate_id
                evolution_runs[run_id]["best_code"] = run_result.best_candidate_code
                evolution_runs[run_id]["best_fitness"] = run_result.best_training_fitness
                evolution_runs[run_id].update(status="completed", stage="completed")
            else:
                # No valid candidates - mark as failed
                evolution_runs[run_id]["status"] = "failed"
                evolution_runs[run_id]["error"] = "Evolution did not produce a fully evaluated winner."
            
    except Exception as e:
        evolution_runs[run_id]["status"] = "failed"
        evolution_runs[run_id]["error"] = "Evolution failed; no valid comparison is available."
        logging.getLogger(__name__).warning("evolution_failed", extra={"run_id": run_id, "error_type": type(e).__name__})
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                logging.getLogger(__name__).warning("client_cleanup_failed", extra={"run_id": run_id})
        state = evolution_runs[run_id]
        with storage.storage_lock:
            if state.get("cancel_requested") and state["status"] != "completed":
                state.update(status="cancelled", error=None)
            if state["status"] in ("failed", "cancelled"):
                state["stage"] = state["status"]


@router.post("/runs", response_model=EvolutionRunResponse)
async def start_evolution(request: StartEvolutionRequest, background_tasks: BackgroundTasks):
    """
    Start an evolution run.
    
    Runs evolution in the background. Poll /runs/{run_id} for progress.
    
    Modes:
    - 'mock': Use mock LLM responses (fast, no API calls)
    - 'replay': Replay cached LLM responses from a previous run
    - 'live': Make real LLM API calls (requires configuration)
    """
    # Generate run ID
    run_id = uuid.uuid4().hex
    
    # Validate mode
    valid_modes = ["mock", "replay", "live"]
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{request.mode}'. Must be one of: {valid_modes}"
        )
    
    # For live mode, validate environment configuration
    if request.mode == "live":
        import os
        
        # Check for required environment variables
        if not os.getenv("LLM_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="Live mode requires LLM_API_KEY in the process environment."
            )
        
        if not os.getenv("LLM_BASE_URL"):
            raise HTTPException(
                status_code=400,
                detail="Live mode requires LLM_BASE_URL in the process environment."
            )
        
        if not os.getenv("LLM_MODEL") and not request.llm_model:
            raise HTTPException(
                status_code=400,
                detail="Live mode requires a requested model or LLM_MODEL in the process environment."
            )
    
    # Store run configuration
    config = {
        "num_stops": request.num_stops,
        "num_instances": request.num_instances,
        "num_generations": request.num_generations,
        "candidates_per_generation": request.candidates_per_generation,
        "elites_kept": request.elites_kept,
        "seed": request.seed,
        "mode": request.mode,
        "llm_model": request.llm_model,
        "temperature": request.temperature
    }
    
    with storage.storage_lock:
        if len(evolution_runs) >= storage.MAX_RUNS or sum(r["status"] in ("pending", "running", "cancelling") for r in evolution_runs.values()) >= storage.MAX_ACTIVE_RUNS:
            raise HTTPException(status_code=429, detail="Evolution capacity reached; wait for active runs or restart the local server to clear retained runs")
        evolution_runs[run_id] = {
            "run_id": run_id,
            "config": config,
            "status": "pending",
            "current_generation": 0,
            "total_generations": request.num_generations,
            "generations": [],
            "best_heuristic_id": None,
            "error": None
        }
    
    # Start background task
    background_tasks.add_task(run_evolution_background, run_id, config)
    
    return EvolutionRunResponse(
        run_id=run_id,
        status="pending",
        message=f"Evolution run {run_id} started in {request.mode} mode"
    )


@router.get("/runs/{run_id}", response_model=EvolutionProgressResponse)
async def get_evolution_progress(run_id: str):
    """
    Get progress of an evolution run.
    
    Poll this endpoint to track generation-by-generation progress.
    """
    if run_id not in evolution_runs:
        raise HTTPException(status_code=404, detail=f"Evolution run {run_id} not found")
    
    run_data = evolution_runs[run_id]
    
    # Convert to response format
    generations = [
        GenerationResult(
            generation=gen["generation"],
            candidates=[
                HeuristicInfo(**candidate)
                for candidate in gen["candidates"]
            ],
            best_fitness=gen["best_fitness"],
            valid_count=gen["valid_count"],
            invalid_count=gen["invalid_count"]
        )
        for gen in run_data["generations"]
    ]
    
    return EvolutionProgressResponse(
        run_id=run_id,
        status=run_data["status"],
        current_generation=run_data["current_generation"],
        total_generations=run_data["total_generations"],
        generations=generations,
        best_heuristic_id=run_data["best_heuristic_id"],
        error=run_data["error"],
        stage=run_data.get("stage", run_data["status"]),
        candidates_done=run_data.get("candidates_done", 0),
        candidates_per_generation=run_data["config"]["candidates_per_generation"],
        test_evaluation=run_data.get("test_evaluation"),
    )


@router.get("/runs/{run_id}/best", response_model=BestHeuristicResponse)
async def get_best_heuristic(run_id: str):
    """
    Get the best heuristic from a completed evolution run.
    """
    if run_id not in evolution_runs:
        raise HTTPException(status_code=404, detail=f"Evolution run {run_id} not found")
    
    run_data = evolution_runs[run_id]
    
    if run_data["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Evolution run {run_id} is not completed (status: {run_data['status']})"
        )
    
    best_id = run_data["best_heuristic_id"]
    if not best_id:
        raise HTTPException(status_code=404, detail="No best heuristic found")
    
    # Find the best heuristic in generations
    best_heuristic = None
    for gen in run_data["generations"]:
        for candidate in gen["candidates"]:
            if candidate["heuristic_id"] == best_id:
                best_heuristic = candidate
                break
        if best_heuristic:
            break
    
    if not best_heuristic:
        raise HTTPException(status_code=404, detail="Best heuristic data not found")
    
    return BestHeuristicResponse(
        run_id=run_id,
        heuristic=HeuristicInfo(**best_heuristic),
        training_fitness=best_heuristic["fitness"],
        validation_fitness=(run_data.get("test_evaluation") or {}).get("evolved_avg_distance"),
        test_results=None,  # Deprecated: use the structured held-out evaluation.
        test_evaluation=run_data.get("test_evaluation"),
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_evolution(run_id: str):
    state = evolution_runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Evolution run not found")
    with storage.storage_lock:
        if state["status"] in ("pending", "running", "cancelling"):
            state.update(cancel_requested=True, status="cancelling", stage="cancelling")
    return {"run_id": run_id, "status": state["status"]}
