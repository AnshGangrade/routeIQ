# Phase 5: reproducible fleet benchmarks

Historical Phase 5 record. Phase 5B supersedes its paired-comparison policy with
completed-only pairs and adds checkpointed full-split execution; see
[fleet-benchmark-phase5b.md](fleet-benchmark-phase5b.md). The original measurements
below remain preserved and are not relabelled as completed results.

This is an offline measurement layer around the existing FleetProblem, trusted
constructors, historical fleet baselines, and hybrid solver. It changes no
optimization operator, search policy, API, evolution code, or frontend.

## Run and reproduce

From `D:\routeIQ`, the full **development** suite is one command:

```powershell
python -B scripts/run_fleet_benchmark.py --profile full --output runs/fleet-development
```

The default `--profile smoke` is a fixed 12-case coverage check. `full` is 360
cases per split and can take substantially longer. Each output directory must
be new. Exit 0 means reports were written without evaluation failures, **not**
that every method completed its budget; exit 1 means evaluation failures were
recorded; invalid CLI/protocol configuration exits 2.

The output contains `results.json`, `results.csv`, and `report.md`. JSON stores
the exact FleetProblem snapshot (including the matrix), both fingerprints,
routes, independent costs, statuses, configuration, source hash, and software
versions. CSV contains one method/case row, with nested records encoded as JSON.
Markdown contains aggregate and all per-instance results. No environment files
or external services are used. Timing is machine-dependent and is not expected
to reproduce bit-for-bit.

Rerun one case with identical budgets and search seed:

```powershell
python -B scripts/run_fleet_benchmark.py --case development-n20-k1-uniform-symmetric-r0 --operations 1000000 --seconds 60 --search-seed 0 --output runs/fleet-single
```

For strict reproduction, freeze a protocol before evaluation and use it for
development, validation, and the final held-out run:

```powershell
python -B scripts/run_fleet_benchmark.py --freeze-protocol runs/fleet-protocol.json --operations 1000000 --seconds 60 --search-seed 0
python -B scripts/run_fleet_benchmark.py --protocol runs/fleet-protocol.json --profile full --split validation --output runs/fleet-validation
python -B scripts/run_fleet_benchmark.py --protocol runs/fleet-protocol.json --profile full --split heldout --acknowledge-heldout --output runs/fleet-heldout
```

Protocol files are created exclusively; parameter overrides are rejected when
loading one. Catalog, configuration, source, Python/dependency/platform, and git
metadata are checked against the frozen record. Held-out CLI runs require both a
protocol and explicit acknowledgement; case IDs cannot cross the requested
split. Saved reports never overwrite old experiments. An individual held-out
case can be reproduced with the same protocol, acknowledgement, and `--case`.

Use only development data for implementation/tuning, validation for selection,
and freeze the final protocol **before** opening held-out results. Do not use
held-out reports to choose configurations. These are accidental-misuse guards,
not an access-control service: a human can still create a new protocol or read
the generator. Repeated final evaluation must be disclosed. This local capstone
cannot cryptographically prove that a researcher never inspected test outcomes.
The lower-level Python generator and runner are testable functions, not an
access-control boundary; use the registered CLI workflow for research runs.

## Dataset v1

`engine/evaluation/fleet_dataset.py` defines a fixed Cartesian product per split:

- 20, 50, 100, 200 delivery stops (depot is additional).
- 1, 2, 3, 5, 10 drivers, with FleetProblem's floor/ceil workload bounds.
- Uniform, four-cluster, and mixed-density distributions.
- Symmetric Euclidean matrices and synthetic directed matrices.
- Three independent instance replicates per combination: 360 cases/split,
  1,080 across development, validation, and held-out.

The depot is `(50, 50)`. Uniform coordinates cover `[0,100]^2`. Cluster centers
are sampled in `[15,85]^2`; cluster points have Gaussian standard deviation 6,
clipped into the square. Mixed density uses 70% clustered and 30% uniform stops.
Each seed is a 64-bit prefix of SHA-256 over the dataset version and complete
case specification, **including split**. Tests verify all 1,080 seeds are distinct.
Search seed is separate (default **0**); it never changes the instance matrix.

Directed costs multiply each Euclidean arc by an independently seeded factor in
`[1,2)`. They are finite, nonnegative, asymmetric synthetic stress cases, **not
OSRM roads**, and need not satisfy triangle inequality. Coordinates remain
available for the historical assignment comparator; their costs always come
from the canonical matrix. All benchmark distances are **map units**. Sweep is
inapplicable to directed cases and is explicitly recorded as such.

