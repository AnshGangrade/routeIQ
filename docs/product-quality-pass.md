# Product and research quality pass — 2026-11-26

Starting branch: `master`, commit `4403750` (`reWrap`). Working tree was clean.
Historical ignored `runs/` artifacts are evidence, not disposable build outputs.

## Architecture and contract audit

The active application is `App` → persistent `PlanningWorkspace` / Compare /
StrategyLab → typed services → FastAPI instance, routing, optimization and strategy
routers. Immutable FleetProblem owns matrix, workload and fingerprints. Historical
FleetRouter baselines remain separate from trusted construction/VND/ILS. The
adaptive controller schedules that existing search; declarative evolution evaluates
fixed strategies. Executable-code evolution and its sandbox remain legacy backend
capabilities, not the current product workflow.

Contradictions identified before editing:
- Compare chooses shortest regardless of completion, unlike recommendedResult.
- ILS schedule completion is classified as resource exhaustion.
- Strategy loop completion and bounded fitness can look like completed winners.
- Driver identifiers are colored in lists but discarded by map markers/routes.
- Construction can consume controller work before any feedback checkpoint.
- Independent static/adaptive initial proposals do not isolate feedback value.
- README/steering foreground legacy executable code; three CSS layers conflict.

## Acceptance checklist

- [x] Inspect Git, source/API contracts, tests and local historical evidence.
- [x] Consolidate tokens, remove slogans, retain operational layout and disclosures.
- [x] Stable distinct driver identity through list, legend, markers and routes.
- [x] Verify integrated map/draft/selection/stale/mobile behavior.
- [x] Completed-first recommendation, incomplete alternative, identity-safe savings.
- [x] Versioned validity/completion/termination/resource status; preserve old records.
- [x] Separate completed and bounded candidate rankings and honest LLM attribution.
- [x] Reserved adaptive work, meaningful scheduling, failure/replay/budget tests.
- [x] Matched-initial ablation plus balanced end-to-end protocol and saved evidence.
- [x] Measured route output, longest route and truthful driving-time labels.
- [x] Current README and steering; historical reports unchanged.
- [x] Focused/backend/frontend/browser/AST/TypeScript/build/diff verification.
- [x] Visual captures, exact commands/counts, live/fixture distinction and limitations.

No held-out execution is authorized by this checklist. Final held-out work requires
the separately frozen protocol and single-use authorization described in the request.

## Implemented contracts

- `index.css` is the authoritative token, typography, button and base-surface layer.
  Existing component and workspace styles retain their filenames; duplicated global
  overrides were removed. Twenty supported driver IDs have stable muted colors,
  supplemented by route patterns and numbered stops. Selection changes width/opacity,
  not identity. Both SVG and Leaflet consume the same presentation helper.
- Compare uses the completed-first shared recommendation helper. A shorter incomplete
  alternative remains actionable with its actual distance difference. Server-side
  savings independently revalidate cached routes and matrix costs. Unknown legacy
  records remain visible but cannot establish percentage savings.
- `fleet-search-status/v2` is additive metadata for new results. Route validity,
  search state, schedule completion, termination and budget exhaustion are separate.
  Finishing configured ILS iterations is complete if scans were not truncated and
  there were no failures. Controller stop is incomplete but not resource exhaustion;
  neighborhood truncation is separate from global operations/time/operator-call caps.
  Existing status strings/API job states remain compatible; saved old statuses are
  never rewritten. The corrected classifications must not be pooled with old
  completed-only statistics as though the policy had stayed unchanged.
- Future strategy exports include `candidate-ranking/v2`: completed-only ranking,
  bounded ranking, recommended ID and kind. The historical bounded evolutionary
  tournament/fitness remains unchanged and explicit. The UI independently prefers a
  completed panel; otherwise it says **Best incomplete candidate** and **Test strategy
  on current plan**. Live proposal counts require accepted recorded identity and a
  valid evaluated development panel, not merely a provider label or model request.
