# Phase 5B: benchmark completion and methodology audit

This phase preserves the Phase 5 framework, dataset, historical baselines,
constructors and hybrid solver. Only benchmark reporting, observational event
accounting, checkpoint execution and audit tests change. No optimization operator,
search decision, LLM integration or frontend is added. The original reports and
source snapshots remain in `runs/phase5b-source-before` and the Phase 5 run folders.

## Audit of the original 12-case development report

All 96 JSON/CSV row identities, statuses, distances, runtime and work measurements
agree. All method rows have the exact same problem and matrix fingerprints per
case. Feasible routes were independently recomputed using both the canonical
validator and a separate edge-sum/coverage/workload oracle. The fingerprints cover
objective, driver count, workload, coordinates, matrix and units; search seed is
separately checked. Historical source files have not changed in this phase.

The previously reported arithmetic is reproducible:

| Historical statement | Original all-incumbent mean | Completed-only eligible pairs | Completed-only mean |
|---|---:|---:|---:|
| VND vs historical NN+2-Opt | 31.4683658717% (12 instances) | 5 | 22.3522415715% |
| VND+ILS vs historical NN+2-Opt | 31.7136872367% (12 instances) | 0 | undefined |

The original report disclosed incomplete statuses and contained complete-only
statistics in JSON, but its primary paired table included valid incomplete
incumbents. That does **not** meet Phase 5B's stricter completed-only requirement.
The old percentages are retained as audited historical incumbent observations,
not relabelled as successful completed comparisons.

`fleet_reporting.py` now admits a quality pair only when both runs are completed,
feasible and nonfailed. Exclusions are explicit and disjoint, in this order:
missing method, failure, inapplicable, incomplete, no feasible result. W/T/L uses
all eligible pairs. Percentage mean/median/SD/CI use only eligible pairs with a
defined percentage (`percentage_pairs`); zero eligible pairs produces null, never
zero improvement. Completion conditioning can favor easier cases and is a stated
limitation, not evidence of performance on all 360 instances.

Zero vs zero is a tie and 0%. Positive vs exact zero is a loss with undefined
percentage, even below the ordinary absolute tie tolerance. Nonzero costs use
absolute/relative `1e-9` tolerance for W/T/L; unrounded percentages retain their
sign. A prior edge case could call a tiny positive cost a tolerance tie while
also recording an undefined zero-reference loss; it is now tested and corrected.

## Why the original VND improvement is large

Independent decomposition against the *same historical NN+2-Opt denominator*:

- Best construction accounts for **26.7318883841 percentage points**.
- Subsequent VND accounts for **4.7364774877 percentage points**.
- Their sum is the original **31.4683658717%** observation.

The constructed portfolio route equals the hybrid's recorded initial distance on
all 12 cases. Portfolio construction alone averages **0.1311%** lower distance
on the three single-driver instances and **35.5988%** on nine multi-driver ones.
Driver partitions differ from historical assignment on **all nine** multi-driver
cases, after ignoring driver-slot permutations. Winning constructor counts:
cheapest insertion 6, bounded NN starts 3, contiguous sweep 1, legacy 2-Opt 2.

Historical `engine/routing/assignment.py` sorts angles then assigns round-robin;
historical 2-Opt only reorders within each assigned route. The new constructors
may change which driver serves which stop. This explains why large gains are
plausible without indicating an incorrect distance formula. Assignment and route
ordering change together in these constructors; this is measured trajectory
accounting and subgroup evidence, **not** a randomized causal ablation separating
their individual contributions. Operator-event global-best decreases provide
additional trajectory evidence in new runs, not order-independent causal effects.

Maximum allocations were equal, actual computation was not: original historical
NN+2-Opt consumed **686,053** charged operations, the portfolio **3,919,816**, and
VND **12,636,891** (about 18.4 times the historical comparator). Runtime is
reported separately. These are heterogeneous work units, not equal CPU cycles;
the quality gains are not an equal-actual-work or speedup claim.

## Frozen experiment and execution policy

The full campaign retains every Phase 5 solver setting:

Frozen Phase 5B protocol fingerprint:
`32728d3d4f53660632c32cd90a99399ea661af7a6887d61617ad7fe3a6cd9781`.
Its solver settings were asserted equal to the original Phase 5 configuration;
the added worker setting is recorded explicitly.

- 2,000,000 charged operations and a 60-second cooperative deadline per method.
- Search seed 0, NN starts 4; operator-call limit 1000; 10,000 moves/operator.
- Directed-safe 2-Opt iterations/call 1; ILS iterations 5; perturbation moves 2;
  diversification limit 3; unchanged operator order.
