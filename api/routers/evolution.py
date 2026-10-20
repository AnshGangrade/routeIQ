"""
Evolution endpoints for LLM-guided heuristic discovery.
"""
import uuid
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
    try:
        # Update status
        evolution_runs[run_id]["status"] = "running"
        evolution_runs[run_id]["current_generation"] = 0
        
        mode = config["mode"]
        
        # Create evolution config
        evo_config = EvolutionConfig(
            num_generations=config["num_generations"],
            candidates_per_generation=config["candidates_per_generation"],
            retained_candidates=config["elites_kept"],
            training_instance_count=config["num_instances"],
            test_instance_count=max(2, config["num_instances"] // 2),
            num_stops=config["num_stops"],
            seed=config["seed"] or 42,
            llm_mode=mode,
        )
        
        # Create LLM client based on mode
        if mode == "live":
            # Load configuration from environment variables
            from engine.llm import load_config_from_env
            try:
                llm_config = load_config_from_env()
            except ValueError as e:
                evolution_runs[run_id]["status"] = "failed"
                evolution_runs[run_id]["error"] = f"Live mode configuration error: {e}. Please check your .env file."
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
                temperature=0.7,
            )
        else:
            evolution_runs[run_id]["status"] = "failed"
            evolution_runs[run_id]["error"] = f"Unknown mode: {mode}"
            return
        
        client = create_client(llm_config)
        
        # Create and run evolution loop
        evolution = EvolutionLoop(config=evo_config, llm_client=client)
        
        # Run evolution and track progress
        run_result = evolution.run_evolution()
        
        # Convert engine results to API format
        for gen_idx, gen_record in enumerate(run_result.generations):
            generation_result = {
                "generation": gen_record.generation_number,
                "candidates": [
                    {
                        "heuristic_id": cand.candidate_id,
                        "generation": gen_record.generation_number,
                        "parent_id": None,  # TODO: Track parent IDs
                        "code": cand.source_code,
                        "rationale": "",  # MockLLM doesn't provide rationale
                        "is_valid": cand.is_valid,
                        "rejection_reason": cand.error_message if not cand.is_valid else None,
                        "fitness": cand.fitness_score,
                    }
                    for cand in gen_record.candidates
                ],
                "best_fitness": gen_record.best_fitness,
                "valid_count": gen_record.num_valid,
                "invalid_count": gen_record.num_invalid,
            }
            
            evolution_runs[run_id]["generations"].append(generation_result)
            evolution_runs[run_id]["current_generation"] = gen_idx + 1
        
        # Mark as completed
        evolution_runs[run_id]["status"] = "completed"
        evolution_runs[run_id]["best_heuristic_id"] = run_result.best_candidate_id
        evolution_runs[run_id]["best_code"] = run_result.best_candidate_code
        evolution_runs[run_id]["best_fitness"] = run_result.best_training_fitness
        
    except Exception as e:
        evolution_runs[run_id]["status"] = "failed"
        evolution_runs[run_id]["error"] = str(e)
        import traceback
        evolution_runs[run_id]["traceback"] = traceback.format_exc()


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
    run_id = str(uuid.uuid4())[:8]
    
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
        from dotenv import load_dotenv
        load_dotenv()
        
        # Check for required environment variables
        if not os.getenv("LLM_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="Live mode requires LLM_API_KEY in .env file. Copy .env.example to .env and add your API key."
            )
        
        if not os.getenv("LLM_BASE_URL"):
            raise HTTPException(
                status_code=400,
                detail="Live mode requires LLM_BASE_URL in .env file. See .env.example for configuration."
            )
        
        if not os.getenv("LLM_MODEL"):
            raise HTTPException(
                status_code=400,
                detail="Live mode requires LLM_MODEL in .env file. See .env.example for configuration."
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
        error=run_data["error"]
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
        validation_fitness=best_heuristic["fitness"],
        test_results=None  # TODO: Add test set evaluation
    )
