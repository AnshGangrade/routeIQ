# RouteIQ: LLM-Guided Evolutionary Heuristic Discovery for Delivery Route Optimization

**Capstone Project - Level 2**

## Project Overview

RouteIQ explores whether Large Language Models can automatically discover effective routing heuristics through evolutionary optimization. The system:

1. Uses an LLM to propose candidate routing heuristics as executable Python functions
2. Evaluates each heuristic on synthetic delivery instances
3. Selects the best performers and provides structured feedback
4. Iterates through multiple generations to evolve improved heuristics
5. Compares the evolved heuristic against classical baselines (Nearest Neighbor, 2-Opt)

## Key Features

- **Classical Baselines**: Nearest Neighbor construction + 2-Opt local search
- **LLM-Driven Evolution**: Automated heuristic discovery via iterative refinement
- **Multi-Driver Routing**: Deterministic stop assignment with per-driver optimization
- **Safety-First Sandbox**: Multi-layer validation and isolated execution of generated code
- **Mock/Replay Mode**: Development and demos without requiring live LLM API calls
- **Interactive Dashboard**: Map visualization, metrics, and algorithm comparison
- **Reproducible Experiments**: Seeded instances, logged runs, and scientific evaluation protocol

## Architecture

```
Browser (React + Leaflet + Recharts)
    ↓ HTTP/JSON
FastAPI Backend
    ↓
Python Optimization Engine
    ├── Instance Generator
    ├── Baseline Solvers
    ├── Heuristic Harness
    ├── Code Validator & Sandbox
    ├── Evaluator & Fitness
    ├── Evolution Loop
    └── Multi-Driver Router
    ↓
Runtime LLM API (configurable: OpenAI/Groq/Local)
```

## Tech Stack

- **Backend**: Python 3.10+, NumPy, Pydantic, FastAPI
- **Frontend**: React, Vite, TypeScript, Tailwind CSS
- **Visualization**: Leaflet (maps), Recharts (charts), Matplotlib (report figures)
- **Testing**: pytest
- **Version Control**: Git

## Repository Structure

```
routeiq/
├── engine/              # Core optimization logic
│   ├── instances/       # Synthetic instance generator
│   ├── baselines/       # NN and 2-Opt solvers
│   ├── heuristics/      # Heuristic harness
│   ├── llm/             # LLM client and prompt management
│   ├── sandbox/         # Code validation and safe execution
│   ├── evaluation/      # Fitness scoring and metrics
│   ├── evolution/       # Main evolutionary loop
│   ├── routing/         # Multi-driver routing layer
│   └── metrics/         # Comparison and reporting
├── api/                 # FastAPI backend
├── web/                 # React dashboard
├── tests/               # pytest suite
├── runs/                # Saved experiment logs (gitignored)
├── docs/                # Report figures and documentation
├── scripts/             # Benchmark runners and utilities
└── .kiro/               # Kiro steering files and specs
```

## Development Workflow

### Phase 1: Core Engine (Steps 0-7)
Build the optimization engine as a standalone CLI tool:
- Instance generation and cost calculation
- Baseline solvers
- Heuristic harness and scoring contract
- LLM client with mock/replay mode
- Code validation and sandboxed execution
- Evolution loop with feedback generation

### Phase 2: Multi-Driver + API (Steps 8-9)
- Multi-driver routing with deterministic stop assignment
- FastAPI backend exposing engine over HTTP
- Progress polling for long-running evolution jobs

### Phase 3: Dashboard (Step 10)
- Interactive map showing depot, stops, and routes
- Metrics table comparing algorithms
- Convergence charts showing evolution progress

### Phase 4: Experiments (Step 11-12)
- Benchmark protocol with train/validation/test splits
- Repeated evolution runs
- Statistical analysis and Matplotlib figures
- Polish and documentation

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- Node.js 18+ (for frontend)
- Git

