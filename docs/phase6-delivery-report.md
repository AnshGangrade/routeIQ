# RouteIQ delivery verification

Date: 2026-11-25. This report covers the integrated planning workspace, charcoal/
gold identity, adaptive controller, measured product outputs, and four-arm
evaluation, followed by this verification phase. It does not reinterpret the
older research Phase 6B as complete.

## Repository state and preservation

Before editing, branch `master` was at `ed757a0` (`simpleEvolution`), with **34
modified tracked files and 19 untracked files**. These existing modifications
were reported before editing. The exact path/status/SHA-256 inventory is
`runs/phase6-verification/preexisting-worktree.json`. Original test harness copies
are under `runs/phase6-verification/preexisting-files/`.

This phase adds no production architecture changes. It changes only:

| File | Change in this phase |
|---|---|
| `tests/unit/test_delivery_verification.py` | New 16-case backend acceptance suite |
| `web/tests/product-browser.mjs` | Additional integration/deep-link/resize checks, six delivery captures, new output directory |
| `web/tests/workflow-browser.mjs` | New output directory; existing assertions preserved |
| `scripts/smoke_frontend_redesign.py` | New output directory; actual local solver and explicit offline service fixtures preserved |
| `docs/phase6-delivery-report.md` | This delivery report |

Hash comparison confirms the only pre-existing files altered by this phase are
the three test/smoke harnesses above. Production source remains unchanged. No
commit, push, reset, cleanup of research records, or overwrite of historical
experiments was performed. All new verification artifacts are under
`runs/phase6-verification/`. The Phase 5 frozen protocol/source still verifies.

## Delivered architecture and logical phases

1. **Integrated workspace:** `App.tsx` owns the selected instance, draft,
   per-method results, scoped job identity and driver selection. The persistent
   `PlanningWorkspace` replaces separated wizard/result experiences while
   preserving both `#setup` and `#routes` entry links. The planning column scrolls
   independently beside the map; mobile exposes a collapsible planning panel.
   Draft identity changes hide stale results and block inappropriate reuse.
2. **Visual identity:** existing global styles and map components use warm white,
   charcoal and restrained gold. Leaflet remains the geographic renderer with
   attribution and zoom controls. Grayscale tiles and separate route casing/
   stroke panes preserve actual returned geometry. Synthetic coordinates remain
   explicitly labeled, not presented as streets. A ResizeObserver invalidates the
   actual Leaflet viewport as the layout changes.
3. **Adaptive controller:** `engine/routing/control.py` adds a scheduling contract
   to the existing hybrid solver. `engine/strategies/adaptive_models.py`,
   `adaptive.py`, `experience.py` and the bounded provider implement aggregate
   problem-aware selection, finite feedback actions, shared work/deadline caps,
   precise attribution and recorded-decision replay. The engine owns routes;
   independently validated cost/feasibility determines the retained result.
4. **Product evidence:** `routeEvidence.ts`, `CompactResults`, `RouteExplanation`
   and `CompareScreen` display named-baseline savings, feasibility, workloads,
   available driving time, runtime and honest completion state. Explanations use
   recorded gains and measured driver comparisons, never free-form model claims.
   Diagnostics stay collapsed by default.
5. **Evaluation:** `controller_benchmark.py`, `controller_reporting.py` and the
   explicit CLI compare conventional hybrid, random selection, static LLM and
   adaptive LLM under one frozen protocol. Every trial is preserved. Completed
   pairs and bounded incomplete incumbents remain separate; protected splits
   cannot enter experience prompts. See `docs/controller-value-evaluation.md`.
6. **Verification:** this phase adds boundary, leakage, replay and browser checks,
   reruns existing suites and captures the delivered UI without redesigning it.

Detailed prior-phase file inventories and decisions are in
`docs/adaptive-strategy-controller.md`, `docs/product-outputs.md`, and
`docs/controller-value-evaluation.md`. The complete pre-existing inventory above
also includes the workspace/identity files from phases 1–2.

