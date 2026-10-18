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
- OpenAI-compatible API format
- Configurable provider/model/base_url via .env
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