- All seven required methods plus the three-trial random configuration control.
- All **360 cases per split**, unchanged seeds and matrices, with development,
  validation and held-out kept separate (1,080 instances total).

Execution is registered as a **new experiment**, not a continuation mixed into
the original serial timing sample: at most eight independent case processes on
the observed 16-logical-CPU host. Methods execute sequentially within a case.
Per-method budgets are not multiplied by worker count. Concurrent CPU contention
can change wall-clock stopping points and completion rates; runtime is not
directly comparable to the old serial observations. No hardware isolation or
equal-CPU-time guarantee is claimed. The same concurrency policy is frozen for
all three splits; no parameters change in response to results.

The full campaign runs development, then validation, then held-out. Protocol,
source and dataset are rechecked before every split. Its manifest commits to all
case IDs and method order before measurement. Each completed case has an exclusive
checkpoint with protocol fingerprint and content checksum. Resume independently
checks matrix/problem identity, methods, budgets, seed, feasibility and costs.
Missing checkpoints remain pending; worker/infrastructure crashes are not converted
to successful scores. Reports require complete split coverage. A full report is
not synthesized from partial batches.

The original frozen guard correctly rejects changed measurement source. Rather
than bypass it, a new protocol is created with the unchanged solver configuration
and explicit worker setting. The source fingerprint now also covers the campaign
and audit entry points. No guard checks are removed; altered protocol/config/source,
unacknowledged held-out execution and inconsistent resume manifests fail closed.
These are accidental-misuse guards, not protection against a researcher deliberately
reading held-out data outside the registered workflow.

The 63 engine/entry-point source files covered by the frozen source fingerprint
are archived in `runs/fleet-phase5b-frozen-source/`, together with the protocol.
The archive's computed source fingerprint was checked against the frozen record,
and the live repository was reverified before and after copying. No environment
files are included. This preserves the measured source even though the working
tree contains uncommitted changes from earlier phases.

## ILS accounting

New benchmark diagnostics observe the solver's existing immutable events; they
do not instrument or change the algorithm:

- Entered ILS means an actual perturbation event was executed.
- Attempted iterations preserve the original solver counter, which can include
  an interrupted final iteration.
- Completed iterations require `ils_acceptance`, closing perturbation, VND and
  acceptance/restart handling.
- Global-best updates are actual decreases in the retained best after ILS begins,
  not merely accepted moves or improvements over a worse local walk.
- Exhaustion before/during ILS and ILS charged work are recorded separately.

The unchanged solver reports `ils_iteration_limit` as incomplete. Therefore a
normal five-iteration ILS run is **not** promoted to completed for this audit.
Completed-only VND-vs-ILS quality estimates may have zero eligible pairs. In that
case no benefit is claimed. Additional runtime/work are retained as per-instance
resource accounting with both statuses, separately from successful quality pairs.

## Exact commands and artifacts