Request flow: the draft creates a canonical instance through the FastAPI instance
endpoint; its immutable matrix/problem identity is retained. Historical solves
or scoped optimization jobs use that exact problem. The backend independently
checks complete fleet coverage, depot returns, workload and cost before publishing
a result. Polling uses the selected job/instance identity. Results feed the
summary, comparison and interactive map; road polylines use returned geometry
only. Updating the draft hides results until it again matches the saved plan or a
new instance is generated.

## Coverage

| Requirement | Evidence |
|---|---|
| One integrated screen / existing deep links | Cold `#setup` and `#routes` navigation, exactly one workspace, no stepper, same mounted component and draft across aliases |
| Draft-to-map synchronization | Real Leaflet marker creation/removal/dragging, coordinate edits verified in marker popup, depot placement |
| Stop/driver/marker selection | List-to-marker and marker-to-list selection, driver itinerary, highlighted routes, measured insight-to-driver focus |
| Stale handling | Draft changes remove result summary/geometry and disable optimization; reverting restores matching results |
| Responsive / map sizing | 1440×900, 1024×768, 768×900, 390×844; independent scrolling, panel collapse, actual SVG renderer dimensions against map dimensions |
| Mobile overflow | Document and navigation width assertions, Compare and Strategy Experiments on mobile |
| Valid/invalid model responses | Schema, duplicate/nonfinite JSON, unsupported actions, explicit provider failures and unfinished/oversize responses |
| Bounded actions/work | Controller schema and optimizer boundary both reject invalid actions/caps; global work/token/call limits verified |
| Cancellation/timeouts | Slow stream cancellation/deadline closes resources; scoped job cancellation becomes terminal without cancelling another job |
| Unavailability / fallback | No initial fake AI route; invalid checkpoints explicitly deterministic fallback; no random result relabeled as AI |
| Independent validation | Forged successful operator output rejected; retained routes revalidated; local smoke recomputes full matrix edge sums |
| Reproducibility | Fixed decision replay yields the same routes/work; changed seed, source, allocation, decisions and final-route fingerprint rejected |
| No held-out leakage | API and experience importer reject protected split IDs before reading their measurement records or creating a model controller |

## Exact verification commands

From repository root:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_delivery_verification.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/phase6-verification/backend-tests.xml -q
web/node_modules/.bin/tsc.cmd --noEmit --incremental false -p web/tsconfig.json
npm.cmd --prefix web run build
python -B scripts/smoke_frontend_redesign.py
git diff --check
```

From `web`:

```powershell
npm.cmd test
npm.cmd run test:browser
```

Python AST verification:

```powershell
@'
import ast
from pathlib import Path
excluded={'.git','venv','.venv','env','ENV','node_modules','__pycache__','dist','build'}
paths=[p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts)]
for p in paths:
    ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
