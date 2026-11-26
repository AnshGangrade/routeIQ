> Current contract (2026-11-26): the active product is the integrated planning
> workspace and canonical FleetProblem with trusted construction/VND/ILS, declarative
> strategy evolution and bounded native Ollama feedback (`qwen3:1.7b`). Historical
> executable-code guidance below applies only to legacy APIs. Preserve research
> records, independent validation, baseline definitions and split protection.
> README.md and docs/product-quality-pass.md describe the current workflow.

# RouteIQ Product Requirements

## Core Mission
LLM-guided evolutionary heuristic discovery for delivery route optimization. Research capstone demonstrating whether LLMs can automatically discover effective routing heuristics through iterative refinement.

## Required Features
- Classical baselines: Nearest Neighbor construction + 2-Opt local search
- Synthetic instance generator with configurable stops and drivers
- LLM-generated heuristic scoring functions (NOT full route builders)
- Evolutionary loop: generate → validate → evaluate → select → feedback
- Fleet routing with common matrix, objective and workload constraints; trusted operators may change assignment. Historical baseline assignment remains unchanged.
- Fair comparison: identical test instances and consistent assignments
- Interactive dashboard: map, routes, orders, metrics, algorithm comparison
- Mock/replay mode for development and demos without live LLM calls

## Out of Scope (Do NOT Build)
- Live traffic data or GPS tracking
- Real customer data or production logistics
- User authentication or accounts
- Mobile app
- Model training or fine-tuning
- Paid geocoding and live traffic (OSRM road distance/geometry is supported)
- Capacity constraints (optional only)
- Time windows (optional only)

## Success Criteria
Report genuine measured results. Do NOT promise fixed percentage improvements. The evolved heuristic may be better, worse, or comparable to baselines - all outcomes are valid research results.

## Team Responsibilities (Preserve These)
- Member 1: Data generation, instance management, baseline solvers
- Member 2: LLM integration, prompt engineering, code validation
- Member 3: Evaluation, fitness scoring, evolution loop
- Member 4: Visualization, dashboard, metrics reporting