### Installation

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository-url>
   cd routeiq
   ```

2. **Create a Python virtual environment**:
   ```bash
   py -m venv venv
   ```

3. **Activate the virtual environment**:
   - Windows PowerShell: `.\venv\Scripts\Activate.ps1`
   - Windows CMD: `.\venv\Scripts\activate.bat`
   - Linux/Mac: `source venv/bin/activate`

4. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure environment variables**:
   ```bash
   # Windows PowerShell:
   Copy-Item .env.example .env
   
   # Or use any text editor to copy .env.example to .env
   # Then edit .env and add your LLM API key
   ```

6. **Install frontend dependencies** (when frontend is implemented):
   ```bash
   cd web
   npm install
   cd ..
   ```

### Running Tests

```bash
pytest
```

### Running the Engine (CLI mode)

```bash
# Generate a synthetic instance
py -m engine.instances.generator --seed 42 --stops 20

# Run baseline solvers
py -m engine.baselines.solve --instance instances/test_42.json

# Run evolution (mock mode for development)
py -m engine.evolution.run --mode mock --generations 5
```

### Running the Full Stack (when implemented)

```bash
# Terminal 1: Start backend
uvicorn api.main:app --reload

# Terminal 2: Start frontend
cd web
npm run dev
```

## Team Responsibilities

As documented in the mid-term presentation:

- **Member 1**: Data generation, instance management, baseline solvers
- **Member 2**: LLM integration, prompt engineering, code validation
- **Member 3**: Evaluation, fitness scoring, evolution loop
- **Member 4**: Visualization, dashboard, metrics reporting

## Important Notes

### Two Different LLMs

- **Kiro's Claude**: Used during development to write RouteIQ's code
- **Runtime LLM**: Used by the running application to generate routing heuristics

These are completely separate. The runtime LLM is configured in `.env` and never accesses Kiro.

### Safety & Sandboxing

Generated heuristics are untrusted code. The system uses multiple safety layers:
1. Static AST-based validation
2. Restricted namespace (limited built-ins)
3. Process isolation with timeouts
4. Smoke tests before actual evaluation

This provides defense-in-depth appropriate for an academic demo. Not suitable for production use without additional hardening.

### Reproducibility

All experiments use:
- Fixed random seeds for instance generation
- Deterministic tie-breaking in algorithms
- Saved LLM responses (replay mode)
- Logged configuration and results

## License & Attribution

Academic capstone project. All source code and documentation developed by the RouteIQ team.

## Current Status

**Milestone 0**: Project foundation established ✅  
**Milestone 1**: Instance generation and distance calculations ✅  
**Milestone 2**: Baseline routing algorithms ✅  
**Milestone 3**: Heuristic scoring harness ✅  
**Milestone 4**: Candidate validation and controlled execution ✅  
**Milestone 5**: Runtime LLM client and mock/replay mode ✅

### Completed Features
- Synthetic delivery instance generator with reproducible seeds
- Euclidean distance calculations with validation
- Distance matrix computation  
- Route cost calculation and validation
- **Nearest Neighbor construction heuristic** (deterministic tie-breaking)
- **2-Opt local search improvement** (never increases distance)
- **Combined NN + 2-Opt baseline** (construction + improvement)
- **Heuristic scoring contract** (HeuristicContext → HeuristicResult)
- **RouteHarness** for trusted route construction
- **Built-in nearest_distance_heuristic** (reproduces NN exactly)
- **Static AST validation** (allowlist-based Python subset)
- **Controlled execution** with restricted namespace and timeout
- **Candidate adapter** for integrating validated code with harness
- **Runtime LLM client** (httpx, OpenAI-compatible API format)
- **Prompt builder** with iteration feedback and problem context
- **Response parser** (extract code, validate function signature)
- **Mock mode** (8 predefined candidates for testing)
- **Replay mode** (load from saved fixture files)
- **Client factory** (auto-select based on provider config)
- Comprehensive test suite (212 tests, 85% coverage)

### Quick Examples

**Instance Generation:**
```python
from engine.instances import InstanceGenerator, compute_distance_matrix

