# Phase 9 ? One-Click Intelligence

Completed 2026-11-24, preserving Quiet Atlas and existing engine semantics.

## Delivered behavior

Compare has one primary action, **Run route comparison**. It runs historical NN, NN+2-Opt and the existing constructor portfolio sequentially against the selected instance. Portfolio uses the existing application defaults: 100,000 operations, 10 seconds, search seed zero. The orchestrator validates problem/matrix identity, complete route coverage and method identity, retains individual errors, prevents duplicate submissions, and survives tab navigation. It does not increase budgets or change solver behavior.

The recommendation prefers the shortest validated **completed** preset result. If no completed result exists, a valid incomplete incumbent can be shown with an explicit incomplete label. Shorter incomplete alternatives remain visible. No valid result produces an actionable retry state, never a fabricated recommendation. Per-driver distances and stop counts are available, and the route-inspection action uses the real current-plan map. Experimental methods, fingerprints, runtime/work and termination details are collapsed under Advanced / Experimental.

Evolution Lab offers **Quick strategy experiment** (random, offline, non-LLM) and **AI-guided strategy experiment** (local Ollama). A selected default experiment starts in one action. Existing defaults, development cases and resource limits remain unchanged. Advanced controls preserve hand-authored and fixture workflows. Seeds, generation controls and provider parameters are collapsed. Results show eligible fitness, actual source, evaluation counts, generation progression and training change; application still independently recomputes the selected plan. Candidate records, lineage, tokens, rejections and raw exports remain available in research details.

AI requests perform a bounded model-inventory preflight before creating a job. The UI reports unknown reachability until checked, and unavailable/missing models block creation with actionable messages. No mocked response is silently substituted. Existing engine fallback behavior is unchanged, but AI-requested runs disclose random configurations and separately label actual LLM, fixture, authored, mutation and crossover sources. No accepted LLM proposals means no AI-evidence claim. A completed generation loop with incomplete/failed evaluations receives an explicit qualified results headline.

## Method audit and selection

Read existing Phase 5B development evidence: portfolio completed 348/360, VND 182/360, VND+ILS 0/360 under that benchmark's different budgets. No historical or held-out experiment was rerun or modified.

Then ran 24 fresh offline application-budget measurements: 20/50/100/200 stops, 3 drivers, uniform distribution, symmetric and directed matrices, development replicate 0; identical case/matrix across all three methods; seed 0, 100,000 operations and 10 seconds each. Every final solution was independently validated. Per-case fingerprints, distances, runtime, charged operations, errors and termination are saved in `runs/phase9/method-audit.json`.

| Method | Completed | Stopped/incomplete | Failed | Observed termination |
|---|---:|---:|---:|---|
| Constructor portfolio | 4 | 4 | 0 | 4 local-search-complete; 4 operation-budget |
| VND | 2 | 6 | 0 | 2 local-search-complete; 6 operation-budget |
| VND+ILS | 0 | 8 | 0 | 6 operation-budget; 1 operator-call-limit; 1 ILS-iteration-limit |

All 24 solutions were feasible. Aggregate measured seconds: portfolio 6.083, VND 10.342, VND+ILS 11.303. No measured stop was a wall-clock deadline. Larger portfolio cases exhausted work during construction; VND adds neighborhood scans and ILS additionally exposes call/iteration limits as incomplete under the unchanged engine contract. Portfolio is the most dependable *existing exposed improved method in this audit*, not universally completing. Completed historical alternatives therefore take recommendation priority. The 8-case panel is an engineering audit, not a statistically representative benchmark or evidence of universal improvement.

## Exact files changed

- `web/src/App.tsx`: persistent comparison orchestration/state and cancellation UI wiring.
- `web/src/services/comparison.ts` (new): scoped preset runner, identity/feasibility checks, cancellation, repeat protection, recommendation policy.
- `web/src/services/api.ts`: backward-compatible provider check request.
- `web/src/services/presentation.ts`: honest experiment-result headline.
- `web/src/components/CompareScreen.tsx`: preset action, progress, completed-first recommendation, compact alternatives and collapsed diagnostics.
- `web/src/components/StrategyLab.tsx`: two experiment choices, preflight, synchronous repeat guard, collapsed research controls, source disclosures and result presentation.
- `web/src/components/ResearchVisuals.tsx`: measured generation-to-generation development change.
- `web/src/watercolor.css`: responsive preset action and experiment choice layout.
- `api/routers/strategies.py`: additive `POST /api/strategy-experiments/provider/check`, using existing loopback-only ProviderConfig validation, bounded inventory response/time and sanitized errors. No generation call in the probe.
- `web/tests/visual-design.cjs`: preset/result/cancellation/identity/status regressions. The earlier incomplete-winner test now uses two incomplete preset alternatives, matching the explicitly requested completed-first policy; it still requires the valid incomplete route and its exact distance/status.
- `web/tests/product-browser.mjs`: one-click concurrency/navigation, unavailable AI, complete default quick-run and mobile text-width checks; Phase 9 artifacts.
- `web/tests/workflow-browser.mjs`: Phase 9 output location; existing assertions retained.
- `scripts/smoke_frontend_redesign.py`: isolated Phase 9 output/checkpoints and an explicit unavailable-provider fixture; all real local solver checks retained.
- `tests/unit/test_phase9.py` (new): exact model availability, network/malformed/oversize inventory, sanitized responses, external-origin rejection and no job mutation.
- `docs/phase9-one-click-intelligence.md` (new): this report.