Smoke's 12 predetermined cases span all sizes, driver counts, distributions and
directions, but are unbalanced and do not contain three replicates of every
condition. Use full for stratified research conclusions. Seeds/case IDs and
generated matrix fingerprints allow inspection and replay independently of
execution order. Archive source plus result snapshots for long-term reproduction;
source hashing detects generator changes but does not replace source archival.

## Compared methods and fairness

`engine/evaluation/fleet_benchmark.py` creates **one FleetProblem object per
case**, then hands it to every method. No adapter rebuilds Euclidean distances.
Every returned fleet is independently validated and its costs recomputed. A
before/after problem fingerprint detects mutation. Solver-supplied costs are
never treated as authoritative.

| Name | Existing implementation / behavior |
|---|---|
| historical_nn | Historical angular round-robin assignment, original NN |
| historical_nn_2opt | Same assignment and NN, historical directed-safe 2-Opt, max 1000 iterations/driver |
| cheapest_insertion | Existing joint matrix insertion constructor |
| sweep | Existing contiguous angular assignment and matrix NN; symmetric Euclidean only |
| constructor_portfolio | Existing hybrid constructor portfolio, operators disabled, ILS disabled |
| hybrid_vnd | Existing portfolio and VND, ILS disabled |
| hybrid_ils | Same portfolio/VND plus bounded ILS |

The portfolio includes the existing ordered feasible seed fallback, legacy NN,
legacy 2-Opt, bounded alternative NN starts, insertion and applicable sweep.
It receives one shared allocation, **not** a full allocation per constructor.
Truncated portfolios list unstarted/interrupted constructors. Completion of a
baseline is tested against its unchanged unbudgeted implementation. Interrupted
baselines are labelled incomplete and never called historical completed results.

Default common limits are 1,000,000 charged operations and a **cooperative**
60-second deadline per method/case. The default SearchConfig is NN attempts 4,
operator calls 1000, moves per operator 10000, 2-Opt iterations per call 1,
ILS iterations 5, perturbation moves 2, diversification limit 3. Full config is
recorded. ILS iteration exhaustion is reported as incomplete, consistent with
the solver's existing lifecycle; it may still return a valid good incumbent.
An ILS-labelled run can exhaust its budget before any ILS iterations occur;
construction status and search counters must be inspected before interpreting it.

Work units are heterogeneous distance comparisons, insertion/move checks,
constructor/operator calls and perturbations, not interchangeable CPU cycles.
Historical NN/2-Opt use the existing optional budget hooks. Bootstrap assembly,
fingerprinting, assignment, independent validation and result bookkeeping are
not charged operations; measured end-to-end method runtime includes them.
Budgets are soft: an atomic operation/validation can finish after the deadline.
No hard process timeout or equal-CPU guarantee is claimed. Constructor checks,
operator calls, accepted proposals and runtime are reported separately.
Historical 2-Opt does not expose accepted reversal counts: these are **null**,
not fabricated zero. Hybrid accepted moves count VND proposals; internal 2-Opt
reversals are not individually exposed. No new counters were added to solver core.
`constructor_work` preserves the wrapper's raw counters; its default zero for
accepted moves does not measure internal reversals. The top-level null is the
authoritative availability indicator for historical 2-Opt.

Optional `--random-trials 3` adds `random_config_search`. The existing immutable
SearchConfig supports this without solver changes. A local RNG with the fixed
search seed samples operator order, NN attempts 1..4, perturbation moves 1..3,
and ILS iterations 0..the configured cap. Each trial receives
`floor(total_operations/trials)`; unused allocations are not transferred. All
trials share the remaining wall-clock allowance. Configurations, child work,
statuses and costs are recorded; aggregate work cannot exceed the method's
allocation. This is a best-of-random-configurations **per-instance search
control**, not training, LLM evolution, or evidence of generalization. It makes
the same fixed draws on every case; no held-out feedback changes them.

## Metrics and statistical interpretation

`engine/evaluation/fleet_reporting.py` pairs methods on the **same case**, with
one fixed search seed and independently generated instance seeds. Positive
improvement is `100 * (baseline - candidate) / baseline`. W/T/L uses distance
comparisons with absolute and relative tolerances both `1e-9`; percentages
retain their unrounded values. Zero vs zero gives 0%; positive vs zero has no
finite percentage and is counted as a loss plus an undefined-percentage pair.
The worst percentage regression is undefined if such a loss exists; the worst
finite regression and absolute cost regression are retained separately.

