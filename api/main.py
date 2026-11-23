"""
FastAPI application for RouteIQ.

Exposes the optimization engine via HTTP endpoints.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import instances, routing, evolution, results
from api.routers import strategies
from api.routers import optimization

app = FastAPI(
    title="RouteIQ API",
    description="LLM-guided evolutionary heuristic discovery for delivery route optimization",
    version="1.0.0"
)

# Omit rejected input values and exception context (which may contain secrets).
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import logging


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(error["loc"]),
         "msg": f"Invalid {'.'.join(str(part) for part in error['loc'])} ({error['type']})",
         "type": error["type"]}
        for error in exc.errors()
    ]})


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logging.getLogger(__name__).warning("request_failed", extra={"error_type": type(exc).__name__})
    return JSONResponse(status_code=500, content={"detail": "Internal request failure"})

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite default ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(instances.router, prefix="/api/instances", tags=["instances"])
app.include_router(routing.router, prefix="/api/routing", tags=["routing"])
app.include_router(evolution.router, prefix="/api/evolution", tags=["evolution"])
app.include_router(results.router, prefix="/api/results", tags=["results"])
app.include_router(strategies.router, prefix="/api/strategy-experiments", tags=["strategy-experiments"])
app.include_router(optimization.router, prefix="/api/optimization", tags=["optimization"])


@app.get("/api/health")
async def health_check():
    """Check if the API is running."""
    return {"status": "ok", "message": "RouteIQ API is running"}


@app.get("/api/system/status")
async def system_status():
    """
    Get system configuration status (no secrets exposed).
    
    Returns information about which capabilities are configured,
    but never returns API keys or other sensitive data.
    """
    import os
    
    
    # Check LLM configuration
    llm_configured = False
    llm_provider = None
    llm_model = None
    
    try:
        llm_api_key = os.getenv("LLM_API_KEY")
        llm_base_url = os.getenv("LLM_BASE_URL")
        llm_model = os.getenv("LLM_MODEL")
        llm_provider = os.getenv("LLM_PROVIDER", "openai")
        
        # Check if required fields are present (not empty)
        if llm_api_key and llm_base_url and llm_model:
            llm_configured = True
    except Exception:
        pass
    
    return {
        "backend": {
            "status": "operational",
            "message": "API ready"
        },
        "osrm": {
            "status": "unknown",
            "message": "Status not verified - use road mode to test",
            "url": "https://router.project-osrm.org"
        },
        "mock_mode": {
            "status": "available",
            "message": "Predefined candidates for testing"
        },
        "live_llm": {
            "status": "configured" if llm_configured else "not_configured",
            "message": f"Provider: {llm_provider}, Model: {llm_model}" if llm_configured else "Set process environment variables to enable",
            "provider": llm_provider if llm_configured else None,
            "model": llm_model if llm_configured else None,
            "note": "Use POST /api/system/test-llm to verify connectivity" if llm_configured else None
        }
    }


@app.post("/api/system/test-llm")
def test_llm_connection():
    from api.storage import expensive_request
    with expensive_request():
        return _test_llm_connection()


def _test_llm_connection():
    """
    Test LLM API connectivity with a minimal request.
    
    Makes a real API call to verify configuration.
    Returns connection status without exposing secrets.
    """
    import os
    from engine.llm import LLMClient, LLMConfig, GenerationRequest, LLMProvider
    import httpx
    
    
    # Check configuration
    provider = os.getenv("LLM_PROVIDER", "openai")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    
    if not api_key or not base_url or not model:
        return {
            "status": "error",
            "error": "Missing configuration",
            "details": "LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL must be set in the process environment"
        }
    
    client = None
    
    try:
        # Create client
        config = LLMConfig(
            provider=LLMProvider(provider.lower()),
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0.0,
            timeout=60.0
        )
        
        client = LLMClient(config)
        
        # Make minimal test request
        request = GenerationRequest(
            prompt="Say only the word 'test' and nothing else.",
            generation_id="test_connection",
            metadata={}
        )
        
        response = client.generate(request)
        
        return {
            "status": "success",
            "message": "LLM connection successful",
            "provider": provider,
            "model": model,
            "latency_seconds": response.metadata.get("latency_seconds", 0)
        }
        
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("llm_connection_failed", extra={"error_type": type(exc).__name__})
        return {"status": "error", "error": "LLM connection failed", "details": "Check provider configuration and connectivity."}
    finally:
        # Always clean up client
        if client:
            try:
                client.close()
            except Exception:
                pass  # Ignore cleanup errors
