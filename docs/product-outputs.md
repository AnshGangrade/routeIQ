# Phase 4: measured product outputs

The Route Plan summary identifies **Nearest Neighbor (historical)** as its
baseline. It shows total and baseline distance, signed absolute savings, relative
distance, served stops, feasibility, per-driver stop counts, available driving
duration, calculation runtime, and completion state. New results bring the summary
into view within the independently scrolling planning column; the map stays put.

Savings require both results to be validated, finite and nonnegative, from the
selected problem and matrix fingerprints, with matching units. Application
results additionally pass existing coverage/depot/workload validation. Failed or
active executions cannot supply savings. Missing or legacy unverified baselines
show unavailable. A zero baseline never produces a percentage, including ties.
Worse results say longer rather than saved. Incomplete searches may provide
measured route differences but are explicitly valid incumbents, not completed
optimization. Driving duration requires values for all active drivers; its sum is
not fleet finish time. No speed or duration is inferred from distance.

## Why this route?

Explanations are deterministic templates, not LLM prose. They use existing
validated retained-distance events to attribute new fleet bests to recorded VND
operators, including 2-Opt, relocation, swaps and cross-driver operators. At most
two operator gains, the last measured no-gain pass, and one driver comparison are
shown. A trace must end at the published distance. Failed events and unrelated
traces cannot create improvement claims.

The existing telemetry does not identify the driver affected by each move.
Operator explanations therefore focus all fleet routes. A separate driver
comparison uses actual per-driver distances against the named baseline and says
whether the stop sets changed. Its link selects that driver on the map. It does
not attribute that difference to an operator. Stop counts are reported as measured;
no improvement in workload balance is inferred. Missing move-level evidence is
explicit, and model rationales never enter this section.

Compare highlights the shortest validated result across all available methods,
including an incomplete incumbent when it is shorter. Ties are disclosed; this is
the best observed route, not proof of optimality. The existing completed-first
recommendation helper remains unchanged for its other callers. Diagnostics and
legacy selection details are collapsed by default.

## Files changed in this phase

- `web/src/services/routeEvidence.ts` (new): shared evidence and savings rules.
- `web/src/components/RouteExplanation.tsx` (new): measured insights and map actions.
- `web/src/components/CompactResults.tsx`: compact outcome summary.
- `web/src/components/PlanningWorkspace.tsx`: explanation integration and summary visibility.
- `web/src/components/CompareScreen.tsx`: shortest-result selection and honest baseline comparisons.
- `web/src/workspace.css`: compact summary/explanation styling using existing colors.
- `web/tests/route-evidence.cjs` (new): ten evidence regressions.
- `web/tests/workflow.cjs`: registers tests; comparison fixture supplies explicit verified identity.
- `web/tests/workflow-browser.mjs`: contract-complete fixtures, summary and insight-focus checks.
- `web/tests/product-browser.mjs`: actual API summary checks and separate artifact path.
- `scripts/smoke_frontend_redesign.py`: separate Phase 4 smoke artifact path.
- `docs/product-outputs.md` (this file).

Existing engine/API changes and Phase 1–3 UI work were preserved. No solver,
baseline, strategy policy, API contract, research artifact, or secret was changed
in this phase. No live provider or OSRM call was made.

## Verification

From `web`:

```powershell
npm.cmd test
npm.cmd run test:browser
npm.cmd run build
```

From repository root:

```powershell
web/node_modules/.bin/tsc.cmd --noEmit --incremental false -p web/tsconfig.json
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_adaptive_controller.py tests/unit/test_hybrid_search.py tests/unit/test_strategy_evolution.py tests/unit/test_strategy_api.py tests/unit/test_phase7.py -q
python -B scripts/smoke_frontend_redesign.py
git diff --check
```

AST parsing used the root command documented in
`docs/adaptive-strategy-controller.md` (all project `.py` files, excluding installed
environments/build directories, UTF-8 BOM-aware).

Results: 78 frontend tests; 20 mocked-API browser checks; 181 focused backend tests (one existing Starlette/httpx
deprecation warning); 332 Python files parsed; standalone TypeScript and production
build passed. The local real-backend smoke passed 38 browser checks and 13
independent matrix-cost/coverage audits with explicit offline service fixtures.
Artifacts are under `runs/product-outputs/`. Responsive smoke covers 1440, 1024,
768 and 390 pixel widths. The full offline backend suite was not repeated for
these frontend-only production changes; its preceding Phase 3 result was 960
passed, not a new Phase 4 run.

The final summary-scroll adjustment was checked by the 20-check browser rerun
and production rebuild after the real-backend smoke. Final diff checks passed.

An initial new test exposed a standalone event being described as a no-gain
pass without a preceding retained distance; production now requires that preceding
measurement. The first browser attempt exposed test-state interference: the new
insight check selected Driver 1 before the existing toggle check. The fixture now
restores the all-driver view between checks, retaining both assertions.
