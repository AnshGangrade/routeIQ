# Guided frontend redesign

## Journey and capability mapping

The previous application put generation, baseline solving, evolution setup, the map, driver metrics, and research progress in one workspace. App owned instance/results/evolution state, but map selection and driver-detail selection were independent. Some unused legacy components also mixed training fitness with held-out labels. The redesign routes users through one primary task at a time.

| View | User task | Preserved capabilities |
| --- | --- | --- |
| Home | Understand the app and begin | One-sentence explanation, create plan, return to selected plan |
| Setup wizard | Choose mode → locations → drivers → review | Synthetic layout and seed; road depot, map placement/dragging, current location, manual coordinates, simulated nearby stops; stop/driver validation; editable review |
| Routes | Explore the generated fleet | Synthetic coordinate map and road Leaflet map; method selection; shared driver selection; stop sequence, driving duration when reported, total/individual distances, road geometry warnings, retry/recalculate |
| Compare | Choose using actual measured routes | Nearest Neighbor, 2-Opt, evolved result; same instance and fleet; shorter/longer/equal wording; longest route and calculation time; unavailable results remain unavailable |
| Evolution Lab | Explore optional heuristic discovery | Mock, replay, live modes; collapsed advanced settings; training counts, generations, candidates, retained strategies, seed, model/temperature; progress, polling errors, cancellation, terminal states, all candidate details/code, authoritative winner, training and held-out results, winner application |

Synthetic depots/stops remain backend-generated because the existing synthetic request contract does not accept manually placed coordinates. The wizard explains this instead of pretending custom synthetic locations can be submitted. Real-road mode retains the existing location controls.

## State and API dependencies

- App owns the plan draft, wizard step, selected instance, results by method, selected driver/method, evolution configuration/run, applied winner identity, and pending/error states. Moving between steps/views does not reset these. Hash navigation supports browser Back/Forward. Refresh persistence was not added; the UI says to keep the tab open.
- `SetupWizard` edits the draft. `services/workflow.ts` validates it and creates the existing instance request. `generatePlan` calls `api.createInstance` once, then both baseline solves for that returned ID. Each solve is checked independently, and partial failure preserves successful results and exposes retries.
- `Routes` and `CompareScreen` operate on the selected instance. `api.getComparison` remains the source of measured comparison results. A stale response cannot replace a different plan's comparison. Zero/undefined baselines and worse results are not presented as improvements.
- `api.startEvolution`, `watchEvolution`, and `api.cancelEvolution` retain the Phase 3/4 lifecycle. Polling continues while the lab is hidden. Requests and callbacks are scoped to the active run ID. Duplicate mutations are guarded, and failures stay visible until dismissed or retried.
- `api.applyWinner(runId, instanceId)` still posts to the existing solve endpoint. The returned instance and method must match before storing a result. Applying a winner recomputes fleet routes; neither training fitness nor held-out scores are substituted for route distance.
- `EvaluationSummary` presents held-out means separately from selected-plan comparisons. `EvolutionPanel` uses the server winner ID, preserving tie behavior; other candidates remain inspectable in collapsed history.
- Map and driver details share App's selection. Road distance units remain meters/kilometers; synthetic distances remain map units. Missing road geometry gets a visible warning and dashed straight-line previews. Unavailable map tiles get their own message.

The Python engine, backend, API request/response contracts, and Phase 1–4 fixes were not changed. No new frontend dependencies were added. Existing unused legacy panels were retained rather than deleting unrelated work; the guided app does not mount them.

## Design and accessibility

Warm off-white surfaces, charcoal text, restrained teal actions, consistent controls/cards/statuses, compact metrics, and a map-focused routes view replace the mixed dashboard. The Home display type is editorial; operational screens use the system sans-serif stack. External font and stylesheet requests are unnecessary.

Inputs have labels; wizard errors/statuses are announced; navigation exposes the active page; step indicators expose the active step; driver selection uses pressed states; a skip link and focus handling support keyboard navigation. All four navigation destinations fit the small viewport. The road map retains zoom, popups, draggable locations, and attribution.

