# Completed Route Plan and AI-guided Evolution workflow

Implementation audit, 27 November 2026. Work began on a clean `master` at
`57a120c`. No commit/push, secret-file access, historical run modification,
held-out evaluation, baseline redefinition or unrelated visual redesign was made.

## Reproduced cause

The previous Evolution UI allowed six broad initial strategies under 20,000
operations / 10 seconds per development case. Eight of twelve measured runs
(six strategies, two cases) exhausted the operation budget. Their routes were
feasible, but the configured search had not finished. The previous fitness and
recommendation logic still admitted these records. Mixed proposal generation
also used random/mutation/crossover paths and a random fallback after LLM failure.

The hybrid searched every distinct constructor result, including the ordered
bootstrap, rather than just refining its best construction. Application compounded
this larger schedule with a 100,000-operation / 10-second default. The API trusted
the saved eligibility flag, and the UI published completed and incomplete jobs alike.

Evidence is append-only under `runs/workflow-completion-20261127/`:
`reproduction.json` and `application-measurements.json`. With the same two-operator
strategy on ten cases, the smaller schedule completed 8/10 versus 4/10 for the old
schedule/defaults. Both 200-stop, single-driver cases still reached 30 seconds.
Some smaller schedules returned longer distances. These are diagnostic observations,
not a fair quality/runtime benchmark: budgets differ and some timing measurements
overlapped verification workloads. No superiority claim is supported.

## Implemented contract

- `completed_panel/v1` requires every expected case, unique case identities,
  feasibility, independent validation, completed status and a genuine completed
  termination. Missing, failed, cancelled, interrupted, truncated and resource-limited
  evaluations cannot supply recommendation fitness. Raw bounded distances remain
  diagnostic records; they are not fallback winners.
- Before application the API reconstructs the canonical development panel and
  checks its fingerprints, units, seeds, execution scope, budgets, route coverage,
  workload and matrix-derived costs. Saved summary flags alone are insufficient.
- New application routes are independently checked against the selected problem
  and matrix, with full cost/longest-route verification. A completed status with an
  incompatible termination is rejected. Incomplete strategy jobs return no published
  route, retain the prior completed cache/UI result and expose exact measurements
  in technical details. The frontend checks completion and identity again.
- `search_scope=best_construction` is an explicit smaller schedule in the existing
  solver. It keeps mandatory historical NN/2-Opt constructors and fully runs the
  configured local search on the best construction. Historical research keeps the
  default `all_constructions` schedule and unchanged operators/baselines.
- Strategy application defaults to `min(500000, max(100000, 20*n*n))` operations
  and `min(30, max(15, .15*n))` seconds. Explicit API limits, including zero,
  remain authoritative. The UI requests these host defaults when applying a strategy.

## Product Evolution protocol

`workflow=ai_product` requires Ollama and the LLM arm. The host freezes two 20-stop
development cases (uniform/symmetric, two drivers; clustered/directed, three drivers),
seed/search seed zero, two rounds, four total candidates, eight case evaluations,
100,000 operations / 20 seconds per case, 800,000 operations total and 180 seconds
overall. At most eight proposals and six reserved model attempts are allowed.
Unused retry reservations are deliberately not reclaimed; actual calls are recorded
separately. Requests use Qwen `qwen3:1.7b`, temperature .3, 2,048 output tokens,
20-second provider timeout and one retry.

Two deterministic seeds cover legacy NN+2-Opt and bounded NN starts with 2-Opt.
Subsequent candidates must be genuine LLM proposals: supported legacy/NN-start
construction, one or two neighborhoods, at least one beyond 2-Opt alone, no ILS,
at most two NN starts, and enough per-neighborhood scan allowance. The provider's
generation format restricts the existing schema to this product subset; the
unchanged strict `StrategyConfig` and host admission checks still validate it.
No proposal is silently rewritten or replaced by random/mutated code. Source,
rejection, latency and token evidence remain explicit. Seeds cannot become the
user-facing LLM winner. Duplicate proposals consume the bounded allowance.

Evolution presents Check Ollama, Run evolution, progress/cancel, one completed
strategy and Apply to current plan. Diagnostics/export are collapsed. Accepted LLM
counts mean accepted proposals; evaluated LLM counts require a complete successful
full panel. Research random/hand/offline APIs and historical artifacts remain.
Historical records lacking the new evidence contract are not automatically promoted
or rewritten. Software-frozen experiments retain their existing resume protections.

## Actual live Ollama smoke

Three separate development-only smoke attempts are preserved:

1. `live-1795775730341829400/report.json`: broad generation format produced three
   product-schedule rejections; terminal failure, no winner or application.
2. `live-1795792765117949700/report.json`: product format produced three duplicates
   of trusted seeds; terminal failure, no application.
3. `live-1795792826961909700/report.json`: generation format requests an additional
   supported neighborhood instead of suggesting the seed's schema default. Three
   real calls, one duplicate rejection, two accepted LLM candidates, both complete
   on both cases. Eight total case evaluations including seeds completed. Recorded
   provider usage: 7,678 input/output tokens, 5.303 seconds. Winner used bounded NN
   construction, 2-Opt and cross-route relocation; mean development distance
   445.574615 map units. Reapplication to a distinct 10-stop/two-driver plan completed
   with 420.416669 map units, 173 operations, `local_search_complete`.