- Controller searches retain both mandatory historical comparators. Optional
  constructors share at most one third of remaining operations. Search slices also
  reserve work for later feedback. All work charges the same parent budget. A very
  small budget can still expire in mandatory baselines; those runs remain incomplete.
  Actions record host acceptance/denial, schedule changes and ineffective reorders.
  Replay additionally checks the recorded time allowance.

## New research protocol

Frozen protocol: `7d9000c40a4314007b6a947ea069aaa03d235b52ac699c2a70077da3d3f4cdd9`.
Model: `qwen3:1.7b`, digest
`8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`.

Each split contains 24 independent cases, covering every combination of four sizes,
three distributions and two matrix directions. Driver counts rotate across all five
supported counts; this is not a full driver-count factorial. Two solver/proposal seeds
(0, 1), one trial per arm, six arms yield 288 trials per split. Every trial receives
100,000 counted operations and a 15-second wall ceiling, including proposal latency.
No limit is changed after observing results. The provider allows five seconds per
request, six total model seconds, three calls, two checkpoints, 768 output tokens,
8192 context tokens, 40,000 reserved tokens, temperature 0.3, and no retries.

The four end-to-end arms retain independently generated initial proposals. The added
paired_static/paired_adaptive arms share one accepted initial proposal and its
fingerprint. Both receive the same initial latency charge and reserved call/token
allowance. Actual initial model usage is counted once in `shared_initial_usage`;
per-arm `seconds` is actual arm elapsed time, while `charged_seconds` includes the
common initial charge. Pairs with different constructed initial routes are excluded
from the feedback ablation. Failed shared initial requests are not resampled.

Completed-only statistics and bounded-incumbent statistics have separate denominators.
The latter includes valid stopped searches, never labels them complete. Percentages
use the reference distance. Zero/zero is zero; positive cost over zero has an undefined
percentage. W/T/L uses the existing tolerance. Confidence intervals bootstrap
per-instance means, not seed replications as independent instances. Reports are
reconstructed from saved measurements, validating identity and costs; absent files
remain missing. New directories and exclusive file creation prevent overwrite.

Live preflight saved all three attempts: two five-second timeouts followed by one
schema-valid strategy (1.978 seconds; 1307 reported tokens). They are not benchmark
trials and were not used for route-quality selection. No model substitution occurred.

Historical 96-trial development and 96-trial validation reports were independently
reconstructed and matched exactly. Separately, 168 archived live strategy development
rows were revalidated for an explicitly labeled screenshot. No historical held-out
measurement was rerun, repaired, or supplied to a prompt.

## Verification commands and scope

The complete offline backend command passed **1,023 tests**, with no failures or
errors, in 378.843 seconds (JUnit duration). One environment-template test was
explicitly deselected to honor the environment-file restriction, not to conceal a
failing assertion. One Starlette/httpx deprecation warning remains.

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --basetemp=runs/product-quality-20261126/pytest-full-3 --junitxml=runs/product-quality-20261126/backend-tests-verified.xml -q
npm.cmd --prefix web test
web/node_modules/.bin/tsc.cmd --noEmit --incremental false -p web/tsconfig.json
npm.cmd --prefix web run build
npm.cmd --prefix web run test:browser
python -B scripts/smoke_frontend_redesign.py
git diff --check
```

Earlier checks were not all successful: the first full backend run had 1,012 passes
and two failures. These exposed compatibility handling for missing legacy metadata
and an old test expecting an unverified zero-distance comparison. Missing metadata
now fails verification; a new independently validated zero-matrix endpoint test
proves the valid zero/zero case still returns zero percent. A separate rerun failed
on Windows temporary-directory ACLs and was stopped; those directories remain.
The successful full run used a new temporary directory and approved execution
outside the restricted process sandbox. Browser/Node subprocess startup also needed
that execution mode after EPERM. An earlier browser assertion expected the retired
gold selected-marker style; it now verifies persistent driver identity and a dark
selection outline. Failed-run evidence was preserved.

Final frontend unit verification passed **82/82**. The stricter savings check first
exposed one fixture without completion metadata (81 passed, one failed); the fixture
now declares its intended completed baseline and retains the original worse-route
assertion. TypeScript and the production build passed (103 modules). The final
mocked-HTTP Chromium workflow passed **20/20**, including polling/cancellation,
different-instance application, stale draft state and explicit road failures.

The extended real-backend browser checks also found two test-only capture problems:
Vite's HTML fallback intercepted the saved-evidence endpoint, then a DOM-valued wait
predicate could not be serialized by CDP. The endpoint is now explicitly served by
the test interceptor and the predicate returns a Boolean. A separate idle-driver
color assertion exposed zero-length SVG depot-to-depot segments; the renderer now
omits those segments while retaining idle drivers in the itinerary and legend.
These failed attempts and screenshots remain in the new run directory.

AST validation uses only tracked and new project Python files, avoiding ignored
historical code snapshots and deliberately invalid sandbox fixtures:

```powershell
@'
import ast, subprocess
from pathlib import Path
files = subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'], text=True).splitlines()
py = sorted({f for f in files if f.endswith('.py')})
for f in py:
    ast.parse(Path(f).read_text(encoding='utf-8-sig'), filename=f)
