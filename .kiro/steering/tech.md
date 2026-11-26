> Current contract (2026-11-26): the active product is the integrated planning
> workspace and canonical FleetProblem with trusted construction/VND/ILS, declarative
> strategy evolution and bounded native Ollama feedback (`qwen3:1.7b`). Historical
> executable-code guidance below applies only to legacy APIs. Preserve research
> records, independent validation, baseline definitions and split protection.
> README.md and docs/product-quality-pass.md describe the current workflow.

# RouteIQ Technology Stack

## Language & Core
- Python 3.10+ (via `py` command on Windows)
- NumPy for distance matrices and cost calculations
- Pydantic for data validation

## Backend
- FastAPI + Uvicorn for HTTP API
- Background jobs for evolution runs
- Simple polling (no SSE required)

## Frontend
- React + Vite + TypeScript
- Tailwind CSS for styling
- Leaflet for map visualization (react-leaflet)
- Recharts for charts and convergence graphs

## LLM Integration
- httpx for HTTP client
- Native Ollama structured JSON for current strategies; OpenAI-compatible legacy workflow remains isolated
- Explicit bounded provider configuration in current UI/API; never read or log environment secrets during maintenance
- Mock mode and replay cache for testing

## Storage
- JSON files in runs/ directory
- No database required

## Testing
- pytest with async support
- Coverage reporting
- Unit and integration test markers

## Development Tools
- python-dotenv for environment management
- Git for version control
- py launcher for Python execution on Windows

## Commands Reference
```bash
# Python execution
py -m <module>           # Run module
py -m venv venv         # Create virtual environment

# Virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1   # Activate
deactivate                     # Deactivate

# Testing
pytest                   # Run all tests
pytest -m unit          # Run unit tests only
pytest -k test_name     # Run specific test

# Backend
uvicorn api.main:app --reload

# Frontend (when implemented)
cd web ; npm run dev
```

## Two LLMs - Keep Separate
1. **Kiro's Claude**: Writes RouteIQ's code during development. Never accessed by the app.
2. **Runtime LLM**: Configured in .env, generates heuristics when app runs. Never accessed by Kiro.

These must NEVER be mixed. No runtime API key in Kiro chat. No Kiro calls from the app.