From `D:\routeIQ`:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_fleet_benchmark.py tests/unit/test_fleet_benchmark_audit.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/fleet-phase5b-offline-final.xml -q
python -B scripts/audit_fleet_benchmark.py --results runs/fleet-phase5-development/results.json --output runs/fleet-phase5b-original-audit --rewrite-report
python -B scripts/run_fleet_benchmark.py --freeze-protocol runs/fleet-phase5b-protocol.json --operations 2000000 --seconds 60 --search-seed 0 --random-trials 3 --workers 8
python -B scripts/run_fleet_campaign.py --protocol runs/fleet-phase5b-protocol.json --output runs/fleet-phase5b-full --acknowledge-heldout
python -B scripts/run_fleet_campaign.py --protocol runs/fleet-phase5b-protocol.json --output runs/fleet-phase5b-full --acknowledge-heldout --resume
```

Resume uses the same campaign command with `--resume`. Do not change protocol,
budgets, seeds, workers, or case definitions. Changed parameters require a separate
experiment directory and frozen protocol, never overwriting this one.

Separate audit/finalization commands (outputs are exclusive, never overwritten):

```powershell
python -B scripts/audit_fleet_benchmark.py --results runs/fleet-phase5b-full/development/report/results.json --output runs/fleet-phase5b-full/development/audit
python -B scripts/audit_fleet_benchmark.py --results runs/fleet-phase5b-full/validation/report/results.json --output runs/fleet-phase5b-full/validation/audit
python -B scripts/audit_fleet_benchmark.py --results runs/fleet-phase5b-full/heldout/report/results.json --output runs/fleet-phase5b-full/heldout/audit
python -B runs/fleet-phase5b-finalize.py
```

The finalizer independently checks every JSON/CSV field and every paired mean,
median, eligibility denominator and W/T/L count. It verifies live/archived source
fingerprints and preserved core hashes, then writes `final-audit/summary.json`,
`paired-comparisons.csv` and `report.md` under the full campaign directory.

AST verification:

```powershell
@'
import ast
from pathlib import Path
excluded={'.git','venv','.venv','env','ENV','node_modules','__pycache__','dist','build','runs'}
files=sorted(p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts))
for p in files: ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
p=Path('runs/fleet-phase5b-finalize.py')
ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
print('AST:',len(files),'project Python files passed; final-analysis artifact also passed')
'@ | python -B -
```

Example **optional** single-case rerun, into a new output directory:

```powershell
python -B scripts/run_fleet_benchmark.py --protocol runs/fleet-phase5b-protocol.json --split development --case development-n20-k1-uniform-symmetric-r0 --output runs/fleet-phase5b-single-rerun
```

A single-case rerun executes serially; its wall-clock measurements must not be
mixed into the eight-worker campaign. Fixed seeds do not make wall-clock deadline
cutoffs identical across host loads. Preserve the original checkpoint/report.

Each split has its own `manifest.json`, `cases/*.json`, and `report/results.json`,
`report/results.csv`, `report/report.md`. Runtime and charged-work distributions
include n, mean, median, SD, min, max and nearest-rank p95. Paired percentages have
fixed-seed 1,000-resample descriptive bootstrap mean intervals. Audit outputs add
independently checked JSON, attribution/resource CSVs and a Markdown summary.

Independent reproduction of the two **historical** percentages (all 12 original
feasible incumbents, deliberately not a new completed-only estimate):

```powershell
@'
import json, statistics
from pathlib import Path
b=json.loads(Path('runs/fleet-phase5-development/results.json').read_text())
for name in ('hybrid_vnd','hybrid_ils'):
    percentages=[]
    for case in b['cases']:
        rows={row['method']:row for row in case['results']}
        reference=rows['historical_nn_2opt']['total_distance']
        percentages.append(100*(reference-rows[name]['total_distance'])/reference)
    print(name, len(percentages), statistics.mean(percentages))
'@ | python -B -
```

No environment files, credentials, LLM calls or external services are used. The
existing environment-example-reading test remains explicitly deselected. No test
is deleted or relaxed; the former incomplete-pair assertion is strengthened to
the new completed-only contract. The Windows pytest temp-directory ACL limitation
requires approved execution outside the filesystem sandbox with the offline guard.

## Verification and campaign status

Focused benchmark/audit tests: **71 passed**. Final full offline suite:
**810 passed, 1 deliberately deselected, 0 failures**, 317.22 seconds. The existing
Starlette/httpx deprecation warning remains. An earlier full pass before the final
zero-distance regression also passed (809 tests). AST: **112 Python files parsed**.
Solver, construction, baseline and dataset source hashes match the pre-phase
snapshots. No frontend/API types change, so no frontend work is required.

The first campaign launch inside the filesystem sandbox failed with Windows
access denied creating worker IPC, before any cases ran. Its manifests were
preserved. Approved execution outside that sandbox resumed the **same protocol**
and manifests successfully. Logs: `runs/fleet-phase5b-campaign.log` and
`runs/fleet-phase5b-campaign-resume.log`. No guard, budget, seed, dataset, or solver
logic was changed to work around this host permission issue.

After a later interrupted session, process checks confirmed that the campaign
and its workers had exited. The same `--resume` command verified **271** existing
development checkpoints and scheduled the remaining **89**, then validation and
held-out. Its new log is `runs/fleet-phase5b-campaign-resume2.log`. No finished
checkpoint was rerun or selected by quality. Checkpoints are per-case: partial
work without a finished checkpoint was lost at interruption and is rerun from
the fixed case definition. Its unavailable method-level outcomes and wasted
runtime are not fabricated or included in retained-run statistics.

A second session interruption left all **360 development** cases and **259
validation** cases checkpointed. Process checks found no remaining campaign or
worker processes. The unchanged command resumed the remaining **101 validation**
cases and the held-out split; log: `runs/fleet-phase5b-campaign-resume3.log`.
The separate development audit independently verified all **2,880 method records**.

The next interruption left development and validation complete and **332/360
held-out** cases saved. Process checks again found no active campaign or worker
processes. `runs/fleet-phase5b-campaign-resume4.log` records verification of those
checkpoints and the unchanged resume command for the remaining **28** cases.

## Phase 5B files changed

Implementation and tests (historical baselines and solver code unchanged):

- `engine/evaluation/fleet_benchmark.py`
- `engine/evaluation/fleet_reporting.py`
- `engine/evaluation/fleet_experiment.py` (new)
- `scripts/run_fleet_benchmark.py`
- `scripts/run_fleet_campaign.py` (new)
- `scripts/audit_fleet_benchmark.py` (new)
- `tests/unit/test_fleet_benchmark.py`
- `tests/unit/test_fleet_benchmark_audit.py` (new)
- `docs/fleet-benchmark.md`
- `docs/fleet-benchmark-phase5b.md` (new)

Generated experimental artifacts are under `runs/fleet-phase5b-*`, including
the frozen source archive and the read-only final-analysis script
`runs/fleet-phase5b-finalize.py`. Existing repository ignore rules exclude `runs/`;
these results must be retained or archived separately from a Git commit.

### Verified development results (full 360 cases)

The completed report and independent audit contain **2,880 method records**:

| Method | Completed | Incomplete | Failed | Inapplicable |
|---|---:|---:|---:|---:|
| Historical NN | 360 | 0 | 0 | 0 |
| Historical NN+2-Opt | 351 | 9 | 0 | 0 |
| Cheapest insertion | 360 | 0 | 0 | 0 |
| Sweep | 180 | 0 | 0 | 180 |
| Constructor portfolio | 348 | 12 | 0 | 0 |
| Hybrid VND | 182 | 178 | 0 | 0 |
| Hybrid VND+ILS | 0 | 360 | 0 | 0 |
| Random configuration control | 0 | 360 | 0 | 0 |

VND vs historical NN+2-Opt: **182 eligible pairs**, 178 wins / 4 ties / 0 losses;
mean reduction **33.360696%**, median **38.044766%**, descriptive bootstrap mean
95% interval **[30.976185%, 35.701432%]**, worst paired regression **0%**. These
completed pairs exclude 178 cases and cannot establish improvement for all sizes
or all runs. Runtime median/p95: historical NN+2-Opt **0.089929 / 8.371370 s**;
VND **15.418450 / 60.126866 s**. Work median/p95: historical **3,776 / 231,831**;
VND **657,143 / 2,000,000** heterogeneous charged operations.

ILS entered **182/360** runs, attempted **863** iterations and completed **841**;
179 runs completed at least one iteration. **62** runs recorded a new global best
after ILS began (215 decreasing events). Limits were reached before ILS in 178
runs and during ILS in 182, including the normal configured iteration cap. There
are **zero completed VND/ILS pairs**, so there is no completed-pair estimate of
ILS benefit. Execution evidence from incomplete incumbents is not promoted to one.

### Verified validation results (full 360 cases)

The separate validation report and independent audit verify all **2,880 records**:
**1,779 completed**, **921 incomplete**, **0 failed**, **180 inapplicable**.
VND vs historical NN+2-Opt has **183 eligible pairs**, 180 wins / 3 ties / 0 losses;
mean **32.152323%**, median **35.937107%**, descriptive bootstrap mean 95% interval
**[29.679390%, 34.401707%]**, worst paired regression **0%**. The remaining 177
pairs are excluded, not assigned invented improvements.

ILS entered **182/360** runs, attempted **870** iterations and completed **848**;
176 runs completed at least one iteration, and 70 found a new global best after
ILS began (228 decreasing events). Limits were reached before ILS in 178 runs
and during ILS in 182. Completed VND/ILS comparison pairs: **0**.

### Verified held-out results (full 360 cases)

Held-out ran only after the frozen-protocol checks, with no tuning or source
changes based on any split's outcomes. Its report and independent audit verify
all **2,880 records**: **1,793 completed**, **907 incomplete**, **0 failed**,
**180 inapplicable**. VND vs historical NN+2-Opt has **180 eligible pairs**,
173 wins / 7 ties / 0 losses; mean **33.230892%**, median **38.231545%**,
descriptive bootstrap mean 95% interval **[30.742485%, 35.582687%]**,
worst paired regression **0%**. The other 180 pairs are excluded.

ILS entered **180/360** runs, attempted **862** iterations and completed **841**;
177 runs completed at least one iteration, and 55 found a new global best after
ILS began (201 decreasing events). Limits were reached before ILS in 180 runs
and during ILS in 180. Completed VND/ILS comparison pairs: **0**.

## Final campaign verification and interpretation

The campaign exited **0** after **1,080 cases**, with **0 evaluation failures**.
All three independent audits passed. The finalizer exited **0**, checking all
**8,640 JSON/CSV rows** (every field), all **168 ordered paired comparisons**
(56 per split), exact catalog/method coverage, summary consistency, live and
archived frozen source, and unchanged solver/baseline/dataset hashes.

| Split (360 cases each) | Completed method runs | Incomplete | Failed | Inapplicable |
|---|---:|---:|---:|---:|
| Development | 1,781 | 919 | 0 | 180 |
| Validation | 1,779 | 921 | 0 | 180 |
| Held-out | 1,793 | 907 | 0 | 180 |

These are method-run counts, not case counts. Inapplicable runs are the sweep
method on 180 directed cases per split. No missing case was extrapolated, omitted,
or replaced. Incomplete feasible incumbents are retained but not counted as
completed comparisons. All 360 ILS and all 360 random-control runs per split are
incomplete under the unchanged solver contract.

All applicable method rows have independently verified feasible incumbents:
**0 no-feasible-result rows**, **0 feasibility failures**, and **0 evaluation
failures** in every split. Feasible does not imply completed search.

Completion conditioning is substantial. Eligible VND/NN+2-Opt pairs by stop count
(there are 90 cases of each size in each split):

| Split | 20 stops | 50 stops | 100 stops | 200 stops |
|---|---:|---:|---:|---:|
| Development | 90 | 86 | 6 | 0 |
| Validation | 90 | 86 | 7 | 0 |
| Held-out | 90 | 85 | 5 | 0 |

Thus the primary completed-pair averages mostly describe small cases and **do not
establish a completed-search improvement at 200 stops**. Every larger incomplete
incumbent, runtime and work measurement is still available for inspection.

For ILS, the additional wall time and charged work below are **resource accounting
over all 360 matched attempts**, including incomplete runs. There are zero
completed VND/ILS pairs, so successful-pair quality and resource estimates are
undefined. These numbers do not establish an ILS benefit:

| Split | Mean additional seconds | Median additional seconds | Mean additional work | Median additional work |
|---|---:|---:|---:|---:|
| Development | 0.508400 | 0.245049 | 33,667.161111 | 3,796.5 |
| Validation | 0.826837 | 0.267066 | 17,469.216667 | 6,700.5 |
| Held-out | 0.887148 | 0.428830 | 30,059.133333 | 3,342.0 |

Some per-case deltas are negative because independently timed bounded runs can
stop at different points under concurrent host load. They are not evidence that
adding ILS inherently saves time or work. ILS termination reasons are separately
recorded; the configured iteration cap accounts for 160 development, 160
validation and 159 held-out runs, while the others hit operation, operator-call
or deadline limits. Reaching the iteration cap does not remove incomplete status.

Completed-pair trajectory decomposition, with the *same historical NN+2-Opt
denominator* at both stages:

| Split | Eligible pairs | Construction contribution (percentage points) | Subsequent VND contribution (points) |
|---|---:|---:|---:|
| Development | 182 | 28.523473 | 4.837223 |
| Validation | 183 | 27.163251 | 4.989072 |
| Held-out | 180 | 28.607723 | 4.623169 |

This supports the original finding that construction/assignment accounts for
most of the observed distance difference. It remains trajectory accounting,
not a controlled assignment-vs-ordering ablation or an equal-computation claim.

Final artifacts:

- `runs/fleet-phase5b-full/final-audit/report.md`: compact separate-split report.
- `runs/fleet-phase5b-full/final-audit/summary.json`: all denominators, descriptive
  intervals/dispersion, runtime/work distributions, terminations and ILS accounting.
- `runs/fleet-phase5b-full/final-audit/paired-comparisons.csv`: all 168 comparisons.
- Each split's `report/` contains the full JSON/CSV/Markdown per-instance results;
  its `audit/` contains independent checks and attribution/resource CSVs.

Remaining limitations: completed-only comparisons select a subset of cases;
incomplete ILS/random-control runs cannot support a completed-only superiority
claim; budgets use heterogeneous work units and cooperative wall-clock limits;
concurrent host load and interruption/restart timing affect cutoffs; uncheckpointed
partial work at interruptions is unavailable; directed matrices are synthetic,
not sampled real roads. Best observed is not a proven global optimum. Bootstrap
intervals are descriptive, without multiple-comparison significance claims.
No solver or budget was changed in response to validation or held-out results.

No additional implementation code changed after the final **71 focused tests**
and **810-test offline pass**. AST parsing was repeated at completion: **112
project Python files passed**, plus the standalone final-analysis artifact.
Frontend/API types are unaffected; frontend checks and local API smoke tests were
not rerun in this measurement-only phase. Phase 5B stops here.