print(len(py), 'project Python files passed')
'@ | python -X utf8 -B -
```

Result: **146 parsed, zero syntax failures**. `git diff --check` passed; Git emitted
only line-ending conversion warnings. Build, tests and browser checks never load
environment files. Live benchmark calls target only the explicitly configured local
Ollama model; they are separate from the offline test suite.

The new status, checkpoint and server comparison tests are in
`tests/unit/test_quality_contracts.py`; shared-initial protocol, preservation and
reporting tests are in `tests/unit/test_controller_ablation.py`. The full suite also
covers the prior FleetProblem, operators, hybrid, sandbox, API and lifecycle tests.
No historical baseline implementation was changed.

Research commands (already executed; do not rerun validation into its existing
directory or reset its single-use guard):

```powershell
python -B scripts/run_controller_benchmark.py freeze --config runs/product-quality-20261126/experiment-config.json --output runs/product-quality-20261126/protocol.json
python -B scripts/run_controller_benchmark.py run --protocol runs/product-quality-20261126/protocol.json --output runs/product-quality-20261126/development --split development --live
python -B scripts/run_controller_benchmark.py run --protocol runs/product-quality-20261126/protocol.json --output runs/product-quality-20261126/validation --split validation --development runs/product-quality-20261126/development --live
python -B runs/product-quality-20261126/audit_saved.py
```

The last command only reconstructs reports and independently checks saved routes,
matrix edge sums, stop coverage, workload, identity and paired statistics. It never
calls the solver or provider. Its output uses exclusive creation.

## Limitations and interpretation

- Conventional hybrid remains the default. An accepted live configuration or an
  applied feedback decision is participation, not proof it caused a better route.
  The same-initial ablation is the relevant feedback comparison.
- All arms share ceilings, not identical actual computation. Model inference
  FLOPs/memory are not measured. Provider latency consumes wall time; Python and
  HTTP deadlines are cooperative, so recorded overruns must remain visible.
- Mandatory historical baseline work can exhaust a very small global allowance
  before feedback. It is not omitted or silently abbreviated to help AI results.
- Provider/structured-response failures retain sanitized generic error categories;
  raw provider bodies are not saved. The experiment cannot retrospectively separate
  every timeout from every schema failure within that generic category.
- The 24-case panel covers size/distribution/direction cells with rotating driver
  counts, not every size/driver combination. Two seeds do not create 48 independent
  instances. Runtime is local-machine evidence, not a hardware-independent claim.
- All browser external requests are blocked. Leaflet placement, geometry rendering,
  resize and missing-geometry behavior use explicit fixtures; live OSRM availability
  and downloaded OSM cartography were not tested. No roads or addresses are invented
  in the product. Screenshot fixture geometry must not be treated as a real journey.
- Twenty driver colors have stable IDs; numbering, driver labels and line patterns
  supplement them. They are not a claim of universal color-vision distinguishability.
- Jobs and instances remain in memory; restart recovery and multi-worker coordination
  require separate work. The legacy executable-code path is preserved, not certified
  as a production-security boundary by this quality pass.
- No final held-out study was launched, no prior missing measurements were backfilled,
  and no validation result was fed back into tuning. Historical completion policies
  and new status-v2 statistics must remain separate.


## Measured live results

Both splits used the frozen `qwen3:1.7b` protocol. All 576 trial slots were recorded. Development had 141 completed and 147 incomplete trials. Validation had 127 completed, 160 incomplete and one failed trial. No measurements are missing. The failed validation initial request timed out before any solver operations; it was not retried or replaced.

| Split | Arm | Completed | Incomplete | Failed | Missing |
|---|---|---:|---:|---:|---:|
| development | hybrid | 9 | 39 | 0 | 0 |
| development | random | 24 | 24 | 0 | 0 |
| development | static_llm | 27 | 21 | 0 | 0 |
| development | adaptive_llm | 27 | 21 | 0 | 0 |
| development | paired_static | 27 | 21 | 0 | 0 |
| development | paired_adaptive | 27 | 21 | 0 | 0 |
| validation | hybrid | 8 | 40 | 0 | 0 |
| validation | random | 24 | 24 | 0 | 0 |
| validation | static_llm | 24 | 24 | 0 | 0 |
| validation | adaptive_llm | 23 | 24 | 1 | 0 |
| validation | paired_static | 24 | 24 | 0 | 0 |
| validation | paired_adaptive | 24 | 24 | 0 | 0 |

Percentage improvement uses the reference distance; negative means worse. Primary comparisons require both searches completed. Bounded comparisons also include validated incomplete incumbents. Counts below are pairs/independent cases; repeated seeds are not independent cases.

| Split | Candidate vs reference | Population | Pairs / cases | W/T/L | Mean % | Median % | Worst % | Mean extra seconds |
|---|---|---|---|---|---:|---:|---:|---:|
| development | adaptive_llm vs hybrid | completed_only | 9 / 5 | 0/4/5 | -4.594 | -1.192 | -17.870 | 2.444 |
| development | adaptive_llm vs hybrid | bounded_incumbents | 48 / 24 | 15/17/16 | -1.413 | 0.000 | -35.236 | 3.866 |
| development | adaptive_llm vs random | completed_only | 21 / 13 | 13/5/3 | 5.280 | 2.513 | -3.756 | 3.933 |
| development | adaptive_llm vs random | bounded_incumbents | 48 / 24 | 35/9/4 | 14.992 | 4.427 | -3.756 | 3.473 |
| development | paired_adaptive vs paired_static | completed_only | 27 / 14 | 0/27/0 | 0.000 | 0.000 | 0.000 | 1.676 |
| development | paired_adaptive vs paired_static | bounded_incumbents | 48 / 24 | 0/48/0 | 0.000 | 0.000 | 0.000 | 1.567 |
| validation | adaptive_llm vs hybrid | completed_only | 7 / 4 | 0/4/3 | -1.690 | 0.000 | -4.765 | 2.603 |
| validation | adaptive_llm vs hybrid | bounded_incumbents | 47 / 24 | 14/19/14 | 0.608 | 0.000 | -7.507 | 3.856 |
| validation | adaptive_llm vs random | completed_only | 19 / 12 | 14/5/0 | 3.722 | 2.847 | 0.000 | 3.860 |
| validation | adaptive_llm vs random | bounded_incumbents | 47 / 24 | 35/11/1 | 15.709 | 3.651 | -3.840 | 3.467 |
| validation | paired_adaptive vs paired_static | completed_only | 24 / 12 | 0/24/0 | 0.000 | 0.000 | 0.000 | 1.632 |
| validation | paired_adaptive vs paired_static | bounded_incumbents | 48 / 24 | 0/48/0 | 0.000 | 0.000 | 0.000 | 1.548 |

**Finding:** feedback did not improve distance in either shared-initial study: 48/48 valid pairs tied in development and 48/48 tied in validation. Completed-only pairs were 27 and 24 respectively, also all ties. Adaptive feedback added about 1.55?1.57 seconds on average across valid pairs. It made some schedule changes, but those changes did not produce a better final route in this study. Conventional hybrid remains the default.

Adaptive versus conventional bounded means were ?1.413% development and +0.608% validation. Case-mean bootstrap 95% intervals crossed zero: [?5.243%, +1.506%] and [?0.888%, +1.992%]. Completed-only adaptive comparisons had no wins over conventional. Adaptive beat random on many paired cases, but that does not establish that feedback adds value over static selection or that LLM policy is universally superior. All 30 ordered arm comparisons, all denominators, subgroup statistics and per-pair measurements are retained in each split?s JSON/Markdown report.

Feedback reached 12/12 trials at each of 20, 50 and 100 stops and 8/12 at 200 in each development adaptive arm. Validation end-to-end counts were 11/12, 12/12, 10/12, 8/12; paired-adaptive counts were 12/12, 12/12, 10/12, 8/12. Actual schedule changes occurred in 2 development trials per adaptive arm, and 2 end-to-end / 3 paired validation trials. One diversification was host-denied in each split. No quality gain is attributed merely to an accepted continue/reorder.

Development recorded 320 model requests and 428,298 reported tokens; validation recorded 310 requests and 412,510 reported tokens. Shared initial proposals are counted once, not once per ablation arm. Two validation requests have unknown token usage, so validation token totals are lower bounds. Preflight requests are separate. No counted global-operation cap or recorded wall-deadline overrun occurred. The checkpoint traces include 96 development and 111 validation deterministic fallbacks. Validation includes one explicit checkpoint timeout; the other generic provider/response failures cannot be diagnosed further from saved sanitized metadata. No fallback is labelled as an accepted LLM decision.

Saved evidence audit independently verified 288 development and 287 validation feasible route costs/coverage/workloads, and 60 paired population summaries per split. Reconstructed reports matched saved JSON exactly; source/protocol fingerprints remained unchanged. All 23,244 pre-existing historical files matched their starting SHA-256 hashes, with none missing. No environment file occurred in that preservation inventory.

Artifacts: `runs/product-quality-20261126/{development,validation}/{results.json,results.csv,report.md}`; `evidence-audit.json`; `preservation-audit.json`; `protocol.json`. Raw trial envelopes and shared-initial selections are retained alongside each report.

## Exact repository files changed

The tree began clean at `4403750`; all changes below belong to this pass. No commit or push was made. The archived README preserves the complete previous text. Generated evidence remains in the new ignored run directory.

```text
.kiro/steering/design-guidance.md
.kiro/steering/product.md
.kiro/steering/safety.md
.kiro/steering/structure.md
.kiro/steering/tech.md
README.md
api/routers/optimization.py
api/routers/results.py
docs/archive/readme-before-quality-20261126.md
docs/product-quality-pass.md
engine/evaluation/controller_benchmark.py
engine/evaluation/controller_reporting.py
engine/routing/budget.py
engine/routing/search.py
engine/routing/status.py
engine/strategies/adaptive.py
engine/strategies/evaluation.py
engine/strategies/evolution.py
scripts/smoke_frontend_redesign.py
tests/unit/test_controller_ablation.py
tests/unit/test_hybrid_search.py
tests/unit/test_phase4.py
tests/unit/test_quality_contracts.py
web/src/App.tsx
web/src/components/CompactResults.tsx
web/src/components/CompareScreen.tsx
web/src/components/Design.tsx
web/src/components/Home.tsx
web/src/components/InteractiveMap.tsx
web/src/components/LocationPicker.tsx
web/src/components/MapDesign.tsx
web/src/components/OptimizationDetails.tsx
web/src/components/PlanningWorkspace.tsx
web/src/components/ResearchVisuals.tsx
web/src/components/RouteExplanation.tsx
web/src/components/RouteVisualization.tsx
web/src/components/StrategyLab.tsx
web/src/index.css
web/src/services/comparison.ts
web/src/services/experiments.ts
web/src/services/presentation.ts
web/src/services/product.ts
web/src/services/routeEvidence.ts
web/src/types/api.ts
web/src/watercolor.css
web/src/workspace.css
web/tests/experiments.cjs
web/tests/product-browser.mjs
web/tests/product.cjs
web/tests/quality-evidence.tsx
web/tests/route-evidence.cjs
web/tests/visual-design.cjs
web/tests/workflow-browser.mjs
web/tests/workflow.cjs
```

## Final browser and visual acceptance

The real local FastAPI + Chromium smoke passed **45/45 checks**, with zero browser
runtime exceptions. An independent matrix-edge, coverage and workload audit passed
for **13 saved route results**. Terminal cancellation and recomputation of the same
strategy on two distinct instances were verified. The harness blocked 223 external
browser requests. The separate mocked-HTTP workflow passed 20/20 (102 requests
blocked). Neither count is a live OSRM/network-availability claim.

The desktop/tablet/mobile checks covered 1440?900, 1024?768, 768-pixel width and
390?844. They asserted no horizontal document/navigation overflow, usable map height,
Leaflet renderer resize, mobile panel collapse, synchronized marker/list selection,
coordinate editing/dragging, stale-result removal, and cold #setup/#routes deep links.
Screenshots were visually inspected for hierarchy, driver identity and truthful labels.

All paths below are relative to `runs/product-quality-20261126/product-browser/`:

| Requested view | Screenshot | Evidence scope |
|---|---|---|
| Home | `01-home.png` | Current product; illustration explicitly decorative |
| Integrated road-location workspace | `08-road-location-review.png` | Real Leaflet coordinates/markers; external tiles blocked and unavailable state visible |
| Multi-driver routes | `delivery-02-optimized-multi-driver.png` | Actual local synthetic solver results; distinct identities; idle drivers retained |
| Selected driver and itinerary | `delivery-03-expanded-itinerary.png` | Actual selected route and stop order |
| Completed comparison | `delivery-04-compare.png` | Actual local completed measurements |
| Incomplete-only comparison | `14-compare-incomplete-only.png` | Actual zero-budget incumbent; test response deliberately omits completed rows, explicitly labelled |
| No accepted live LLM proposals | `17-no-live-proposals.png` | Actual offline experiment, counted as zero live proposals |
| Accepted/evaluated live LLM proposals | `15-archived-live-proposals.png` | Audited historical live experiment, explicitly archived; 168 route rows independently checked |
| Actual adaptive checkpoint | `16-live-adaptive-decisions.png` | Saved new live development reorder decision rendered read-only; no new browser inference |
| Mobile workspace | `delivery-06-mobile-route-plan.png` | Actual local plan at 390?844 |

Additional `11-driver-road-geometry.png` verifies exact returned fixture geometry and
route casing; unavailable geometry remains absent. Responsive captures and failed
capture attempts are retained, not substituted for the final successful evidence.
The fixture geometry and coordinates are not evidence of a drivable real-world journey.

Final logs: `backend-tests-verified.xml`, `frontend-tests-delivery.txt`,
`build-delivery.txt`, `browser-workflow-final.txt`, `product-smoke-delivery.txt`,
`smoke-measurements.json`, and `ast-final.json` in the same run root.

Final focused regression: **34 passed, zero failed, one deprecation warning,
21.11 seconds**, using:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_quality_contracts.py tests/unit/test_controller_ablation.py --basetemp=runs/product-quality-20261126/pytest-focused-delivery --junitxml=runs/product-quality-20261126/focused-delivery.xml -q
```

The requested product/engineering/evidence pass is delivered. A positive causal LLM
quality claim is **not** delivered: the measured feedback result is negative. A new
held-out study, live road-service check, production deployment/security hardening,
and generalization beyond this local panel remain outside this pass.
