# Phase 5: measuring the controller contribution

This adds a four-arm experiment around the existing solver. It does not change
historical baseline definitions, the solver, strategy schema, previous reports,
or the Phase 5B/6B held-out guards. No superiority claim follows from participation.

## Protocol and estimand

For each canonical FleetProblem and replication seed, every arm receives the
same two trial slots, each capped at 20,000 host operations and 8 seconds. The
runner passes the very same immutable problem object to all arms/trials. Trial
seed is `(replication_seed + trial_index * 1000003) mod 2**32`; zero is valid.
The default panel has four cases (20/50/100/200 stops, 1/3/5/10 drivers,
uniform/clustered/mixed-density, symmetric/directed) and three replication seeds.
It is a small exploratory panel, not a balanced benchmark or a power calculation.

Arms:

1. **hybrid**: existing conventional portfolio + VND + ILS, using unchanged
   `SearchConfig()` defaults (including eight ILS iterations).
2. **random**: existing seeded random strategy sampler, followed by a fixed
   checkpoint schedule. Up to eight draws reject inapplicable directed Sweep
   proposals; rejected proposals and generation time are recorded. No silent
   replacement after that cap.
3. **static_llm**: real initial problem-aware strategy selection, then the same
   fixed checkpoint schedule as random. No later model calls or strategy changes.
4. **adaptive_llm**: initial selection plus bounded decisions from actual measured
   feedback, using the existing adaptive controller.

Static/random retain the initial work slice at checkpoints. Adaptive can select
the supported next action and slice. Conventional retains its historical hybrid
schedule. These schedule differences are the treatment, not an identical internal
algorithm. Static/adaptive initial responses are independently generated with
matched provider options and seeds; they need not be identical. This is an
end-to-end comparison, not a causal ablation holding initial proposals fixed.

All arms have identical host operation/time ceilings, trial counts, available
operator set, feasibility rules, and solution-selection rule. Model latency and
proposal preparation consume the trial time allocation. Unused time/work is not
redistributed between trials. Arm order is deterministically shuffled per
case/seed and execution is sequential. The best independently validated route
across the allocated trials is selected; all trials remain in the evidence.

The exact Ollama model is `qwen3:1.7b`. Default model limits per trial are three
request attempts, two checkpoints, six seconds total model time, five seconds per
request, zero retries, 768 requested output tokens, 8,192 context tokens and
40,000 reserved context/output tokens. Model, temperature, seed, token caps and
request outcomes are recorded. Static uses only its initial request; non-LLM arms
use none. Common maximum allowances do not imply equal actual work.

Inference hardware work, RAM and energy are not independently metered or hard
limited. Solver work units are heterogeneous candidate/call counts, not CPU
instructions. Deadlines are cooperative; actual runtime overruns are recorded.
Mandatory independent validation can finish after a deadline. These limitations
prevent an equal-hardware-cost or speedup claim. Artifact/report I/O and aggregate
analysis are outside arm timing; trial timing includes route validation and
proposal overhead. Model warm-up/cache effects remain a limitation.

## Measurements and statistics

Every trial stores routes, independent objective values, status, actual work,
runtime, termination, operator telemetry, full accepted controller decisions,
provider errors, token reporting and attribution. Group rows report the selected
trial, longest route, completed/incomplete/failed/missing counts, actual model
calls, unknown work/token counts and provider seconds. A failed initial LLM
response returns no AI route; it is never substituted with random search.

A group is completed only if every allocated trial completed. A valid result
with an incomplete or failed slot is incomplete; absent measurement files make
the group missing. **Primary paired statistics require both groups completed.**
Separate bounded-incumbent statistics include valid incomplete groups. They are
not silently promoted into completed measurements. In particular, existing
conventional ILS reports `ils_iteration_limit` as stopped/incomplete even after
its configured iterations; this experiment preserves that status. Completed-only
comparisons against that arm can therefore have zero eligible pairs.

Percent improvement uses `100 * (reference - candidate) / reference`. Zero/zero
is a tie and zero percent; positive cost against zero has undefined percentage.
W/T/L uses existing nonzero absolute/relative `1e-9` tolerance, while percentages
retain unrounded differences. W/T/L denominators and defined-percentage
denominators are separate. Mean, median, worst result, all paired distances,
exclusions, subgroup summaries, runtime and work differences are persisted.

Repeated seeds on the same instance are dependent. Dispersion and bootstrap
intervals are computed from **per-case mean percentages**, not by pretending
seeds are independent instances. Four independent cases are insufficient for a
general superiority claim. Subgroups with one case have no confidence interval.
Completed-only conditioning and best-of-two selection are explicitly reported.

Winner attribution distinguishes an accepted LLM initial selection, an applied
LLM checkpoint, and an applied reorder/diversification recommendation. It also
records the retained route's source and gain after construction. A model can be
accepted while a mandatory conventional constructor supplies the winning route.
Participation, a rationale, or even an applied action does not prove a causal
distance gain.

