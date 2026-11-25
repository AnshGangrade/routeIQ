# Adaptive strategy controller

This is opt-in adaptive strategy selection using feedback, not model training.
The existing population experiment remains a fixed-configuration development
comparator. Existing historical baselines, assignment, operators, immutable
FleetProblem, independent validation and frozen held-out guards remain in place.

## Integration

`solve_hybrid(..., controller=...)` extends the existing solver. Without a
controller it executes the previous constructor/VND/ILS schedule. With a
controller it builds the same mandatory legacy comparators plus the chosen
constructor, starts from the shortest validated constructor, and schedules the
existing VND and seeded stop-swap perturbation at bounded work checkpoints.
It does not run another optimizer or evaluate generated code.

`engine/routing/control.py` defines the controller contract and shared-budget
work slices. `engine/strategies/adaptive_models.py` validates initial selections
with the existing `fleet-strategy/v1` schema and a separate finite action schema.
`adaptive.py` handles source attribution, budgets, evidence and replay;
`experience.py` handles aggregate features and selected development evidence.
`provider.py` adds total-deadline asynchronous Ollama requests inside the existing
synchronous worker interface. No environment file or proxy configuration is read.

Initial context includes fingerprints, actual matrix mean/spread/directionality,
nearest-stop distance ratios, driver/workload bounds, available/unsupported
constraints and coordinate spread/4x4 occupancy proxies. Geographic spread uses
an approximate kilometer projection; dateline-crossing box density is unavailable.
No raw coordinates, customer data, full matrix or route arrays enter prompts.
Features describe geometry; objective costs always use the canonical matrix.

Initial output selects construction, ordered operator priorities, implemented
parameters, a first work-slice allocation (100–20,000 operations) and rationale.
An unavailable/invalid initial response fails closed without publishing AI routes.
Contiguous sweep is rejected for non-Euclidean/directed/geographically indexed
problems. Unsupported algorithms, weights, policies and source code are rejected.

Checkpoint actions:

| Action | Executed meaning |
|---|---|
| continue | Retain the current trusted operator order |
| reorder | Choose a unique ordered subset of the six existing operators |
| diversify | Existing seeded stop swap, only after observed stagnation and within initial ILS/diversification caps |
| stop | End with the independently validated incumbent; explicitly incomplete |

All actions can select the next bounded work slice and scan cap. They cannot
change the matrix, objective, constraints, random seed or global operation/time
limits. The optimizer separately records whether a validated recommendation was
actually applied (for example, diversification can be denied).

Telemetry includes global best distance, change since the previous checkpoint,
stagnation, elapsed/remaining time, consumed/remaining work, and per-operator
calls, candidate attempts, accepted improvements, rejections and failures.
Improvement per operation credits only new global bests, not recovering a
diversification loss. For best-scan operators, rejected means scanned candidates
not retained. Two-Opt's optional observation callback counts actual reversal
decisions without changing historical traversal or acceptance. Work units remain
the existing host candidate/call counters, not CPU FLOPs.

## Limits and failure behavior

Default: exact model `qwen3:1.7b`, temperature 0.3, host search seed (including zero),
4 reserved request attempts, 4 checkpoints, 5 seconds/request, 15 total model
seconds, zero retries, 768 output tokens/request, 8,192 context tokens/request,
40,000 reserved context/output tokens, and a 24,000-byte prompt limit. Every
attempt reserves context + output allowance, including failed requests. Actual
request counts and reported token usage are separate; missing usage stays unknown.
The Ollama request sets `num_ctx`, `num_predict`, seed, temperature and JSON schema.
These bound requested inference, not independently metered server hardware work.

Provider time consumes the same solver deadline. Cancellation interrupts a slow
HTTP response with a 50 ms polling interval and closes the response/client.
Disconnect does not guarantee Ollama stops inference server-side. Numerical
scans, summarization, source hashing and independent validation are cooperative,
not a hard real-time or security-isolation guarantee.

After successful initialization, invalid/unavailable checkpoint responses keep
the current trusted schedule and record **deterministic fallback**, never random
search. Model proposals, offline fixtures and replay are explicitly distinguished.
The existing population experiment's independently labeled random proposals remain
separate. Both live experiment admission and adaptive admission now reject an
unavailable exact Ollama model on the server, not only in the UI.

No new global optimum, permanent learning or LLM-over-random advantage is claimed.
Live model output can vary. Fixed recorded decisions, problem, seed, work budget
and source reproduce the solver trajectory when deadlines do not intervene.
`ReplayController(result.controller)` verifies source/problem/decision fingerprints,
seed, budget and checkpoint work/distance before replaying. Record elapsed time
separately. Interrupted/cancelled/deadline or failed traces remain evidence and
cannot be executed as successful replays; final route fingerprints and work are
also checked. The initial strategy fingerprint is not the complete adaptive policy;
the separate decision fingerprint identifies its recorded decision trace.

## Development experience

The existing experiment registry/checkpoints are the experience store; there is
no new database or scan of research output directories. Supply at most three
explicit terminal development job IDs. The importer checks registered case split,
regenerates the canonical development problems, verifies fingerprints, validates
available routes and recomputes their distances. Validation/held-out case IDs are
rejected before their measurement rows are read. Failed measurements remain failed
with null distance. Free-form historical rationales never enter prompts.

Selection is bounded to the first 16 records per selected job, panels of at most
12 cases, and the four closest records by directionality, stop count and driver
count. This is a small historical context sample, not an unbiased matched study.
Original configurations, source, budgets, completion states and measured costs
are retained. Older records lack per-operator efficiency/stagnation: these remain
null. New fixed-strategy development evaluations persist the trusted operator
counters, validated for internal count/work consistency when imported. Historical
stagnation remains unknown; it is not inferred from missing event data.
Current application plans are not silently promoted into development evidence.

