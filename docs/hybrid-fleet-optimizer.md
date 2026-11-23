# Optimization upgrade Phase 4: bounded hybrid fleet optimizer

Implemented the reusable engine solver only. Existing API routes, frontend,
LLM prompts, evolution policy and population management are unchanged. No ALNS,
new neighborhood operators, environment-file access, or live LLM/OSRM calls.

## Public interface

```python
from engine.routing.search import SearchConfig, solve_hybrid

result = solve_hybrid(
    problem,
    construction_strategy="portfolio",
    config=SearchConfig(ils_iterations=5, max_operator_calls=500),
    search_seed=0,
    operation_budget=100_000,
    time_limit_seconds=10.0,
    should_cancel=cancel_event.is_set,  # optional callable
)
plan = result.final_solution
```

`FleetProblem` remains immutable. The separate search seed is applied to a
validated copy and does not change problem identity. A missing explicit search
seed uses the problem's search seed, then zero. Global random state is untouched.

The frozen `HybridResult` contains initial/final `TrustedPlan` objects, initial
constructor reports, raw candidate events, improvement percentage, seed,
operator names/calls, accepted moves, ILS/diversification counts, work consumption
and category counts, elapsed time, termination reason, budget-exhaustion flag,
truncated-neighborhood count, status and sanitized error categories. Plans contain
routes, per-driver distances, total and longest distance, units through the
problem contract, and problem fingerprint. Reported distance always comes from
independent validation, including final output after early termination.

## Construction and selection

Before optional search, a deterministic ordered-stop seed is assembled using
feasible workload quotas and fully validated. This guarantees a usable incumbent
for a zero-work, zero-time, or already-cancelled request when the seed has a finite
objective. It is labelled `ordered_feasible_seed`, never NN or an evaluated
baseline. Invalid/nonfinite solutions fail closed rather than inventing a result.

The default portfolio then attempts, in order:

1. Legacy angular-round-robin Nearest Neighbor.
2. The existing 2-Opt baseline on those assignments, retaining its 1000-iteration
   default per driver and its historical result when not interrupted.
3. Bounded multi-start NN (four attempts by default).
4. Cheapest Insertion.
5. Contiguous Sweep when Euclidean coordinates are applicable.

A specific construction strategy selects that method plus the two legacy
comparators. Inapplicable coordinate-based methods are labelled `not_applicable`;
workload-incompatible legacy assignments remain explicit failures. Interrupted,
failed and unstarted attempts are distinguished from completed measurements.
Multi-start NN retains its best completed attempt if a later attempt stops.
Partial 2-Opt improvement of a complete fleet may be retained, with its constructor
report labelled interrupted. Incomplete route construction is never selected.

The best validated constructor is `initial_solution`. Ties with the fallback
prefer a measured legacy baseline; ties between those baselines keep NN. New
methods do not redefine historical baselines. Neither the final solution nor any
reported best-so-far value can exceed the best validated solution already seen.
Percentage improvement is `(initial_D - final_D) / initial_D * 100`, on the same
problem/matrix/objective; a zero/zero tie reports zero. It is not an improvement
against every unmeasured baseline or a held-out research metric.

## VND and ILS schedule

Distinct complete initial plans are ordered by distance and improved through
VND. The default neighborhood order is relocate, swap, Or-Opt-2, directed-safe
2-Opt, cross-route relocate, cross-route exchange. Each strict improvement becomes
the current walk state and restarts at relocate. Equal/worse proposals are not
accepted by VND. Every proposal is independently revalidated, even if its supplied
cost looks plausible. Invalid operator output stops search with an explicit
failure and the previously validated incumbent intact.

After portfolio VND, ILS starts from the global best. Each perturbation makes a
bounded number of seeded stop swaps (default two), within or between routes.
Swaps preserve stop counts and workload bounds; each intermediate fleet is
validated and can update the global best. An immediate undo is avoided when
another pair exists. These controlled perturbations may worsen the exploration
state; they do not replace a better global incumbent.