This is a live functional smoke, not evidence that AI beats conventional methods.
One additional diagnostic model call is saved as `live-diagnostic-proposal.json`;
it is not included in the final run's usage. No mocked output was counted as live.

## Verification commands and evidence

Run from the repository root. Use fresh `--basetemp`/output paths when rerunning;
do not overwrite these evidence files.

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_completed_workflow.py tests/unit/test_phase7.py tests/unit/test_strategy_evolution.py tests/unit/test_strategy_api.py tests/unit/test_quality_contracts.py --basetemp=runs/workflow-completion-20261127/pytest-final-focused -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --basetemp=runs/workflow-completion-20261127/pytest-full-final --junitxml=runs/workflow-completion-20261127/backend-full-final.xml -q
npm.cmd --prefix web test
web/node_modules/.bin/tsc.cmd --noEmit --incremental false -p web/tsconfig.json
npm.cmd --prefix web run build
npm.cmd --prefix web run test:browser
python -B scripts/smoke_completed_workflow.py
python -B scripts/smoke_ai_product.py
git diff --check
```

The last smoke command intentionally invokes real loopback Ollama; all automated
tests use mocks or prohibit provider/network access. Offline selection excludes
manual/live-service tests and explicitly deselects one foundation test that reads
an environment template. No tests were deleted or relaxed to accept incomplete work.
Older lifecycle/application fixtures now contain genuine completed evaluation evidence;
small-budget failure coverage remains explicit.

AST verification parsed every Git-visible project Python path (including untracked
source) returned by `rg --files -g '*.py' -g '!.env*'`:

```powershell
@'
import ast, subprocess
from pathlib import Path
paths=subprocess.check_output(['rg','--files','-g','*.py','-g','!.env*'],text=True).splitlines()
for name in paths:
    ast.parse(Path(name).read_text(encoding='utf-8-sig'),filename=name)
print(len(paths))
'@ | python -B -
```

Results: AST 151 passed; frontend 84 passed, zero failed/skipped; TypeScript passed;
production build passed (103 modules). Focused backend intermediate verification:
137 passed. Real API/solver browser smoke: eight checks plus six independently
audited route results passed, including applying to two instances, zero-budget
retention and terminal cancellation. Final full offline backend suite: **1,045
passed, zero failed, one explicitly deselected, one deprecation warning**, in
360.28 seconds (`backend-full-final.txt` / `.xml`). This includes the final new
publication-tampering and bounded-proposal tests. Existing frontend browser suite:
**21 passed, zero failed** (`frontend-existing-browser-final.txt`). Both browser
suites use explicitly mocked providers, separate from the three real Ollama runs.

Screenshots from the real-API mocked-provider browser run:
`browser-1795792911124298200/01-completed-strategy.png`,
`02-applied-route.png`, `03-incomplete-retains-route.png` beneath the evidence root.

Earlier failures remain recorded: restricted Windows execution encountered ACL/spawn
errors; approved subprocess execution with fresh test directories resolved these.
The first full backend run had 1,039 passes and two fixture failures (simultaneous
zero limits can terminate as deadline; an old fake winner had no panel evidence).
Focused reruns corrected both. A browser assertion also needed to wait for running
after pending; the progress heading itself deliberately covers both states.

## Limitations

- Completion is not optimality, nor a guarantee that every supported large plan
  finishes. The 200-stop/single-driver diagnostic still hit the hard deadline.
- Product evaluation covers only two development cases. No validation/held-out
  selection, benchmark, permanent learning or AI superiority is claimed.
- A smaller search can give a longer result than a broader search. Baseline
  constructors are retained, but a new completed strategy need not beat another
  previously completed strategy. Compare retains honest measured distances.
- Model failures, duplicates and out-of-profile proposals can still produce no
  winner; the UI explains the terminal issue and never substitutes random proposals.
- Cancellation is cooperative. An in-flight native Ollama request can wait for its
  bounded HTTP timeout; disconnecting does not kill the local Ollama model process.
- Road services were not called. Existing missing-geometry handling remains; tests
  use explicit offline geometry fixtures. Jobs/instances remain local, in-memory,
  single-worker state. Old UI automation for the historical redesign remains an
  archived harness; the current npm browser suite and new real-API smoke cover this workflow.

## Files changed

- API: `api/routers/optimization.py`, `api/routers/strategies.py`.
- Engine: `engine/routing/search.py`; `engine/strategies/evaluation.py`,
  `evolution.py`, `models.py`, `provider.py`, new `product.py`.
- UI: `web/src/App.tsx`; `components/OptimizationControls.tsx`,
  `components/StrategyLab.tsx`; `services/experiments.ts`, `services/product.ts`,
  `services/workflow.ts`; `types/api.ts` (paths beneath `web/src/`).
- Backend tests: new `tests/unit/test_completed_workflow.py`;
  `test_phase7.py`, `test_quality_contracts.py`, `test_strategy_api.py`,
  `test_strategy_evolution.py` beneath `tests/unit/`.
- Frontend tests: `web/tests/experiments.cjs`, `product.cjs`, `workflow.cjs`,
  `workflow-browser.mjs`, new `completed-workflow-browser.mjs`.
- Smoke scripts: new `scripts/smoke_completed_workflow.py`, `scripts/smoke_ai_product.py`.
- Documentation: `README.md`, this report. New append-only verification artifacts
  are under the ignored evidence directory; existing research files are untouched.
