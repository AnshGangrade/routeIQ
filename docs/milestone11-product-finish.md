# Milestone 11: product finish and visual identity

Delivered 28 November 2026 on `master`, starting at `5fafb49` (`atleastWorking`). The working tree was clean at initial inspection. Resumed implementation changes were preserved. Nothing was committed or pushed.

## Implementation

The add-on's cool-grey, white, emerald and restrained cyan direction supersedes Field Atlas. A geometric route-network mark and matching favicon replace the old brand pin-and-wave. Desktop has a horizontal header with plan context; mobile has a compact header and bottom navigation. Home, Route Plan, Compare and Evolution share typography, controls, status messages and rounded surfaces. Existing local fonts and the stable driver colour palette remain.

Stylesheet ownership is explicit: `index.css` owns tokens and shared primitives; `watercolor.css` owns page content (the historical filename remains); `workspace.css` owns the shell and persistent planning/map layout. Shared PageHeading and EmptyState components avoid independent page conventions. No dependencies were added.

Route Plan remains mounted across navigation, preserving draft, map and selection state. Leaflet, OpenStreetMap attribution, returned road geometry, manual/map entry, stop editing, driver itineraries, baseline routing, optimization and strategy application remain. Synthetic coordinates are clearly distinguished from roads. The optional higher-contrast map control remains; default tiles are unfiltered.

Compare recommends only completed, verified measurements. It checks problem/matrix identity, units, feasibility, coverage, workload, driver identity, total/per-driver/longest distances, completion reason and exhaustion/truncation flags. API comparison rows have an additive `server_verified` field, based on independently recomputing costs from the canonical matrix. Mismatched cached rows remain diagnostic evidence instead of blocking the entire comparison response. Savings require a completed verified historical Nearest Neighbor baseline. Incomplete, failed and unverified rows stay in collapsed Technical diagnostics, excluded from recommendations, normal selection and charts. Comparison execution never publishes incomplete or contradictory results to primary route state.

The API independently verifies longest-route distance. Browser validation additionally rejects nonfinite longest-route values and explicit `schedule_completed=false`.

Evolution remains the single AI-guided strategy workflow. Export adds a trusted-seed comparison only after revalidating both complete panels, canonical matrices, seeds and budgets. The UI reports improvements, ties, losses and zero-baseline cases honestly. This is development evidence, not current-plan route distance or proof of AI superiority. Configuration-fingerprint tie-breaking now matches the engine; previously the UI could display a different equal-score candidate and omit its seed comparison. The solver and evolution policy were not changed.

## Visual refinement and evidence

Initial screenshots exposed unreadably small synthetic marker labels on mobile. A ResizeObserver now maintains marker/label size without altering coordinates. Local integration screenshots also exposed road geometry clipping or inappropriate zoom after viewport changes. The existing Leaflet resize observer now refits current selected bounds while preserving the map instance; hidden/zero-size containers are ignored. Browser assertions check road marker containment at every requested viewport.

Captured and inspected sizes: **1440 x 900, 1280 x 800, 768 x 1024, 390 x 844**. Page and navigation overflow assertions pass. Keyboard skip navigation, synthetic stop selection and reduced-motion behaviour were exercised.

Before-change reference: `runs/workflow-completion-20261127/workflow-browser-1795807906481/03-routes-desktop.png`.

Final UI fixture screenshots: `runs/milestone11-20261128/workflow-browser-1795814446758/`.

Final actual API/solver screenshots: `runs/milestone11-20261128/browser-1795814376554547600/`.

Each filename below exists with `-1440.png`, `-1280.png`, `-768.png` and `-390.png` suffixes.

| Screen | Directory | Filename stem |
|---|---|---|
| Home | UI fixture | `01-home-desktop` |
| Route Plan setup | UI fixture | `02-setup-review` |
| Synthetic multi-driver results | UI fixture | `03-routes-desktop` |
| Compare | UI fixture | `04-comparison` |
| Evolution | Actual API/solver | `01-completed-strategy` |
| Trusted-seed comparison and apply action | Actual API/solver | `01a-trusted-seed-comparison` |
| Completed strategy application | Actual API/solver | `02-applied-route` |
| Incomplete attempt retains completed result | Actual API/solver | `03-incomplete-retains-route` |
| Manual road setup and map | Actual API/solver | `04-road-draft` |
| Road geometry | Actual API/solver | `05-road-routes` |
| Expanded driver itinerary | Actual API/solver | `06-driver-itinerary` |
| Verified road comparison | Actual API/solver | `07-road-comparison` |

These are actual browser captures, not mockups. The UI-only harness uses API fixtures. The integration harness uses real local FastAPI, the deterministic solver and independent validation, with explicitly mocked Ollama HTTP and road-service geometry/matrices. Road tiles were blocked deliberately; screenshots disclose “Map background unavailable”. They do not demonstrate live cartographic tiles or live OSRM accuracy. Dense neighbouring stops may overlap at overview zoom; zoom and panel collapse remain available.

## Verification

Commands ran from `D:\routeIQ` with fresh output directories. Node/Chromium and isolated Python workers required execution outside the restricted process sandbox; initial restricted `npm test` returned `spawn EPERM`. No secrets or environment files were accessed. The existing Vite wrapper disables environment-file loading; backend checks install `tests.offline_guard`.

