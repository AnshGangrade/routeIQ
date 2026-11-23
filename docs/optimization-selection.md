# Optimization selection and compact Evolution Lab

## Audit and cause

The reported 24.75 km evolved route losing to 24.21 km 2-Opt can be a genuine result. Previously, evolution selected the best **generated candidate**, then applied its raw scoring route without retaining a baseline incumbent. Training and held-out evaluation use synthetic single-driver examples; a selected plan can instead have a directed road matrix and multiple drivers. Training success does not guarantee improvement on that plan. The original in-memory plan was unavailable for exact reproduction; its reported distances are covered by a frontend regression.

Inspected and preserved:

- `engine/evolution/loop.py`: generation prompts contain retained candidate code; candidates are parsed, validated and evaluated on every training example. Finite mean distance is minimized, and the actual best candidate ID is retained. Elites influence subsequent prompts.
- `engine/evaluation/evaluator.py`, `engine/evaluation/fitness.py`: incomplete evaluations cannot gain fitness or aggregate improvement claims. Held-out evaluation uses the same complete batch for the candidate and both baselines; required failures fail the run explicitly. Research scores remain raw candidate measurements.
- `engine/heuristics/harness.py`: candidates receive fresh matrix copies; the trusted reference determines distance. Sandbox execution remains isolated and fail-closed.
- `engine/baselines/two_opt.py`: directed route cost is already recomputed before accepting moves. This algorithm was preserved.
- `api/routers/routing.py`: winner source comes from the completed run; application uses the selected instance's stored matrix and fleet assignments. Training fitness never enters the plan solve.

Two additional defects were corrected: matching seeds/stop counts did not prove research instances were identical, and a zero-distance baseline produced an invented -100% difference. Evaluations now carry an exact-instance SHA-256 fingerprint, with mismatched/missing provenance rejected during comparison. A positive distance against a zero baseline now has an unavailable percentage; zero against zero remains 0%.

## Selection behavior

New `engine/routing/incumbent.py` measures Nearest Neighbor, 2-Opt and the raw candidate on one FleetRouter, matrix and deterministic assignment. It validates driver coverage and every stop sequence and independently recomputes all costs. Candidate 2-Opt refinement is accepted only when verified total distance strictly decreases. The final route is the shortest valid measured result. Ties retain a baseline; equal baselines deterministically prefer Nearest Neighbor.

Invalid, failed or timed-out candidates preserve the best valid baseline and expose the failure. A failed baseline remains unavailable with an error; if both fail, selection fails closed. No partial fleet result enters selection.

`POST /api/routing/solve` retains method `evolved` for compatibility, but its route and total now represent the **final validated selection**. Optional `optimization` metadata exposes both baselines, the raw candidate, accepted refinement (otherwise null), selected source, baseline-retention flag, measured percentage and sanitized errors. `run_id` identifies winner-derived results. Comparisons carry the same metadata.

Invalid supplied candidate code now returns a successful baseline fallback with the candidate explicitly unavailable; missing code and missing/non-completed runs still return errors. Existing integration assertions now require rejection of the candidate and correct fallback instead of the former blanket HTTP 400 behavior.

Optional `preview: true` measures without replacing cached applied results or requesting road geometry. The lab previews a completed winner on the selected plan and ignores stale responses. Applying recomputes and persists the selection, fetching geometry through the existing path.

The guarantee is non-regression against the **best valid measured baseline on the same plan**, not a guaranteed 0.1% improvement. No metrics are adjusted. Differences below 0.1% are labelled `<0.1%`, not rounded up to claim that target. Failed raw results are unavailable, never zero.

## Frontend

The lab has one experiment card, one progress/results section, one compact plan table, one expandable research/candidate section and one primary final-route action. Advanced controls remain collapsed. Compare now uses a table rather than repeated method cards. Navigation, setup, map, driver details, polling, cancellation and correct units remain intact.

The only user-facing modes are **Live LLM** (`live`) and **Offline Demo** (`mock`); the latter identifies predefined candidates. Replay remains in the internal engine/CLI and backward-compatible API for existing consumers/tests, but is absent from the selector and frontend request type. Both modes were tested with mocked requests; no live provider call was made.

## Verification results