Pre-edit snapshot and preservation evidence: `runs/phase9/before.json`, `before/`, `preservation.json`. All **76 engine files** and **96 protected research artifacts** are unchanged. No historical baseline, strategy schema, optimizer internal, benchmark dataset, held-out guard, budget policy, cancellation implementation or FleetProblem validation was changed. No environment file or secret was read.

## Commands and actual verification

From `D:\routeIQ\web`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run test:browser
```

- **57 frontend tests passed, 0 failed.**
- **TypeScript and production build passed.** Existing build runs `tsc` then env-disabled Vite. 100 modules; JS 410.95 kB (124.33 kB gzip), CSS 76.88 kB (20.13 kB gzip).
- **18 existing browser checks passed, 0 failed**, zero runtime exceptions.

From `D:\routeIQ`:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_phase9.py tests/unit/test_phase7.py tests/unit/test_strategy_api.py tests/integration/test_api.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_phase9.py -q
python -B scripts/smoke_frontend_redesign.py
```

- **59 backend/integration tests passed** in 223.60 seconds. One existing Starlette/httpx deprecation warning. Includes comparison/result APIs, optimizer jobs, strategy jobs, cancellation and application.
- After the final inventory-parser hardening, the focused Phase 9 tests were rerun: **6 passed** (a subset rerun, not six additional distinct tests).
- **28 real local browser checks passed**, plus **11 independent matrix/coverage route audits**. Includes repeated comparison clicks, navigation while running, unavailable Ollama preventing job creation, complete default quick experiment, cancellation, two-plan strategy application, real Leaflet editing/geometry, error disclosure and responsive checks. External browser requests were blocked; road/model availability responses are explicitly offline fixtures.
- **121 Python source files parsed** via AST. Full backend suite was not rerun; the targeted integration suites above were run.
- Initial verification found a malformed JSX closing tag, a default-method union mismatch, missing failed-row text in collapsed diagnostics, and a mobile radio-card text-width regression. All were corrected; final checks pass. No tests were deleted or disabled.

The method audit was executed using `python -B -` with the Case/solve_hybrid loop documented above. It used no external services and wrote every observed measurement as it completed; no extrapolated measurements are included.

## Screenshots

Real local Chromium captures under `runs/phase9/product-browser/`:

- Compare: `04-comparison.png`, `compare-390.png`, plus tablet/laptop captures.
- Experiment choices: `11-experiment-choices.png`.
- Experiment mobile: `lab-390.png`.
- Actual quick-run result: `12-quick-result.png` (includes evaluation counts and chart).
- Applied routes and fixture road geometry: `03-routes.png`, `09-road-routes-offline-fixtures.png`.

Desktop and mobile screenshots were inspected; the mobile text column was corrected and regression-checked. Browser manifests: `product-browser/results.json`, `legacy-browser/results.json`; independent route measurements: `smoke-measurements.json`.

## Limitations / explicit decisions

- Portfolio can still stop early at larger problem sizes. It stays visible without becoming the default recommendation over a valid completed alternative. No completion rate is promised.
- Cancellation prevents remaining baseline steps and cancels a known optimizer job. An in-flight synchronous baseline request has no backend cancellation API and must finish; its late result is not published after cancellation. The UI states this limitation. Network polling retains existing retry behavior; cancellation failures remain retryable.
- Comparison progress is tab-local, survives in-app navigation, and does not survive a full page reload. Existing backend in-memory lifecycle limits remain.
- Ollama preflight verifies exact installed-model availability, not whether a subsequent generation will succeed. Reachability is unknown until the user starts AI mode. Direct legacy API callers retain existing behavior; the preflight gates the new UI flow.
- No successful live LLM or live OSRM test is claimed. No live provider generation, real OSRM request, held-out evaluation or tuning was performed. Model inventory tests use MockTransport; browser unavailable-state testing uses a declared fixture.
- An experiment loop can finish while bounded development evaluations remain incomplete; the default results headline and counts disclose this. Eligible incomplete development fitness is allowed by the existing engine policy, which was not changed. Training fitness is never substituted for selected-plan route distance.
- Historical 88 missing held-out LLM-arm measurements remain disclosed. There is no claim that new development experiments establish held-out or AI superiority.