# Generate instance
gen = InstanceGenerator(seed=42)
instance = gen.generate(n_stops=10)

# Compute distances
locations = instance.get_all_locations()
dist_matrix = compute_distance_matrix(locations)
```

**Baseline Routing:**
```python
from engine.baselines import nearest_neighbor, two_opt, nearest_neighbor_with_2opt

# Run Nearest Neighbor
nn_result = nearest_neighbor(dist_matrix)
print(f"NN distance: {nn_result.total_distance:.2f}")

# Improve with 2-Opt
improved = two_opt(nn_result.route, dist_matrix, max_iterations=100)
print(f"Improved distance: {improved.total_distance:.2f}")

# Or run combined algorithm
combined = nearest_neighbor_with_2opt(dist_matrix, max_2opt_iterations=100)
print(f"Combined distance: {combined.total_distance:.2f}")
```

**Heuristic Harness:**
```python
from engine.heuristics import (
    RouteHarness, HeuristicContext, HeuristicResult,
    nearest_distance_heuristic
)

# Define a custom heuristic
def my_heuristic(ctx: HeuristicContext) -> HeuristicResult:
    """Score candidates by distance from current location."""
    scores = {
        stop: ctx.distance_matrix[ctx.current_location, stop]
        for stop in ctx.candidate_stops
    }
    return HeuristicResult(scores=scores)

# Build route using harness
harness = RouteHarness()
result = harness.build_route(
    heuristic=my_heuristic,
    distance_matrix=dist_matrix,
    n_stops=10,
    algorithm_name="My Heuristic"
)
print(f"Route: {result.route}")
print(f"Distance: {result.total_distance:.2f}")
```

**Candidate Validation & Execution:**
```python
from engine.sandbox import (
    CandidateHeuristic, HeuristicValidator,
    create_scoring_function
)

# Define candidate as string
code = '''
def score_candidates(context):
    scores = {}
    for stop in context.candidate_stops:
        scores[stop] = context.distance_matrix[context.current_location, stop]
    return {"scores": scores}
'''

# Validate candidate
candidate = CandidateHeuristic(source_code=code)
validator = HeuristicValidator()
validation = validator.validate(candidate)

if validation.is_valid:
    # Create scoring function and use with harness
    scorer = create_scoring_function(code, timeout=5.0)
    result = harness.build_route(scorer, dist_matrix, n_stops=10)
    print(f"Route: {result.route}")
else:
    print(f"Validation failed: {validation.errors}")
```

**LLM Heuristic Generation:**
```python
from engine.llm import (
    LLMConfig, LLMProvider, create_client,
    GenerationRequest, build_generation_prompt,
    parse_llm_response
)

# Configure mock mode (no API calls)
config = LLMConfig(
    provider=LLMProvider.MOCK,
    base_url="mock://local",
    model="mock-v1"
)

# Generate heuristic
with create_client(config) as client:
    prompt = build_generation_prompt(iteration=0)
    request = GenerationRequest(
        prompt=prompt,
        metadata={"candidate_key": "nearest_distance"}
    )
    response = client.generate(request)

# Parse response
result = parse_llm_response(response)
if result.success:
    print(f"Generated function: {result.function_name}")
    print(f"Source: {result.source_code[:100]}...")
```

**Full Examples:**
```bash
# Baseline algorithms
$env:PYTHONPATH="D:\routeIQ" ; py examples/baseline_routing.py

# Heuristic harness
$env:PYTHONPATH="D:\routeIQ" ; py examples/heuristic_harness.py

# Candidate validation
$env:PYTHONPATH="D:\routeIQ" ; py examples/candidate_validation.py

# LLM generation (mock/replay modes)
$env:PYTHONPATH="D:\routeIQ" ; py examples/llm_generation.py
```

**Next Milestone**: Evaluator and fitness scoring

---

For detailed implementation plans, see `ROUTEIQ_PLAN.md`.