VND is rerun after perturbation. Improvements over the current walk are accepted.
A distinct equal/worse local result may be accepted at most three times by default
for diversification; otherwise the walk restarts from the global best. Default
ILS limit is eight iterations. All loops also share the global operation budget,
deadline and cancellation signal. The raw perturbation/local-search result and
the selected global-best distance are separate fields in the event trace.

## Work limits, cancellation and honest terminal states

`SearchBudget` charges one unit for each constructor/operator admission, NN
distance comparison (including alternative first-stop ranking), sweep angle-key
evaluation, insertion alternative, move delta, 2-Opt reversal proposal, or
perturbation swap. Categories are reported separately. A unit is not a CPU
instruction; a full-route 2-Opt proposal can be more expensive than an O(1) delta.
The counter never exceeds its admitted limit.

Default limits are 100000 operations, 10 seconds, 500 operator calls, 10000 moves
per neighborhood, one 2-Opt iteration per driver per call, eight ILS iterations,
two perturbation swaps and three diversifications. Host validation enforces finite
nonnegative time, 0..10000000 operations, at most 1000 operator calls, 100 ILS
iterations, eight swaps per perturbation, and the existing constructor/operator
caps. Zero operator-call/ILS limits are supported explicitly.

Cancellation/deadline checks occur inside NN comparisons, construction scans,
operator enumeration/delta scans and the existing 2-Opt reversal scan. If stopped
mid-scan, already validated improvements are retained. A cancellation racing with
operator admission also returns the incumbent. Cancellation callback failures are
reported as failures rather than completion.

Deadlines are **cooperative**, not process termination or hard real-time limits.
Mandatory route assembly, input validation/fingerprinting, final validation and
individual atomic candidate evaluations finish even if a deadline is crossed.
These bookkeeping costs are not charged as candidate operations; elapsed time
includes the canonical-copy/bootstrap/finalization work. Matrix fingerprinting is
quadratic in matrix dimension. No CPU, memory, or whole-job hard deadline is
claimed. Fixed seed/work-budget results are reproducible when the wall deadline
and asynchronous cancellation do not intervene; time-limited cutoffs can vary.

Termination reasons distinguish operation budget, deadline, cancellation,
operator-call cap, neighborhood scan cap, ILS iteration cap, operator/cancellation
failure, completed local search, and no possible perturbation. A cap-limited run
reports `stopped`, not completed optimization. Cancellation alone does not claim
a budget was exhausted. Constructor failures remain in reports/errors even if
another valid plan can be returned. Truncated neighborhoods do not establish a
local optimum. `accepted_moves` counts strict VND moves, with 2-Opt counted by
accepted driver proposals rather than its internal reversals; diversification
acceptances and raw perturbations are recorded separately.

## Verified examples and benchmark

On the fixed directed 8-stop fixture (Random(2), integer arcs 1..50, two drivers,
search seed zero), the full VND neighborhood set leaves distance **151** unchanged.
Five ILS iterations find **132**. Independent exhaustive enumeration of all
40320 ordered fleets gives optimum **120**. Thus this verifies escape and
non-regression, not global optimality.

Recorded benchmark: synthetic uniform instances, instance seed 42/search seed 0,
portfolio construction, 1000000 operations, 60-second cooperative deadline,
1000 operator calls and five ILS iterations. Distances are **map units**. The
zero-distance case is a deliberately labelled coincident-location control.

