# Phase 6: declarative strategy evolution

This is an isolated research engine and API. It does not replace the legacy
`/api/evolution` code-generating workflow or alter historical baselines, trusted
operators, the hybrid solver, FleetProblem, or Phase 5B reporting/protocol guards.
The new path accepts JSON data only and never imports the legacy sandbox,
heuristic-code parser, or code-executing evaluation loop. No frontend changes.

## Architecture and actual solver capabilities

`engine/strategies/models.py` owns validated, versioned schemas; `provider.py`
owns bounded native Ollama requests and offline fixtures; `evaluation.py` calls
the unchanged trusted hybrid solver and independently validates the resulting
fleet; `evolution.py` owns populations, budgets, lineage, checkpoints and selection;
`experiment.py` owns three-arm comparisons and frozen final evaluation.
`protocol.py` extends source provenance without modifying the Phase 5B guard.
`api/routers/strategies.py` exposes isolated jobs; `scripts/run_strategy_evolution.py`
provides the offline-first research CLI.

The existing hybrid always includes its legacy NN/2-Opt comparators and an ordered
feasible fallback. `construction="portfolio"` attempts the five existing methods;
other construction selections include that method plus the legacy comparators.
`construction_alternatives` derives this exact list; it is not an arbitrary list
that an LLM can inject. There is no new routing operator or search algorithm.

The schema exposes only implemented scheduling semantics: restart-on-improvement
VND, best strict move within a bounded scan (the existing directed 2-Opt adapter
retains its own internal traversal), seeded stop-swap perturbations, and bounded
diversification acceptance. Alternate schedules, simulated annealing, new
perturbation types, arbitrary Python and unknown operators are rejected rather
than accepted as inert controls. Iteration/call/scan caps select work *within*
the host allocation; proposals cannot raise global operations, time, seeds,
constraints, objectives or dataset access.

## Strategy schema

`fleet-strategy/v1` configuration fields:

- `construction`: portfolio, legacy_2opt, nearest_neighbor_starts,
  cheapest_insertion, or contiguous_sweep.
- Ordered, unique trusted `operators`: relocate, swap, or_opt_2, two_opt,
  cross_relocate, cross_exchange. An empty order is construction-only VND.
- Fixed literal scheduling/improvement/perturbation/acceptance policies above.
- `nn_attempts` 1..16, `max_operator_calls` 0..1000,
  `max_moves_per_operator` 1..100000, `two_opt_iterations` 1..100,
  `ils_iterations` 0..100, `perturbation_moves` 1..8,
  `max_diversifications` 0..100.

Canonicalization removes irrelevant parameters: inactive ILS/2-Opt/multi-start
settings and disabled neighborhood caps do not create artificial novelty.
Configuration fingerprint = SHA-256 of normalized sorted-key compact JSON.
Operator order remains significant. There is no claim that all equivalent
strategies can be identified statically; measured route signatures expose
behavioral similarity on the development panel.

Each record has a run-unique host-generated ID, real parent IDs, generation,
validated configuration/fingerprint, bounded rationale, creation method,
protected-elite flag, evaluation history and fitness. A proposal contains only
`config` and `rationale`; lineage, IDs and measurements are never model-supplied.
The six records in `examples/strategy-population.json` are explicitly unevaluated.

## Evolution methodology

Initial populations combine host-authored seeds, deterministic variations and
seeded random configurations (four authored seeds then random fills in adaptive
arms). The first two authored strategies are protected. Parent selection is
size-three tournament selection minimizing mean development fleet distance,
with configuration fingerprints as deterministic tie-breakers.

Offspring alternate bounded LLM proposals, mutation and field-wise crossover.
Invalid/unavailable LLM responses schedule a separately counted random fallback;
duplicates consume proposal allowance and are rejected. Survivor selection keeps
protected seeds, best elites and the best remaining archived candidates. Retained
strategies supply actual parent configurations in subsequent generations. The
global best remains in the archive and cannot worsen. Tied identity changes do
not count as gains. The random arm does not use parent performance to generate
new configurations; the hand arm evaluates its fixed authored portfolio once.

Diagnostics include proposals/acceptance by source, rejected duplicates/invalid
responses, lineage, population membership/survival, unique configurations,
behavioral route signatures, generation fitness ranges/means, stagnation,
best-so-far and strict distance decreases attributable to each proposal source.
These are selection trajectories, not causal proof of an LLM advantage.

## Honest evaluation and fairness

All candidates within an experiment receive the same immutable development
FleetProblems, matrices, driver counts, workload constraints, objective, search
seed and per-evaluation operation/time limits. Every returned route is validated
independently. Fitness is the unweighted mean total fleet distance over the
entire registered development panel. Failures, missing cases or cancellation
make fitness ineligible; failed cases are never silently omitted from a mean.
Longest route, distance dispersion/worst case, runtime, work and status counts
are reported separately.

