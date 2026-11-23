# RouteIQ watercolor frontend redesign

Completed 2026-11-16. This redesign preserves the current application and all earlier repair/research work.

## Delivered

- Home: original SVG city-map study, editorial headline, asymmetric feature layout and clear route-plan action. The illustration is explicitly labelled decorative, never used as a geographic map or measured result.
- Setup: retained four-step workflow and all inputs, workload policies and validation; new step states, compact plan summary, clear readiness feedback, shared map controls and accessible confirmations.
- Routes: integrated map/driver workspace, compact measured metrics, consistent driver palette, custom depot/numbered stop markers, selected-route emphasis, fit-to-bounds, resize handling, metric scale and original-color toggle. Real geometry and coordinates remain unchanged.
- Compare: zero-based measured-distance bars, inspect-route actions, retained detailed distance/runtime/work/feasibility/completion table. Incomplete searches remain labelled; existing baseline percentage calculations are unchanged.
- Evolution Lab: actual fitness progression (gaps are not interpolated), generation timeline, candidate measurement table, recorded-parent lineage, and retained winning configuration, application, export, cancellation, budgets and experiment-control history. Pending metrics display as unavailable. Offline fixtures remain explicitly distinct from real LLM proposals.
- Shared design: ivory/ink/teal/sage/lavender palette, original SVG icons and brand mark, locally hosted Playfair Display/Inter/IBM Plex Mono, consistent controls/status treatments, focus states, native modal dialog with Escape/focus restoration, restrained motion and reduced-motion support.

## Preservation and integration

Before editing, the complete active frontend, API interactions and all 11 supplied reference images were inspected. Existing App state, routing/result identity validation, API services and optimization controls were retained. No new backend endpoint or research evaluation was introduced.

`runs/frontend-redesign/watercolor-before.json` and `before/` capture the pre-redesign tree. Byte-level verification confirms **100 backend/engine/reference-asset files unchanged**, plus **96 protected research artifacts unchanged** against the Phase 7 manifest. Other pre-existing modifications were preserved. No environment files or secrets were read or modified. No live LLM or OSRM requests were made.

## Exact changed files

Modified existing files (relative to the redesign snapshot, not the already dirty Git baseline):

- `web/src/App.tsx`
- `web/src/main.tsx`
- `web/src/components/CompareScreen.tsx`
- `web/src/components/DriverDetailsPanel.tsx`
- `web/src/components/InteractiveMap.tsx`
- `web/src/components/LocationPicker.tsx`
- `web/src/components/RouteVisualization.tsx`
- `web/src/components/SetupWizard.tsx`
- `web/src/components/StrategyLab.tsx`
- `web/tests/product-browser.mjs`
- `web/tests/workflow-browser.mjs`
- `web/tests/workflow.cjs`

New source, tests and documentation:

- `web/src/components/Design.tsx`
- `web/src/components/Home.tsx`
- `web/src/components/MapDesign.tsx`
- `web/src/components/ResearchVisuals.tsx`
- `web/src/services/presentation.ts`
- `web/src/watercolor.css`
- `web/tests/visual-design.cjs`
- `scripts/smoke_frontend_redesign.py`
- `docs/frontend-watercolor-redesign.md`

New assets:

- `web/public/fonts/inter.ttf`, `inter-OFL.txt`
- `web/public/fonts/playfair-display.ttf`, `playfair-display-OFL.txt`
- `web/public/fonts/ibm-plex-mono.ttf`, `ibm-plex-mono-OFL.txt`
- `web/public/fonts/sources.json` (download origins and SHA-256 fingerprints)

All original SVG artwork/icons/markers are implemented in the new React components. No reference asset was overwritten or inserted as a stretched design-board image. New verification artifacts, screenshots and test browser profiles are under `runs/frontend-redesign/`; existing Phase 7 evidence remains intact.

## Commands and actual verification