| Stops / drivers | Initial D | Final D | Improvement | Calls / accepted | Seconds | Work used | Termination / ILS iterations |
|---|---:|---:|---:|---:|---:|---:|---|
| 20 / 3 | 659.448436 | 608.528133 | 7.721650% | 421 / 129 | 0.642 | 39855 | ILS cap / 5 |
| 50 / 5 | 1013.362528 | 983.397262 | 2.957013% | 1000 / 281 | 7.586 | 395951 | Operator-call cap / 3 |
| 100 / 5 | 1315.227851 | 1203.003729 | 8.532675% | 566 / 183 | 17.321 | 1000000 | Operation budget / 0 |
| 20 / 3, zero control | 0 | 0 | 0% | 48 / 0 | 0.416 | 6527 | ILS cap / 5 |

The 100-stop run exhausted its budget during portfolio VND and did **not** reach
ILS. This limitation is reported rather than hidden. These are single-seed local
diagnostics, not a held-out study, multi-seed performance guarantee, road benchmark
or proof that every instance improves. Initial D is the best constructed result,
not merely the weakest baseline. Full routes, fingerprints, constructor statuses,
operator counts and timings are saved in `runs/hybrid-search-benchmark.json`.

## Verification

- New solver/budget tests: **57 passed, 0 failed** (final focused run).
- Earlier combined solver/contract/operator/baseline/routing/incumbent run:
  **361 passed**, before four additional solver tests were added; those additions
  are included in the final focused and full runs.
- Full offline suite: **739 passed, 0 failed, 1 deliberately deselected**,
  **273.76 seconds**. Report: `runs/hybrid-search-offline.xml`.
- AST: **103 Python files passed**. TypeScript: **exit 0**.
- Actual local Uvicorn/Vite smoke: **11 passed, 0 failed**, with clean shutdown.

The full suite includes Phase 2's 79 FleetProblem tests, Phase 3's 160 trusted
operator/construction tests, all earlier Phase 1–4 regression files, API tests
and the 57 new solver tests. Tests cover directed costs, exact coverage/workloads,
immutable matrices, seeds, budget/cancellation inside scans, deadline injection,
retained partial improvements, ties/zero cost, more drivers than stops, baseline
compatibility, invalid/forged candidates, and independent recomputation of every
reported plan. No test failed during this phase. The existing Starlette/httpx
TestClient deprecation warning remains.

From `D:\routeIQ`:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_hybrid_search.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_hybrid_search.py tests/unit/test_trusted_routing.py tests/unit/test_fleet_problem.py tests/unit/test_baselines.py tests/unit/test_routing.py tests/unit/test_incumbent.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/hybrid-search-offline.xml -q
python -B scripts/benchmark_hybrid.py --operations 1000000 --seconds 60 --output runs/hybrid-search-benchmark.json
python -B scripts/smoke_phase3.py
```

The existing environment-example test is deliberately excluded to honor the
no-environment-file constraint, not to hide a failure. Live/manual tests remain
outside the offline suite. The offline guard blocks dotenv and real HTTP.

From `D:\routeIQ\web` (API/frontend types are unchanged):

```powershell
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
```

AST from repository root:

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

## Files changed and remaining boundaries

Added: `engine/routing/budget.py`, `engine/routing/search.py`,
`tests/unit/test_hybrid_search.py`, `scripts/benchmark_hybrid.py`, this report.

Updated: `engine/routing/construction.py`, `engine/routing/operators/moves.py`,
`engine/baselines/nearest_neighbor.py`, `engine/baselines/two_opt.py`.
The baseline changes are optional checkpoint parameters and calls only; previous
directed-safe logic and default results are preserved. Construction/operator
updates share the host budget and retain completed work on interruption.

Generated verification artifacts: `runs/hybrid-search-benchmark.json` and
`runs/hybrid-search-offline.xml`. All unrelated working-tree changes remain.

The solver is callable through the engine; it is not yet exposed as a new API/UI
method or wired into research/LLM evolution. Existing backend smoke verifies
compatibility; solver behavior is verified separately by unit oracles and the
offline benchmark. Legacy comparators still require their applicable geometry
and assignment constraints. No global-optimality, universal-improvement, provider
availability, or hard real-time guarantee is claimed. Stop after this Phase 4.