## API and product use

Use Route Plan → Advanced routing and diagnostics → Adaptive LLM search on this
plan. Set the installed model and optional development job IDs. Existing global
search limits still apply. Polling, cancellation, matrix identity, stale-draft
blocking, route publication and comparison use the existing job lifecycle.
The UI shows the rationale, source, actual checkpoint metrics and rejected/denied
decisions. A rationale is model-supplied, not an independently verified causal
explanation. Actual route results are recomputed on the selected matrix.

Existing `POST /api/optimization/jobs` accepts this additional method:

```json
{
  "instance_id": "an-existing-plan-id",
  "method": "adaptive",
  "operations": 100000,
  "seconds": 30,
  "search_seed": 0,
  "adaptive": {}
}
```

`adaptive` optionally contains `provider`, `limits`, `experience_job_ids`.
Unknown/unsupported fields are rejected. Status and final execution contain the
controller trace. Export/save that JSON for reproducibility; application job
storage remains in memory and single-worker only. Restart loses these application
jobs; existing development disk checkpoints remain independently managed.

## Offline verification

No live model or OSRM experiment is part of this phase. MockTransport verifies
native provider requests/stream cleanup; scripted fixtures verify scheduling and
actual routing, and are labeled as fixtures. Local browser smoke uses actual API
and solver with explicitly injected road/provider fixtures and blocks external HTTP.

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_adaptive_controller.py tests/unit/test_hybrid_search.py tests/unit/test_strategy_evolution.py tests/unit/test_strategy_api.py tests/unit/test_phase7.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/adaptive-controller-offline.xml -q
python -B scripts/smoke_frontend_redesign.py
```

The existing environment-example-reading test is deselected solely to honor the
no-environment-file constraint. Live/manual tests are outside the offline suite.
From `web`: `npm.cmd test`, `npm.cmd run test:browser`, `npm.cmd run build`.
From root: `web/node_modules/.bin/tsc.cmd --noEmit --incremental false -p web/tsconfig.json`.

Verified on 2026-11-24:

| Check | Actual result |
|---|---|
| Focused pytest command above | 181 passed, 0 failed |
| Full offline pytest command above | 960 passed, 1 explicitly deselected, 0 failed; 339.80 s |
| `npm.cmd test` | 68 passed, 0 failed |
| `npm.cmd run test:browser` | 19 passed, 0 failed |
| Local API/frontend smoke command above, retry | 37 browser checks and 13 independent matrix/coverage audits passed |
| Python AST command below | 332 files passed |
| TypeScript command above | Exit 0 |
| `npm.cmd run build` | Exit 0 |
| `git diff --check` | Exit 0; Git line-ending notices only |

The focused tests initially exposed four deterministic-equality failures from
per-operator elapsed time in the new trace. Production instrumentation was fixed
to retain deterministic work counters and keep wall time separate; existing
assertions were not weakened. Both final Python runs reported one existing
Starlette/httpx deprecation warning.

The first local browser smoke passed 14 checks, then an existing development
experiment returned `failed / experiment_failure / PermissionError` while
persisting its run. The unchanged smoke passed on retry. The saved error type
does not establish whether locking, antivirus or another permission cause was
responsible. This intermittent Windows persistence issue remains unresolved;
the successful retry is not a durability fix. Failure evidence is preserved in
`runs/adaptive-controller-ui/smoke-first-attempt.json`, its referenced experiment
checkpoint, and `product-browser/first-attempt-failure.png`. Successful evidence
is in `product-browser/results.json`, `smoke-measurements.json`, and the
`13-adaptive-offline-evidence.png` screenshot under the same artifact directory.
Full offline results are in `runs/adaptive-controller-offline.xml`.

No live model-quality experiment was run. The verification establishes routing,
budgeting, cancellation, replay and UI behavior with explicit offline fixtures;
it does not establish an LLM advantage over random or hand-authored strategies.

## Phase 3 change inventory

New implementation: `engine/routing/control.py`,
`engine/strategies/adaptive_models.py`, `engine/strategies/adaptive.py`,
`engine/strategies/experience.py`.

Existing implementation extended: `engine/routing/search.py`,
`engine/routing/trusted.py`, `engine/routing/operators/moves.py`,
`engine/baselines/two_opt.py` (observation callback only),
`engine/strategies/provider.py`, `engine/strategies/evaluation.py`,
`api/routers/optimization.py`, `api/routers/results.py`,
`api/routers/strategies.py`.

Product integration: `web/src/App.tsx`, `web/src/types/api.ts`,
`web/src/services/workflow.ts`, `web/src/components/OptimizationControls.tsx`,
`web/src/components/OptimizationDetails.tsx`,
`web/src/components/CompareScreen.tsx`, `web/src/components/StrategyLab.tsx`.

Verification: `tests/unit/test_adaptive_controller.py`,
`web/tests/visual-design.cjs`, `web/tests/product-browser.mjs`,
`scripts/smoke_frontend_redesign.py`, and this document. Existing Phase 1/2
workspace and visual changes remain in the working tree; they were not reverted.

AST verification from repository root:

```powershell
@'
import ast
from pathlib import Path
excluded={'.git','venv','.venv','env','ENV','node_modules','__pycache__','dist','build'}
files=sorted(p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts))
for path in files:
    ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
print(f'AST: {len(files)} passed, 0 failed')
'@ | python -B -
```
