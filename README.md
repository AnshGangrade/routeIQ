# RouteIQ

Delivery-route planning and measured fleet-optimization research. The active product
uses a React/TypeScript planning workspace, FastAPI, an immutable FleetProblem
matrix, trusted constructors/local search, and optional declarative Ollama strategies.
It minimizes total fleet distance with balanced stop counts; it does not model vehicle
capacity, time windows, service times, live traffic, or fleet finish time.

## Run locally

From the repository root (Python 3.10+):

```powershell
python -m pip install -r requirements.txt
python -B -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd web
npm ci
npm run dev
```

Open the local Vite URL (normally http://localhost:5173). The Vite wrapper disables
environment-file loading. The conventional routing workflow needs no LLM credentials.
Do not expose this local capstone service publicly: application instances, route
results and optimization jobs live in memory. Use one backend process/worker. Server
restarts discard those objects; SPA navigation preserves the current draft, but a
full reload does not provide durable draft storage.

## Product workflow

- **Home:** create or return to a route plan.
- **Route Plan:** persistent controls and numbered stops beside a live map; generate,
  optimize, inspect drivers, edit, or cancel. Draft changes hide stale route results.
- **Compare:** independently validated results on the same problem/matrix/units.
  A completed route is the dependable recommendation. Shorter incomplete incumbents
  remain visible alternatives. Savings name the historical Nearest Neighbor baseline.
- **Evolution:** one AI-guided strategy workflow using local Ollama. Two trusted seeds
  precede bounded LLM proposals. Only a fully completed, independently validated
  development panel can produce an applicable strategy. Apply recomputes routes on
  the current plan; an incomplete attempt retains the previous completed route.
  Development mean distance is never the distance of the current road plan.

Synthetic mode uses Cartesian coordinates and Euclidean map units. Real-road mode
uses geographical coordinates, an OSRM distance table (meters), then separate OSRM
route geometry/duration requests. OpenStreetMap supplies map tiles and attribution.
These services require network access. Failed geometry stays missing; no straight
lines are substituted for roads. Address lookup is not configured. Summed driving
minutes are driver effort, not concurrent fleet completion time.

## Optimization and optional Ollama

Historical Nearest Neighbor, NN + 2-Opt and angular round-robin assignment retain
their definitions. Trusted construction, portfolio, VND and bounded ILS operate on
the same canonical matrix. Independent validation checks depot returns, exact stop
coverage, workload and cost. The conventional hybrid remains the default.

For local AI features, install Ollama separately, then:

```powershell
ollama pull qwen3:1.7b
ollama list
ollama serve
```

`pull` downloads model weights; do not run it for offline verification. If Ollama is
already running, a second `serve` is unnecessary. Evolution uses `qwen3:1.7b` by default.
The provider uses native Ollama structured JSON; it does not silently
substitute a model. Inference stays local, but latency and hardware requirements
vary. The model proposes supported configurations/actions, never executable code.

Adaptive search supplies aggregate problem features and bounded measured feedback.
The host owns all routes, work/time limits and validation. Mandatory baselines remain;
optional constructors share a work allocation so feedback can run. Invalid initial
selection fails closed. Failed feedback retains the trusted schedule with explicit
`deterministic fallback` attribution. This is adaptive selection, not model training.
Development-only experience may be imported; held-out outcomes never enter prompts.

## Research and verification

See [completed product workflow](docs/completed-product-workflow.md) for the current
completion policy, verified workflow, live smoke evidence and execution limits.
The earlier [quality-pass report](docs/product-quality-pass.md) preserves its test results,
status v2, protocol, screenshots, live/fixture evidence and limitations.
[Controller methodology](docs/controller-value-evaluation.md) documents the historical
four-arm study, which did not establish an LLM advantage. Historical results and the
88 missing Phase 6B measurements are preserved, not backfilled. Current code changes
require a new frozen protocol; old source-frozen experiments cannot be resumed under
changed code.

The new controller v2 protocol retains four end-to-end arms and adds paired static/
adaptive arms sharing one accepted initial strategy. Reports retain completed-only
and bounded-incumbent comparisons, actual work/runtime, missing/failure counts and
case-level uncertainty. Run or reconstruct using `scripts/run_controller_benchmark.py`;
`audit` reads saved measurements and never reruns missing trials. Held-out execution
remains blocked pending a separately authorized final frozen protocol.

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists
npm --prefix web test
npm --prefix web run test:browser
npm --prefix web run build
python -B scripts/smoke_completed_workflow.py
```

The explicitly deselected foundation test reads an environment template; the offline
checks above avoid environment files. Browser smoke uses real local solver results
and labeled road/provider fixtures, blocking external requests. It is not a live
OSRM availability test. Avoid running research benchmarks concurrently with test or
build workloads when interpreting runtime.

## Active architecture and legacy scope

`web/src/App.tsx` owns instance/draft/job identity; `PlanningWorkspace` synchronizes
list and map. FastAPI routers call `engine/routing` and `engine/strategies`.
`FleetProblem` fingerprints the actual immutable matrix, objective and constraints.
`engine/evaluation` owns reproducible case panels, measurement and paired reports.
`runs/` is mostly Git-ignored: preserve the local files when backing up research.

`engine/evolution`, `engine/heuristics`, `engine/llm`, and `engine/sandbox` retain the
older executable-code heuristic workflow and its APIs/artifacts. It is a legacy
research feature, not the active declarative UI. Restricted builtins are not a secure
sandbox; process/resource restrictions must fail closed where unavailable. Do not
expose it to arbitrary public code or claim production isolation.

The complete previous README, including historical phase notes, is preserved in
[the dated archive](docs/archive/readme-before-quality-20261126.md).
