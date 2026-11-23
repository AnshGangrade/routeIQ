# Phase 8 ? Quiet Atlas

Implemented 2026-11-23. Frontend visual refinement only; existing functionality preserved.

## Design decisions

Refined `watercolor.css` in place rather than loading a second theme. Retained the underlying layout/responsive rules, shared components, native confirmations, real Leaflet integration, and all application state/API flows. Replaced cream/serif styling with forest ink, a pale green background, white surfaces, sage structure, restrained mint accents and coral highlights. Inter and IBM Plex Mono are existing local fonts. Secondary body text uses darker #526B62 for readability; #70817B remains the secondary design token. No font download, image pack, external dependency or raster illustration was added.

Home now uses large Inter editorial typography and a small original SVG network illustration, explicitly separate from route evidence. Setup keeps all four steps and inputs. Routes keeps its real map/driver composition with a larger desktop road viewport, clearer numeric hierarchy and mint selection accents. Evolution retains actions, budgets, progress, candidate records and expandable lineage; the measured fitness chart has more space and all held-out limitations remain explicit.

Compare leads with the shortest explicitly validated same-problem measurement. Valid incomplete incumbents remain eligible for this presentation, labelled incomplete. Failed or mismatched rows cannot become the highlighted result. Ties are disclosed and no global-optimality claim is made. Alternative methods are compact; runtime/work/termination/feasibility and fingerprints remain in expandable technical diagnostics. Existing calculation controls remain there and on Routes. Unverified, failed, not-run and valid-incomplete states are distinguished.

## Exact files changed

- `web/src/watercolor.css`: existing design system refined, responsive best-result/alternative-method layouts.
- `web/src/components/Home.tsx`: original lightweight network SVG replaces decorative city study.
- `web/src/components/Design.tsx`: brand SVG colors.
- `web/src/components/CompareScreen.tsx`: honest best-result summary, compact alternatives, expandable diagnostics.
- `web/tests/visual-design.cjs`: two regression tests for incomplete incumbents and failed/mismatched exclusions.
- `web/tests/product-browser.mjs`: output destination changed to preserve earlier screenshot evidence; assertions retained.
- `web/tests/workflow-browser.mjs`: output destination changed; assertions retained.
- `scripts/smoke_frontend_redesign.py`: output destination changed to Phase 8; real local solver/fixture checks retained.
- `docs/phase8-quiet-atlas.md`: this report.

New artifacts are under `runs/phase8/`, including the pre-edit source snapshot and manifest. Existing user changes and earlier evidence are preserved. Byte-level checks confirm **87 API/engine source files** and **96 protected research artifacts** unchanged. No environment files or secrets were accessed.

## Actual verification

From `D:\routeIQ\web`:

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run test:browser
```

- Frontend tests: **49 passed, 0 failed** (47 retained, 2 added).
- TypeScript and production build: **passed** (`tsc` plus existing env-disabled Vite wrapper). 99 modules; JS 402.57 kB / 121.94 kB gzip, CSS 76.38 kB / 20.04 kB gzip.
- Existing browser workflow: **18 passed, 0 failed**, no runtime exceptions.

From `D:\routeIQ`:

```powershell
python -B scripts/smoke_frontend_redesign.py
```

- Real local backend/browser: **25 passed, 0 failed**.
- Independent matrix/coverage verification: **11 actual route results passed**.
- Includes all five screens at 390, 768, 1280 and 1440 pixels; viewport overflow checks; seed zero, empty drivers, baseline/hybrid methods, cancellations, two-instance winner application, marker placement/drag/removal, fit/color controls, returned road geometry, missing-geometry disclosure, keyboard confirmation and reduced motion.
- No live LLM/OSRM requests. Browser external resources are blocked; road services are explicit fixtures. Local solvers and backend are real. Chromium/Node subprocess tests required sandbox escalation.
- The full offline backend suite was **not rerun in Phase 8** because backend/engine code is unchanged. Earlier test counts are not presented as new results.

## Screenshots and evidence

Desktop and mobile screenshots of every screen were visually inspected. Final evidence lives in `runs/phase8/product-browser/`:

| Screen | Desktop | Mobile |
|---|---|---|
| Home | `01-home.png` | `home-390.png` |
| Setup | `02-setup.png` | `setup-390.png` |
| Routes | `03-routes.png` | `routes-390.png` |
| Compare | `04-comparison.png` | `compare-390.png` |
| Evolution Lab | `05-strategy-lab.png` | `lab-390.png` |

Also: `09-road-routes-offline-fixtures.png`, `10-research-evidence.png`, tablet/laptop variants. Machine-readable browser results: `product-browser/results.json`, `legacy-browser/results.json`; independent distances: `smoke-measurements.json`.

## Existing limitations / not verified

Live tile appearance and OSRM/LLM service availability were not tested. Screenshots show explicit missing-basemap notices and offline geometry fixtures where relevant. Real Leaflet interaction and geometry rendering were verified locally; no invented road paths were introduced. Browser coverage is local Chromium, not cross-browser/accessibility certification.

The current strategy API still exposes development evidence without frozen validation/held-out measurements. Historical 88 missing LLM-arm held-out measurements remain disclosed. No research rerun, schema/contract change, budget change or algorithm change was made. GitHub upload remains pending a destination repository from the earlier separate request.