From `D:\routeIQ\web`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run test:browser
```

- Frontend: **47 passed, 0 failed** (34 existing + 13 new presentation regressions).
- Build: **passed**, includes `tsc` followed by the existing env-disabled Vite wrapper; 99 modules, JS 402.15 kB (122.26 kB gzip), CSS 75.23 kB (19.93 kB gzip).
- Existing browser workflow: **18 passed, 0 failed**, zero runtime exceptions; 78 external tile requests blocked.

From `D:\routeIQ`:

```powershell
python -B scripts/smoke_frontend_redesign.py
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/frontend-redesign/offline.xml -q
python -B runs/frontend-redesign/verify_preservation.py
```

- Real local backend/frontend browser: **25 passed, 0 failed**, zero runtime exceptions; 73 external tile requests blocked. Includes all five screens at 390/768/1280 widths plus 1440 desktop; map placement/drag/removal, color/fit controls, actual geometry and failure disclosure, keyboard modal handling, reduced motion, candidate lineage, cancellations and strategy application on two distinct instances.
- Independent full-matrix cost/coverage audit: **11 route results passed**; current-instance matrix/problem identity and longest route independently verified.
- Offline backend regressions: **900 passed, 1 deselected**, one existing Starlette/httpx deprecation warning; 285.22 seconds. Only the environment-example inspection test is explicitly deselected to honor the environment-file restriction. No test assertions were weakened or deleted.
- Python AST: **120 files parsed**. Preservation audit passes.

Node/esbuild/Chromium needed execution outside the process-restricted sandbox after initial `spawn EPERM` errors. No package installation was necessary. Vite disables environment-file loading. The real smoke script forbids dotenv reads and external HTTP transports, runs real local solvers, and supplies explicit offline road-service fixtures.

Failures found and corrected during verification: mobile nav overflow; a missing argument in the test's CDP confirmation binding; pending candidate metrics causing a render exception; SVG title SSR warnings. An added reduced-motion check initially selected an absent direct-child section; corrected to test the actual button transition. Final runs above passed.

## Screenshot evidence

All are real local Chromium screenshots; no generated product mockups.

- [Home](../runs/frontend-redesign/product-browser/01-home.png)
- [Setup](../runs/frontend-redesign/product-browser/02-setup.png)
- [Routes](../runs/frontend-redesign/product-browser/03-routes.png)
- [Compare](../runs/frontend-redesign/product-browser/04-comparison.png)
- [Evolution Lab](../runs/frontend-redesign/product-browser/05-strategy-lab.png)
- [Measured research charts/table](../runs/frontend-redesign/product-browser/10-research-evidence.png)
- [Road workspace with offline geometry fixtures](../runs/frontend-redesign/product-browser/09-road-routes-offline-fixtures.png)
- [Keyboard confirmation](../runs/frontend-redesign/product-browser/confirmation-keyboard.png)

Additional `{home,setup,routes,compare,lab}-{390,768,1280}.png` files cover responsive layouts. Browser result manifests: `product-browser/results.json`, `legacy-browser/results.json`; solver audit: `smoke-measurements.json`; backend JUnit: `offline.xml`; preservation: `preservation.json`. `failure.png` files retain intermediate failed-run evidence and are not final screenshots.

## Map/provider and asset decisions

The existing OpenStreetMap raster provider remains, using its documented HTTPS endpoint and visible attribution. A restrained CSS filter applies only to raster tiles; markers and actual route geometry retain their own colors. Users can toggle original map colors. Raster tiles do not support independent styling of roads/waterways. No new provider/key dependency, tile prefetch or bulk download was added. See the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/).

The three fonts and their OFL licenses came from the official [Google Fonts repository](https://github.com/google/fonts/tree/main/ofl); exact per-file origins and hashes are in `web/public/fonts/sources.json`. They are served locally, so the running app makes no external font requests.

## Limitations and deliberately deferred work

- Live basemap appearance, LLM responses and external OSRM availability were not exercised. Tile failures are explicit; road screenshots use declared local fixtures. The muted raster style is not a custom vector watercolor basemap.
- Direction arrows/animated route drawing were not added. Actual polylines, numbered stops and driver itineraries retain route-order information; missing road geometry is never replaced with invented paths.
- The current strategy API supplies development experiments, not frozen validation/held-out artifacts. The Lab explicitly labels validation unavailable through this API and the historical 88 missing held-out LLM measurements. Legacy evaluation remains accessible. No new research evidence or LLM-versus-random superiority is claimed; recorded tab history is not represented as an unbiased paired comparison.
- Driver colors repeat after ten drivers; numbered driver names, selection and itineraries remain the primary identity cues.
- Responsive and keyboard checks ran in local Chromium, not a full cross-browser or assistive-technology certification. Existing in-memory/tab-lifetime persistence limitations are unchanged.

No engine, benchmark protocol, historical baseline, solver, strategy schema or held-out guard changes were made.