## Verification

Final checks:

- Frontend unit/service/render regressions: **18 passed, 0 failed**, including all 11 earlier frontend checks.
- Real Chromium interaction checks with mocked API responses: **16 passed, 0 failed**. Covered navigation/Back/Forward, wizard persistence/validation, two baseline calls on one instance, synchronized driver selection, honest comparisons, polling recovery/progress, cancellation, winner application on two different plans, partial failures/retries, road entry persistence, explicit road failures, units/geometry warnings, and no browser runtime exceptions. External requests were blocked before navigation; the synthetic journey requested no external resources.
- TypeScript: **passed**, exit 0.
- Real local Uvicorn/Vite smoke: **9 passed, 0 failed**, using synthetic instances and mock evolution with the actual optimization engine. No live LLM or OSRM calls.
- Production Vite build with environment files disabled: **passed**, 88 modules transformed.
- Final tracked frontend diff whitespace check: **passed**. Existing unrelated modifications were preserved.

Screenshots were inspected for Home, setup review, routes/driver selection, comparison, Evolution Lab, mobile comparison/setup, and offline road setup. Browser screenshots use explicitly mocked test fixtures for layout verification; they are not measured optimization results. They are stored in `runs/redesign-verification/`, with machine-readable browser results in `results.json`.

Exact commands from `D:\routeIQ\web`:

```powershell
npm.cmd test
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
node --input-type=module -e "import { build } from 'vite'; import react from '@vitejs/plugin-react'; await build({configFile:false,envFile:false,plugins:[react()]});"
```

From `D:\routeIQ`:

```powershell
node web/tests/workflow-browser.mjs
python -B scripts/smoke_phase3.py
git diff --check -- web/src/App.tsx web/src/components/RouteVisualization.tsx web/src/index.css web/package.json web/index.html
```

The local test runner/browser/build initially hit sandbox process-launch restrictions and succeeded with scoped execution permission. Browser harness issues were corrected: loopback must be exempt from its external DNS block; accessible button labels exclude decorative arrows; already-cancelled tile interceptions are recorded separately from application exceptions. Earlier rendering assertions were updated to require “longer” wording and inspect the authoritative winner card while allowing other candidates' code in history. Assertions were not relaxed to accept failed application behavior.

## Changed files in this redesign

- Entry/design: `web/index.html`, `web/public/routeiq.svg`, `web/package.json`, `web/src/App.tsx`, `web/src/index.css`.
- New guided views: `web/src/components/SetupWizard.tsx`, `web/src/components/CompareScreen.tsx`, `web/src/components/EvolutionLab.tsx`, `web/src/components/EvaluationSummary.tsx`.
- Refactored/reused views: `web/src/components/EvolutionPanel.tsx`, `web/src/components/CompactResults.tsx`, `web/src/components/DriverDetailsPanel.tsx`, `web/src/components/RouteVisualization.tsx`, `web/src/components/InteractiveMap.tsx`, `web/src/components/LocationPicker.tsx`.
- Workflow logic: `web/src/services/workflow.ts`.
- Tests: `web/tests/phase3.cjs`, `web/tests/workflow.cjs`, `web/tests/workflow-browser.mjs`.
- This report: `docs/frontend-redesign.md`.

## Limits and unverified external workflows

- Live LLM execution, external OSRM availability, live tile appearance, and device geolocation were deliberately not exercised. Their controls remain available, with explicit errors and no simulated production success.
- Geographic map markers and road failure states were tested offline; the synthetic flow and actual engine/winner application were exercised locally.
- State survives navigation within the tab, not reloads. Backend state is still process-local, as documented in Phase 4. Cancellation remains cooperative at backend boundaries.
- No address-search/geocoding service, manual synthetic-coordinate API, deployment, or additional feature phase was introduced. Within the existing contracts, no requested guided screen is left unfinished.