**New training policy:** complete-panel, feasible bounded incumbents may be ranked
even when optimization stopped at a limit. Incomplete remains explicitly labelled;
this does not change Phase 5B's completed-only policy. Control reports contain
both bounded-training and completed-only paired estimates with their separate
denominators, per-case values and zero/tie handling from the benchmark utilities.
Development selection estimates are biased and not validation/test evidence.

Fitness uses the actual independent distance of the hybrid's retained incumbent.
No additional baseline clipping or synthetic improvement score is applied.
Raw candidate-event distances/metadata, retained-best trace and selected distance
remain separate. The underlying hybrid already preserves a global incumbent
including mandatory baseline constructors; this framework does not pretend to
measure an unguarded optimizer that the existing solver does not expose.

The comparison command gives all three arms the same population/evaluation/work
and wall-clock caps and the same panel. It reports actual and reserved usage,
generation/evaluation/total time, provider calls and token counts where available.
The fixed hand portfolio leaves unused allocation; equal caps are **not** equal
actual work. Live inference FLOPs, pricing and hardware utilization are unavailable;
monetary cost is null, not zero. Provider latency consumes the arm's wall allowance.
Offline fixtures establish plumbing only. No LLM superiority can be inferred
from this demo, and no fully hardware-matched comparison is claimed.

## Limits, cancellation and durable resume

Each evaluation reserves its worst-case operation allocation and panel slots
before executing. No later candidate receives a reduced leftover allocation.
Cancellation is checked during proposals, between cases and inside the existing
solver scans. HTTP calls have request timeouts, bounded retries and streamed
response byte limits. Cancellation during a blocked HTTP read can wait for its
configured timeout; hard process termination or security isolation is not claimed.
Trusted numerical code, fingerprinting, validation and checkpoint I/O have
cooperative rather than hard real-time limits.

Checkpoints contain checksummed JSON, RNG state, population/archive, queued
offspring, reservations, measurements and software/provider/panel configuration.
Writes use flush/fsync and same-directory atomic replacement. OS file locks
reject concurrent execution/resume and release on process death. Resume rejects
changed source/configuration/fixtures, revalidates route costs and recomputes
fitness. Candidate-boundary cancellation/resume reproduces deterministic search
when deadlines do not intervene. Live model outputs are not deterministic.

A crash during a reserved evaluation or request consumes the reserved allowance;
missing measurements are marked unavailable, never rerun as though free. Lost
in-flight time is conservatively charged at its reserved cap. Reported actual
work is a measured lower bound when work counters are unavailable. An interrupted
generation remains visible through its queue and candidate records; generation
summaries are emitted after that generation finishes. Resume after a consumed
budget does not grant a new budget.

## Provider and data isolation

Native Ollama `/api/chat` uses explicit model, loopback endpoint, temperature,
timeout, retries, output-token and response-byte limits. This is compatible with
a local Ollama server without requiring a dummy API key. It does not modify the
existing OpenAI-compatible client. Remote authenticated providers are deliberately
not exposed by this local API. Proxy environment discovery and redirects are off.
No environment files are loaded; response bodies/exception messages are not logged.

Strict JSON parsing rejects code fences, duplicate keys, nonfinite numbers,
unknown fields, unsupported settings and oversize responses. Prompts contain
schema, real parent configurations, development fitness/failure summaries and
diversity diagnostics only. Evolution does not read previous benchmark artifacts
or run validation/held-out evaluation. Automatic validation-set selection is
deliberately absent; it cannot silently become repeated optimization feedback.

Freezing requires a terminal, fully measured eligible winner, matching result and
checkpoint checksums, and the measured software. The frozen artifact records the
strategy, configuration, source/software and locked held-out catalog. Final
evaluation requires explicit acknowledgement and writes a single-use registry
entry keyed by the frozen fingerprint, independent of output/artifact paths.
A crash consumes that authorization. Intentional registry deletion, source/data
modification, or creation of new experiments by a researcher is outside this
accidental-misuse guard. No held-out measurements were run for the Phase 6 demo.
The final command evaluates all 360 locked cases with the frozen **per-case**
operation/time caps. Development population/evaluation-count/total-operation caps
govern evolution, not this separate full test sweep: final work is bounded by
360 times the per-case allocation, plus cooperative validation/reporting overhead.
For the example this is at most 7,200,000 charged solver operations and 3,600
allocated solver seconds, not the development run's 720,000/180 limits.