print(len(paths), 'passed')
'@ | python -B -
```

| Check | Result |
|---|---|
| New backend acceptance tests | 16 passed, 0 failed |
| Full offline backend suite | 989 passed, 0 failed, 1 explicitly deselected; 327.47 seconds |
| Frontend unit/component tests | 78 passed, 0 failed |
| Mocked-API Chromium workflow | 20 passed, 0 failed |
| Real-backend Chromium smoke | 41 passed, 0 failed; 242 external requests blocked |
| Independent smoke matrix/coverage audit | 13 route results passed; scoped cancellation and two-instance strategy application verified |
| TypeScript | Passed, exit 0 |
| Production build | Passed; 103 modules transformed |
| Python AST | 415 files passed, including preserved source snapshots |

The excluded existing test reads `.env.example`; it is deliberately not run to
honor the no-environment-file constraint. No test was weakened or deleted.
One existing Starlette/httpx deprecation warning remains. Live/manual tests are
outside the offline regression command. Vite smoke/build disable environment-file
loading, and external browser/HTTP requests are blocked during smoke.

The first expanded real-backend smoke passed 32 checks, then the new resize test
failed because its selector targeted Leaflet's default overlay pane rather than
RouteIQ's existing custom route panes. The test now locates the rendered
`.route-path` and its containing SVG; dimension assertions were retained. No
production change was required. First-attempt evidence is preserved in
`first-smoke-attempt.json` and `product-browser/first-attempt-resize-selector.png`.
The corrected smoke then passed all 41 checks. All six delivery captures were
visually inspected. The production source needed no fixes during verification.

## Delivery screenshots

All paths are relative to repository root. Captures show the actual local UI and
solver output, not generated mockups. The six requested views use synthetic
coordinates and honest measured results; they are not screenshots of live road
service responses. Supplemental road screenshots use explicitly injected offline
geometry, and unavailable paths stay absent. External map tiles are blocked.

| View | Screenshot |
|---|---|
| Integrated Route Plan, desktop | `runs/phase6-verification/product-browser/delivery-01-integrated-desktop.png` |
| Optimized multi-driver routes | `runs/phase6-verification/product-browser/delivery-02-optimized-multi-driver.png` |
| Expanded driver itinerary | `runs/phase6-verification/product-browser/delivery-03-expanded-itinerary.png` |
| Compare | `runs/phase6-verification/product-browser/delivery-04-compare.png` |
| Strategy Experiments | `runs/phase6-verification/product-browser/delivery-05-strategy-experiments.png` |
| Mobile Route Plan, 390×844 | `runs/phase6-verification/product-browser/delivery-06-mobile-route-plan.png` |

The synthetic capture deliberately includes more drivers than stops, showing
valid empty routes. Its zero savings and incomplete status are retained rather
than inventing a better demonstration. The research screen retains the older
Phase 6B warning about 88 missing held-out LLM-arm measurements.

## Live Ollama and experimental findings

**The adaptive controller was implemented and tested with real local Ollama
`qwen3:1.7b` in Phase 5.** This delivery phase reruns offline behavior tests; it
does not rerun the live experiment or claim mocked browser proposals are live.
The immutable live evidence remains in `runs/controller-value-20261125/`.

- 192 trials across frozen development and validation: 190 feasible results,
  two initial-selection failures, no missing measurements.
- Adaptive vs static LLM tied on all 12 valid validation incumbent pairs. The
  adaptive arm consumed an additional 10.073 seconds across validation trials.
- Against conventional hybrid, adaptive had nine ties and three losses on valid
  validation incumbent pairs. No completed-only hybrid pair was available.
- The three completed adaptive-versus-random validation pairs came from only one
  underlying instance; their small mean gain is not evidence across diverse
  independent problems.
- Accepted feedback actions were only `continue`: no accepted reorder or
  diversification was measured. Larger cases exhausted work before feedback.
- The recorded decision is **do not promote either LLM arm**. No repeatable LLM
  advantage has been demonstrated; no held-out evaluation was run.

The four-arm protocol, report reconstructions, independent route/paired audits,
negative results, failed requests and frozen source snapshot remain intact.

## Remaining limitations

- No new live OSRM/map-tile verification in this phase. Road rendering/error paths
  are tested with explicit offline fixtures, not claimed live-service reliability.
- Application state remains local/in-memory and single-worker; full page reloads
  and server restarts are not durable draft/job persistence. SPA navigation does
  preserve the selected plan and draft.
- The older development-experiment persistence path has previously encountered
  intermittent Windows `PermissionError`; this verification does not claim a
  durability fix. Historical incomplete research stays incomplete.
- Independent validation and search are cooperative with deadlines; disconnecting
  an HTTP request does not guarantee Ollama stops inference server-side. Inference
  hardware cost is not independently metered. This is not a sandbox-security claim.
- The live panel has only four independent cases per split, with many incomplete
  searches; model weights were not digest-pinned. Exact live inference replay and
  broad superiority are not established.
- Operator telemetry identifies fleet gains, not an affected driver for every
  move. Driver-specific explanations remain separate measured comparisons.
- A final held-out controller evaluation remains deliberately disabled pending a
  separately reviewed final freeze/evaluation workflow. Existing held-out guards
  and protected records were not bypassed or reset.