## Split and evidence protection

Protocol JSON freezes source/environment provenance, all settings, seeds, arms,
and exact development/validation/held-out panel definitions before execution.
Experience import is disabled for this control to avoid untracked historical
selection. Prompts contain only the current problem summary and search feedback,
never other split results. On a validation problem, feedback is confined to that
single solve; it does not update another trial's policy.

Validation requires matching completed development artifacts, audited against
saved measurements, and consumes a single-use protocol/mode registry entry.
It supports controlled final selection, not repeated tuning. Source/configuration
changes require a new protocol and experiment, with their history disclosed.
The current CLI **rejects held-out execution**. A separately reviewed final
evaluation and freeze/acknowledgement workflow is deliberately deferred until
this architecture/protocol has been reviewed; no large held-out run is started.

New directories only. Each measurement is written once with an integrity checksum
and fsync; no checkpoint replacement, overwrite, implicit resume, or automatic
repair occurs. Interrupted runs can be audited into a separate report, counting
missing slots without executing them. A corrupt partial file fails audit instead
of being silently discarded. Old incomplete Phase 6B records remain untouched.

## Commands

From repository root (no environment-file loading):

```powershell
python -B scripts/run_controller_benchmark.py freeze --output runs/controller-value-20261125/protocol.json
python -B scripts/run_controller_benchmark.py run --protocol runs/controller-value-20261125/protocol.json --split development --live --output runs/controller-value-20261125/development
python -B scripts/run_controller_benchmark.py run --protocol runs/controller-value-20261125/protocol.json --split validation --development runs/controller-value-20261125/development --live --output runs/controller-value-20261125/validation
python -B scripts/run_controller_benchmark.py audit --input runs/controller-value-20261125/development --output runs/controller-value-20261125/development-audit
```

Create the protocol's parent directory first. Reusing an output path is rejected.
`freeze --config <explicit-non-secret-json>` freezes a different preregistered
configuration. Omit `--live` for explicitly labeled offline fixtures only; these
are implementation checks, never LLM-performance evidence. No automatic model
fallback is supported. Live admission checks the exact installed model.

JSON includes all trials and traces; CSV contains per-case/seed/arm outcomes;
Markdown summarizes completion and completed-only paired quality.

## Implementation files

- `engine/evaluation/controller_benchmark.py`: protocol, matched execution,
  independent validation, immutable evidence writes, audit and reports.
- `engine/evaluation/controller_reporting.py`: paired metrics, denominators,
  characteristics and case-level dispersion.
- `scripts/run_controller_benchmark.py`: explicit offline/live CLI.
- `tests/unit/test_controller_benchmark.py`: protocol, fairness, deterministic
  offline replay, statistics, split/guard, attribution and report regressions.
- `docs/controller-value-evaluation.md`: protocol and measured audit record.

## Measured live evidence: 2026-11-25

Frozen protocol fingerprint:
`e3d95b2e249c914ce4eb4e06fd8bedca4297910357368487b25761f853b1ae48`.
The exact installed `qwen3:1.7b` model was available before execution. Its tag and
provider settings are recorded; model-weight digest/hardware identity was not
pinned, so exact inference reproduction is not guaranteed. No parameters changed
between development and the one validation run. No held-out case was executed.

Both splits contain 96 saved trials: four cases × three replications × four arms
× two trials. There are no missing measurement files. Counts below are
**case/seed/arm groups**, each selecting from its two allocated trials.

| Split | Arm | Completed | Incomplete | Failed | Missing | Aggregate trial seconds |
|---|---|---:|---:|---:|---:|---:|
| Development | Conventional hybrid | 0 | 12 | 0 | 0 | 7.465 |
| Development | Random | 3 | 9 | 0 | 0 | 7.010 |
| Development | Static LLM | 3 | 9 | 0 | 0 | 56.532 |
| Development | Adaptive LLM | 2 | 9 | 1 | 0 | 69.089 |
| Validation | Conventional hybrid | 0 | 12 | 0 | 0 | 7.337 |
| Validation | Random | 4 | 8 | 0 | 0 | 7.810 |
| Validation | Static LLM | 3 | 9 | 0 | 0 | 64.085 |
| Validation | Adaptive LLM | 3 | 9 | 0 | 0 | 74.158 |

Trial-level completed/incomplete/failed counts, in arm order hybrid, random,
static LLM, adaptive LLM:

- Development: `0/24/0`, `7/17/0`, `6/18/0`, `4/18/2`.
- Validation: `0/24/0`, `8/16/0`, `6/18/0`, `6/18/0`.

All conventional-hybrid trials actually stopped at the 20,000-operation cap.
There are therefore **zero completed-only pairs against that arm**; do not
interpret a null statistic as zero improvement.