Adding Phase 6 engine files necessarily changes the live source hash. Existing
Phase 5B protocols therefore reject the new tree, exactly as designed. Their
archived source and reports remain unchanged; replay Phase 5B in its archived
environment. No source guard was loosened to accept the new implementation.

## API and commands

New prefix: `/api/strategy-experiments`.

| Method/path | Purpose |
|---|---|
| POST prefix | Start with `config`, `arm`, `mode`, optional `provider` |
| GET `/{job_id}` | Status, generation, winner ID and resource counters |
| GET `/{job_id}/history` | Finished generation diagnostics |
| GET `/{job_id}/strategies/{strategy_id}` | Record scoped to this job |
| GET `/{job_id}/export` | Complete machine-readable state |
| POST `/{job_id}/cancel` | Signal only this job |
| POST `/{job_id}/resume` | Resume the same registered checkpoint/limits |

Jobs run in background worker threads, preserving responsive status/cancel
endpoints. API admission: at most two active/20 retained jobs in the process,
12 cases, 16 population slots, 128 evaluation slots, 200 proposals, one million
operations/evaluation, 128 million allocated operations and 1800 seconds/run.
Disk checkpoints survive restart; registries/admission controls are process-local.
Use one API worker. Cross-process run locks protect an individual checkpoint,
not a global multi-worker capacity limit. Disk retention remains manual.

From the repository root (fresh output directories):

```powershell
python -B scripts/run_strategy_evolution.py compare --config examples/strategy-evolution-offline.json --output runs/phase6-offline-demo
python -B scripts/run_strategy_evolution.py run --arm llm --mode offline --config examples/strategy-evolution-offline.json --output runs/phase6-single
python -B scripts/run_strategy_evolution.py run --arm llm --mode offline --config examples/strategy-evolution-offline.json --output runs/phase6-single --resume
```

Separate final evaluation commands, **not part of evolution or the offline demo**:

```powershell
python -B scripts/run_strategy_evolution.py freeze --input runs/phase6-offline-demo/llm --output runs/phase6-frozen-strategy.json
python -B scripts/run_strategy_evolution.py heldout --input runs/phase6-frozen-strategy.json --output runs/phase6-final-heldout --acknowledge-heldout
```

Live Ollama is opt-in (`--mode ollama --model ... --endpoint ... --temperature ...
--timeout ... --retries ... --max-tokens ... --max-response-bytes ...`). Tests use
only offline proposals or `httpx.MockTransport`, including simulated timeouts.
CLI exit 0 means artifacts written, not proof that search converged; inspect
terminal status and incomplete counts. Failed experiments return 1; invalid
configuration/protocol/output returns 2.