- New selection regressions: **14 passed, 0 failed**.
- Final evolved-routing API checks: **4 passed, 0 failed, 19 deselected**; the valid-candidate check also asserts the exact selected baseline route, not only its distance.
- Broad offline Python suite, including all Phase 1–4 regressions: **441 passed, 2 failed, 1 deliberately deselected**. Both failures were comparison fixtures/legacy records without the new optional metadata. The reader was corrected without changing those tests. The subsequent Phase 4 plus selection rerun passed **46 tests, 0 failed**. The entire broad suite was not repeated after this narrow compatibility fix.
- Frontend unit/service/render suite: **22 passed, 0 failed**.
- Chromium interaction suite: **18 passed, 0 failed**; both mode request values, preview without application, raw loss/fallback, cancellation, different-plan application, navigation, road errors and mobile layout covered. No runtime exceptions. External requests blocked (60 tile requests); the synthetic journey requested none.
- Actual local Uvicorn/Vite/engine smoke: **11 passed, 0 failed**, including preview, recomputation, non-regression and invalid-candidate fallback.
- Python AST: **90 files passed, 0 failed**. TypeScript passed. Production build passed, **89 modules transformed**.
- Screenshots reviewed for the compact lab and mobile comparison. Browser screenshots use explicitly mocked fixtures; engine behavior is separately covered by Python and real local smoke tests.

The initial new Python fixture used the generator's seed argument incorrectly (11 failures); corrected fixture reruns pass. Initial Node process launches hit EPERM; scoped execution permission allowed offline tests/browser/build. Existing Starlette/httpx deprecation remains. Scoped final diff review found existing trailing whitespace in the previously modified routing module; unrelated formatting was preserved. No test was deleted or relaxed to accept invalid application behavior.

## Exact commands

From `D:\routeIQ`:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_incumbent.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/integration/test_api.py -k routing_evolved -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_phase4.py tests/unit/test_incumbent.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/optimization-offline.xml -q
node web/tests/workflow-browser.mjs
python -B scripts/smoke_phase3.py
```

The broad suite includes the 144 Phase 1 tests plus Phase 2, 3 and 4. Live/manual modules are excluded; the foundation test which opens an environment example file is deliberately deselected. The offline guard blocks dotenv loaders and real HTTP transports.

From `D:\routeIQ\web`:

```powershell
npm.cmd test
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
node --input-type=module -e "import { build } from 'vite'; import react from '@vitejs/plugin-react'; await build({configFile:false,envFile:false,plugins:[react()]});"
```

AST parsing from the repository root:

```powershell
@'
import ast
from pathlib import Path
excluded={'.git','venv','.venv','env','ENV','node_modules','__pycache__','dist','build'}
files=sorted(p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts))
for path in files: ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
print(f'AST: {len(files)} passed, 0 failed')
'@ | python -B -
```

## Files changed in this task

- API: `api/models.py`, `api/routers/routing.py`, `api/routers/results.py`.
- Engine: new `engine/routing/incumbent.py`, `engine/evaluation/evaluator.py`, `engine/evaluation/models.py`.
- Python tests: new `tests/unit/test_incumbent.py`, `tests/unit/test_evaluation.py`, `tests/integration/test_api.py`.
- Frontend: `web/src/App.tsx`, `web/src/types/api.ts`, `web/src/services/api.ts`, `web/src/services/workflow.ts`, `web/src/index.css`.
- Components: new `web/src/components/PlanSelection.tsx`, plus `EvolutionLab.tsx`, `EvolutionPanel.tsx`, `EvaluationSummary.tsx`, `CompareScreen.tsx`, `RouteVisualization.tsx` under `web/src/components/`.
- Frontend tests: `web/tests/phase3.cjs`, `web/tests/workflow.cjs`, `web/tests/workflow-browser.mjs`, `web/tests/smoke-phase3.mjs`.
- This report: `docs/optimization-selection.md`.

All earlier unrelated modifications were preserved. No environment files or secrets were accessed, and no live LLM or external OSRM requests were made.

## Remaining limitations

- Live providers, real OSRM availability and real road tiles were not exercised. Directed selection is covered by offline matrices; road failures and geometry warnings remain tested.
- Preview and application intentionally recompute; selection adds baseline/refinement work. Existing request limits and sandbox deadlines remain. No new runtime or globally optimal-route guarantee is claimed.
- Research remains synthetic and single-driver. Plan refinement gains are labelled separately; raw held-out losses remain visible.
- Process-local storage, restart persistence limits and cooperative cancellation boundaries remain unchanged.