| Comparison | Split | Completed pairs / 12 | W/T/L | Mean paired % | Independent cases |
|---|---|---:|---|---:|---:|
| Adaptive vs static LLM | Development | 2 | 0/2/0 | 0 | 1 |
| Adaptive vs static LLM | Validation | 3 | 0/3/0 | 0 | 1 |
| Adaptive vs random | Development | 2 | 1/1/0 | 0.2664 | 1 |
| Adaptive vs random | Validation | 3 | 1/2/0 | 0.3924 | 1 |

The apparent completed-only gain over random comes from just one underlying
instance per split, not independent replication across diverse problems.

For **valid bounded incumbents, not completed-only results**:

- Adaptive vs static: development 11/12 available pairs, all ties; validation
  12/12, all ties. Adaptive added 12.557 seconds across all development trials
  and 10.073 seconds across validation trials relative to static.
- Adaptive vs conventional: development 11 ties; validation 9 ties and 3 losses.
  Validation mean paired improvement is **−0.5755%**, median 0%; worst is
  **−2.3019%**. This does not support an advantage over the conventional solver.
- Adaptive vs random: development W/T/L 2/5/4 on 11 pairs; validation 3/7/2 on
  12 pairs. Validation mean is +3.2884%, median 0%, and worst regression
  **−12.0173%**. Regressions and the sparse panel rule out a blanket benefit claim.

The model made 116 actual requests across both splits. Reported usage totals
152,565 tokens; two timed-out initial requests have unknown usage, so this is
not a complete token bill. Development recorded two timeouts and six other
provider/response failures; validation recorded five provider/response failures.
Error categories do not establish whether each latter failure was invalid JSON,
schema rejection, or another provider-response issue.

Accepted checkpoint proposals were **only `continue`**: two in development and
seven in validation. One development winning group and two validation winning
groups included applied checkpoint decisions. No accepted reorder or diversify
action was recorded. All feedback checkpoints occurred on the 20-stop case;
the 50/100/200-stop cases exhausted work before any checkpoint. These measurements do not demonstrate useful
feedback-driven adaptation or permanent learning.

Decision: retain the existing conventional default; neither LLM arm is promoted.
This is a conservative product decision, not a statistically proven universal
ranking. A stronger experiment needs a new preregistered panel/budget and model
artifact pinning; these results must not be retroactively relabeled or overwritten.

Artifacts (all in a new directory):

- `runs/controller-value-20261125/{development,validation}/`: JSON, CSV, Markdown,
  immutable measurement files and manifests.
- `development-audit/` and `validation-audit/`: independently reconstructed reports,
  exactly equal to the originals, without rerunning any solve.
- `evidence-audit.json`: 190 feasible trial routes independently checked for edge
  sums, depot returns, exact coverage and workload; all 24 directional paired
  summaries across both splits checked from saved rows. The other two trials
  failed initial selection and have no route to validate.
- `selection-decision.json`: validation-linked non-promotion decision, no tuning.
- `paired-arithmetic-audit.json`: all 48 completed-only/bounded directional
  summaries independently checked for pair counts, W/T/L, mean, median and worst
  regression across both splits.
- `frozen-source/`: 77 implementation/entrypoint source files preserved for audit;
  no environment files or secrets copied.

Experiments ran sequentially on a development workstation, not an isolated
benchmark machine. OS/model-cache effects and background activity remain timing
limitations. No universal improvement, equal-hardware-work result, or global
optimality is claimed.

## Verification commands

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_controller_benchmark.py tests/unit/test_fleet_benchmark.py tests/unit/test_fleet_benchmark_audit.py tests/unit/test_adaptive_controller.py tests/unit/test_hybrid_search.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/controller-value-20261125/offline-regressions.xml -q
git diff --check
```

The focused command passed 175 tests, including all 13 new framework tests.
The full offline command passed **973 tests**, with one explicitly deselected
environment-example test, zero failures, and one existing Starlette/httpx
deprecation warning in 327.52 seconds. Its JUnit evidence is
`runs/controller-value-20261125/offline-regressions.xml`. Final diff checks passed
(Git line-ending notices only).
One initial new test caught Pydantic coercing a Boolean seed into an integer;
the protocol now requires strict integer seeds. No existing assertions were
weakened. Source fingerprint verification passed after both live runs and the
audits. AST parsing passed for 413 Python files, including archived source:

```powershell
@'
import ast
from pathlib import Path
excluded={'.git','venv','.venv','env','ENV','node_modules','__pycache__','dist','build'}
files=[p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts)]
for p in files:
    ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p))
print(len(files), 'passed')
'@ | python -B -
```

The environment-example-reading test is explicitly deselected to honor the
no-environment-file requirement. Live/manual tests are outside the offline suite.
Frontend types, API contracts and UI were unchanged in this phase, so frontend
checks were not repeated. The actual live CLI experiments provide the local
integration smoke, with independent source/route/report verification.
