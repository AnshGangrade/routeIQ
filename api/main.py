"""
FastAPI application for RouteIQ.

Exposes the optimization engine via HTTP endpoints.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import instances, routing, evolution, results

app = FastAPI(
    title="RouteIQ API",
    description="LLM-guided evolutionary heuristic discovery for delivery route optimization",
    version="1.0.0"
)

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


@app.get("/api/health")
async def health_check():
    """Check if the API is running."""
    return {"status": "ok", "message": "RouteIQ API is running"}