| Check | Actual result | Final log |
|---|---|---|
| Frontend tests | 89 passed, 0 failed | `frontend-delivery.txt` |
| Browser UI regressions | 23 passed, 0 failed | `browser-delivery.txt` |
| Real local API/browser integration | 11 passed, 0 failed | `local-integration-resize.txt` |
| Independent matrix/route audit | 9 results passed | API screenshot directory, `independent-audit.json` |
| Focused backend regressions | 155 passed | `backend-focused.txt` |
| Full established offline backend suite | 1059 passed, 1 deselected, 0 failed | `backend-full.txt`, `backend-full.xml` |
| Python AST | 151 project Python files, 0 failures | `ast.txt` |
| TypeScript | passed, exit 0 | standalone command and production build |
| Production build | passed, 103 modules transformed | `build-delivery.txt` |
| Diff whitespace check | passed | `git diff --check` |

Logs are under `runs/milestone11-20261128/`. The full backend suite's one deselection is the existing `.env.example` content-reading test, explicitly excluded to maintain the no-environment-file-access constraint. Tests were not removed or weakened. Frontend tests asserting incomplete recommendations now assert the required exclusion policy; successful fixtures include full driver metrics and valid completion evidence. One pre-existing Starlette/httpx deprecation warning remains.

```powershell
npm.cmd --prefix web test
npm.cmd --prefix web run test:browser
node web/node_modules/typescript/bin/tsc --noEmit -p web/tsconfig.json
npm.cmd --prefix web run build
python -B scripts/smoke_completed_workflow.py
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_milestone11.py tests/unit/test_completed_workflow.py tests/unit/test_phase7.py tests/unit/test_strategy_evolution.py tests/unit/test_strategy_api.py tests/unit/test_quality_contracts.py --basetemp=runs/milestone11-20261128/pytest-focused -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --basetemp=runs/milestone11-20261128/pytest-full --junitxml=runs/milestone11-20261128/backend-full.xml -q
git diff --check
```

Use fresh `--basetemp`/JUnit paths for future reruns; pytest can clear an existing base directory. Browser harnesses automatically create fresh timestamped folders.

Exact AST check:

```powershell
@'
import ast, subprocess
from pathlib import Path
files=subprocess.check_output(['rg','--files','-g','*.py','-g','!runs/**','-g','!node_modules/**','-g','!.venv/**'],text=True).splitlines()
for file in files: ast.parse(Path(file).read_text(encoding='utf-8-sig'),filename=file)
print(f'{len(files)} Python files parsed; 0 failures')
'@ | python -B -
```

Intermediate failures were retained: obsolete frontend fixtures initially failed (72 passed/12 failed); integration caught the equal-score candidate mismatch; one added test initially attempted a nonexistent second Run button after the existing one-click Optimize action. These were corrected. All final suites above pass. Screenshot refinements were verified again.

## Limits and scope

- No real Ollama inference, live OSRM requests or external services were used. Model availability in fixture screenshots is explicitly a fixture, not live evidence.
- The illustrative integration proposal measured 702.53 mean map units versus 445.57 for the best completed trusted seed: 57.7% longer. The UI correctly reports the loss. These are deterministic test measurements, not an LLM performance experiment.
- No new held-out evaluation was run. Historical research, algorithms, baselines, strategy schemas and tracked `runs/` artifacts were unchanged. New logs, screenshots and fixture checkpoints are isolated in the fresh ignored directory.
- The reference image itself was not available in the attached text files; implementation follows the written add-on design direction.
- Live tile contrast and actual provider latency were not assessed offline. This is not a formal screen-reader/accessibility certification.
- Existing in-memory/restart behaviour and local service setup are unchanged. No backend redesign, training, benchmark tuning, dependency installation or push was performed.

## Exact files changed

- `api/models.py`
- `api/routers/results.py`
- `api/routers/strategies.py`
- `scripts/smoke_completed_workflow.py`
- `tests/unit/test_phase7.py`
- `tests/unit/test_quality_contracts.py`
- `web/public/routeiq.svg`
- `web/src/App.tsx`
- `web/src/components/CompareScreen.tsx`
- `web/src/components/Design.tsx`
- `web/src/components/Home.tsx`
- `web/src/components/InteractiveMap.tsx`
- `web/src/components/LocationPicker.tsx`
- `web/src/components/MapDesign.tsx`
- `web/src/components/ResearchVisuals.tsx`
- `web/src/components/RouteVisualization.tsx`
- `web/src/components/StrategyLab.tsx`
- `web/src/index.css`
- `web/src/services/comparison.ts`
- `web/src/services/experiments.ts`
- `web/src/services/product.ts`
- `web/src/services/routeEvidence.ts`
- `web/src/types/api.ts`
- `web/src/watercolor.css`
- `web/src/workspace.css`
- `web/tests/completed-workflow-browser.mjs`
- `web/tests/experiments.cjs`
- `web/tests/product.cjs`
- `web/tests/route-evidence.cjs`
- `web/tests/visual-design.cjs`
- `web/tests/workflow-browser.mjs`
- `web/tests/workflow.cjs`
- `tests/unit/test_milestone11.py`
- `docs/milestone11-product-finish.md`