The best observed distance is the shortest **validated, nonfailed incumbent**
among measured methods, including incomplete incumbents. It is never called a
proven optimum. Gaps are `100 * (distance - best_observed) / best_observed`, with
the analogous zero rule. Every per-case result remains inspectable.

Paired means/medians, sample SD, W/T/L, worst regressions, valid/unavailable and
complete/incomplete pair counts are reported. JSON additionally separates
complete-only paired percentages. Failed evaluations cannot contribute an
improvement even if they returned a feasible plan. Incomplete valid incumbents
can contribute **budgeted quality** comparisons, explicitly counted as
incomplete, not silently promoted to successful runs. Missing/inapplicable/
failed pairs are counted, never imputed. Zero-reference undefined percentages
are excluded only from finite percentage statistics and counted separately.

Mean 95% intervals are fixed-seed percentile bootstrap intervals using 1,000
resamples of paired instances (no interval for fewer than two observations).
They are descriptive, not a multiple-comparison significance test or a claim
about all routing problems. Inspect per-size/distribution/direction case rows
before drawing conclusions from pooled means. Runtime is reported separately
from quality; no speedup claim follows from operation counts alone. Methods run
sequentially in fixed order, without dedicated hardware isolation, randomized
order or repeated timing trials. These are runtime observations, not a controlled
speedup study. Dataset generation and report serialization are outside per-method
timings. An interrupted CLI process does not yet checkpoint partially written
suite reports; individual deterministic cases can be rerun.

Method rates use all applicable attempted runs as denominators. Reports separate
deadline, budget exhaustion, invalid returned fleet, evaluation failure, and
absence of a feasible result. An interrupted constructor with no complete plan
is not falsely counted as an invalid returned fleet. Exceptions store type only;
no arbitrary provider text, traceback, credentials or environment is serialized.

## Verification and measured run

Only development performance measurements are used in this phase; held-out
guard unit tests exercise a zero-budget invocation, not a tuning experiment.