## Verification commands

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_strategy_evolution.py tests/unit/test_strategy_api.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_fleet_problem.py tests/unit/test_trusted_routing.py tests/unit/test_hybrid_search.py tests/unit/test_fleet_benchmark.py tests/unit/test_fleet_benchmark_audit.py tests/unit/test_baselines.py tests/unit/test_routing.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/phase6-offline-final.xml -q
python -B scripts/smoke_phase3.py
```

The one environment-example-reading test is explicitly deselected. The offline
guard forbids external HTTP and dotenv access. Frontend types are unchanged;
optional TypeScript verification from `web`: `node_modules/.bin/tsc.cmd --noEmit
--incremental false`. Final measured verification results are recorded below
after the runs finish.

## Measured offline demo

`runs/phase6-offline-demo` contains JSON/CSV comparisons, a human-readable report
and separate complete arm records/checkpoints. Two fixed development problems
were used (20 stops, 2-driver symmetric uniform and 3-driver directed clustered),
proposal seed 2026, search seed 0, population 6, three generations, 36 allocated
case evaluations, 20,000 operations and 10 seconds per case, 720,000 total allocated
operations and 180 seconds per arm. No parameter changed after observing results.

| Arm | Best mean fleet distance | Winner completed / incomplete cases | Evaluations used / allocated | Charged work | Provider requests |
|---|---:|---:|---:|---:|---:|
| Hand-authored | 415.219234 | 2 / 0 | 12 / 36 | 198,102 | 0 |
| Random search | 421.537502 | 0 / 2 | 28 / 36 | 353,250 | 0 |
| Offline fixture-guided | 421.537502 | 0 / 2 | 28 / 36 | 442,712 | 6 offline |

Fixture-guided and random results tie on both cases within numerical tolerance.
Compared with the hand winner, fixture guidance ties once and loses once, with
paired mean reduction **-1.628276%** (a regression). Completed-only comparisons
involving the fixture-guided winner have zero pairs and no estimate. This is a
functional demo, not evidence that an LLM contributes value beyond random search.
Live Ollama was **not** tested; all provider tests use mocks/offline fixtures.

`runs/phase6-frozen-strategy.json` was generated and its source/protocol hashes
verified. No real final held-out evaluation was run. Held-out unit tests stub the
numerical evaluator to test locks/catalog admission, not to produce research
results. The final-evaluation command above remains a separate explicit action.

## Phase 6 file scope

New files:

- `engine/strategies/__init__.py`
- `engine/strategies/models.py`
- `engine/strategies/provider.py`
- `engine/strategies/evaluation.py`
- `engine/strategies/evolution.py`
- `engine/strategies/experiment.py`
- `engine/strategies/protocol.py`
- `api/routers/strategies.py`
- `scripts/run_strategy_evolution.py`
- `scripts/smoke_strategy_evolution.py`
- `tests/unit/test_strategy_evolution.py`
- `tests/unit/test_strategy_api.py`
- `examples/strategy-evolution-offline.json`
- `examples/strategy-population.json`
- `docs/strategy-evolution.md`

`api/main.py` adds exactly one router import and one router registration. Removing
those two lines reproduces its pre-phase content hash. All **60 pre-existing
engine files** match `runs/phase6-source-before.json`; no historical algorithm,
benchmark guard, old test, frontend or unrelated change was rewritten. Generated
records/logs/XML/frozen artifacts under `runs/` remain ignored by existing Git
rules and should be archived separately.

## Verification record

- Focused Phase 6: **72 passed** (60 engine/provider tests, 12 API/CLI tests).
- Combined targeted run: **494 passed**, including FleetProblem **79**, trusted
  routing **160**, hybrid search **57**, benchmark/audit **71**, Phase 6 **72**,
  and historical baseline/routing **55**. XML: `runs/phase6-focused-verified.xml`.
- Python AST: **124 files passed**. TypeScript: exit **0**.
- Real strategy API loopback smoke: **12 passed**, including cancellation/resume
  and cross-job isolation. Log: `runs/phase6-smoke.log`.
- Existing local Vite/Uvicorn compatibility smoke: **11 passed**.
  Log: `runs/phase6-legacy-smoke.log`.

Exact combined targeted command:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_strategy_evolution.py tests/unit/test_strategy_api.py tests/unit/test_fleet_problem.py tests/unit/test_trusted_routing.py tests/unit/test_hybrid_search.py tests/unit/test_fleet_benchmark.py tests/unit/test_fleet_benchmark_audit.py tests/unit/test_baselines.py tests/unit/test_routing.py --junitxml=runs/phase6-focused-verified.xml -q
python -B scripts/smoke_strategy_evolution.py
```

The first new test run had 53 passes and one independent floating-point oracle
mismatch (~6e-14); the new oracle now allows 1e-10 absolute summation-order
roundoff, while an additional directed integer fixture verifies exact cost 11
against exhaustive enumeration. No existing test was relaxed. A later sandboxed
combined run had 460 passes, 33 pytest temporary-directory permission errors and
one process-pool IPC permission failure. The identical permission-corrected run
passed all 494; no assertion was bypassed. Earlier broad/smoke sessions interrupted
by the session restart have no final report and are not counted as passes.

Full offline verification: **882 passed, 1 deliberately deselected, 0 failures**,
in **278.86 seconds**. XML: `runs/phase6-offline-final.xml`; full output:
`runs/phase6-offline-final.log`. The existing Starlette/httpx TestClient deprecation
warning remains. Verification requiring pytest temporary directories/process IPC
ran with approved execution outside the filesystem sandbox after Windows access
denials; the external-HTTP/dotenv guard remained enabled.

Exact AST command (repository root):

```powershell
@'
import ast
from pathlib import Path
excluded={'.git','venv','.venv','env','ENV','node_modules','__pycache__','dist','build','runs'}
files=[p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts)]
for p in files: ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
print('AST:',len(files),'passed')
'@ | python -B -
```

Phase 6 stops here. No live provider performance, remote-provider compatibility,
hard real-time cancellation, equal hardware-compute comparison, automatic
validation selection, or LLM superiority is claimed. Existing trusted solver
policies remain the only executable policies. No frontend redesign or next phase
was started.

The saved demo received a separate artifact audit: **68 case evaluations** had
their matrix/problem identities, independent edge-sum distances, fitness, work
totals, best retention, lineage and checkpoint checksums verified. Final diff
review preserved all prior work. `git diff --check` still reports pre-existing
trailing whitespace in `api/main.py`; the hash reconstruction proves those lines
predate Phase 6. New implementation files and the two added API lines are clean;
unrelated formatting was deliberately left unchanged.