Commands from repository root:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_fleet_benchmark.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_fleet_benchmark.py tests/unit/test_fleet_problem.py tests/unit/test_trusted_routing.py tests/unit/test_hybrid_search.py tests/unit/test_baselines.py tests/unit/test_routing.py tests/unit/test_incumbent.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/fleet-benchmark-offline.xml -q
python -B scripts/smoke_phase3.py
python -B scripts/run_fleet_benchmark.py --freeze-protocol runs/fleet-phase5-protocol.json --operations 2000000 --seconds 60 --search-seed 0 --random-trials 3
python -B scripts/run_fleet_benchmark.py --protocol runs/fleet-phase5-protocol.json --profile smoke --split development --output runs/fleet-phase5-development
python -B scripts/run_fleet_benchmark.py --protocol runs/fleet-phase5-protocol.json --case development-n20-k1-uniform-symmetric-r0 --split development --output runs/fleet-phase5-rerun
```

AST (generated run data and environments excluded):

```powershell
@'
import ast
from pathlib import Path
excluded={'.git','venv','.venv','env','ENV','node_modules','__pycache__','dist','build','runs'}
files=sorted(p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts))
for path in files: ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path))
print(f'AST: {len(files)} passed, 0 failed')
'@ | python -B -
```

From `D:\routeIQ\web`:

```powershell
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
```

Verified: **58 new benchmark tests passed**. Final combined regression run:
**423 passed** (benchmark, contract, trusted operators, hybrid, historical
baseline/routing and incumbent regressions). The earlier combined run also
passed all 418 tests present at that point. Full offline suite:
**797 passed, 1 deliberately deselected, 0 failures, 304.41 seconds**.
The sole deselection reads `.env.example`; live/manual network tests are outside
the offline suite. No tests were weakened/deleted. The existing Starlette/httpx
deprecation warning remains. Later reporting-counter assertions were rechecked
in the final 58-test focused run and 423-test combined run.

**108 Python files parsed**, TypeScript **exit 0**, actual local Vite/Uvicorn
smoke **11 passed, 0 failed**, with server cleanup. No API/frontend changes were
needed; these additional checks confirm compatibility.

The first new-test run found one Windows CSV CRLF bug (52 passed, 1 failed);
the writer was corrected. Sandbox retries then encountered Windows ACL errors
accessing pytest's own temporary directories, including a repository-local
`--basetemp=runs/pytest-phase5-focused`. The successful pytest runs used approved
execution outside that filesystem sandbox with the same offline guard, blocking
dotenv and real HTTP. No security or solver code was relaxed to pass tests.

### Actual development coverage results

Artifacts: `runs/fleet-phase5-development/results.json`, `results.csv`,
`report.md`; frozen settings in `runs/fleet-phase5-protocol.json`. This run used
2,000,000 operations and 60 seconds per method, search seed 0, and the optional
three-trial random control. There are **12 instances / 96 method-case records**:
**59 completed, 31 incomplete, 6 inapplicable, 0 failed**. All **90 applicable**
results are independently feasible. Sweep is inapplicable on six directed cases.
This is the fixed smoke coverage profile, not a full factorial performance study.

Budgeted incumbent quality (all paired cases included, with incomplete search
status retained; positive means shorter):

| Comparison | Pairs | Mean improvement % | Median % | W/T/L | Worst regression % |
|---|---:|---:|---:|---|---:|
| VND vs historical NN | 12 | 39.6562 | 42.3667 | 12/0/0 | 0 |
| VND vs historical NN+2-Opt | 12 | 31.4684 | 32.8979 | 12/0/0 | 0 |
| VND vs constructor portfolio | 12 | 6.8349 | 4.4071 | 12/0/0 | 0 |
| VND+ILS vs historical NN+2-Opt | 12 | 31.7137 | 32.8979 | 12/0/0 | 0 |
| VND+ILS vs cheapest insertion | 12 | 8.9337 | 6.7402 | 12/0/0 | 0 |
| VND+ILS vs sweep | 6 | 15.4484 | 15.5337 | 6/0/0 | 0 |
| VND+ILS vs constructor portfolio | 12 | 7.2342 | 5.1013 | 12/0/0 | 0 |
| VND+ILS vs VND | 12 | 0.4144 | 0 | 2/10/0 | 0 |
| Random control vs constructor portfolio | 12 | 7.7522 | 6.7819 | 10/1/1 | 6.9018 |

The VND+ILS vs historical NN+2-Opt mean's descriptive bootstrap interval is
20.6050%..42.3654%; VND+ILS vs VND is 0%..1.1677%. These do not establish
universal improvement or statistical superiority of ILS. **Seven of twelve
ILS-labelled runs never reached an ILS iteration**; five performed five
iterations and hit the configured ILS limit. VND completed five cases, hit its
operator-call cap on two, and its operation cap on five. All twelve ILS-labelled
runs retain the solver's incomplete status. Complete-only summaries are in JSON.

Mean observed runtimes in seconds: historical NN **0.0288**, NN+2-Opt **2.3605**,
insertion **0.2910**, applicable sweep **0.0239**, portfolio **2.6480**, VND
**16.0320**, VND+ILS **16.2207**, random control **19.8024**. Work/call/accepted
counts are included for every run. The random control reached its cooperative
deadline on **1/12** cases (60.1176 seconds including overhead); other methods
had zero deadline terminations. Evaluation and invalid-fleet failure rates were
zero. Budget exhaustion rates were 7/12 for VND and 12/12 for ILS/random control.

Do not hide the random-control regression: on
`development-n200-k2-mixed_density-directed-r2` it was **108.2870 map units
(6.9018%) longer** than cheapest insertion / the constructor portfolio. Splitting
a fixed allocation across trials can leave constructors unfinished; a higher
aggregate mean on other cases does not erase that loss. All raw child trials
and their stop reasons remain in JSON.

The single-case CLI rerun reproduced the exact matrix, problem fingerprints,
routes, costs, statuses, and charged work for **all eight methods**, excluding
timing fields. Time-limited cases need not reproduce an identical stopping point.
The frozen protocol was reverified against the final implementation after this
run. Generated `runs/` artifacts follow the repository's existing ignore rules;
archive them explicitly for a research record.
The 360-case full development sweep, validation performance study, and locked
held-out performance study were **not run**. The suite definitions and guards
are tested; full research conclusions require those separately registered runs.

New files only: the three `engine/evaluation/fleet_*.py` modules,
`scripts/run_fleet_benchmark.py`, `tests/unit/test_fleet_benchmark.py`, and this
document. All prior modifications are preserved. This framework is a CLI/engine
facility; no API/UI wiring is added. Stop after Phase 5.
