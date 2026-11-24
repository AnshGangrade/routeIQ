# Strategy Experiments: interface and evidence

## Scope

The main application exposes one **Strategy Experiments** page. The legacy
code-generating UI is disconnected from App, including its polling, preview,
configuration and tab state. Its components, API services, backend, tests and
historical artifacts remain available for compatibility. Route comparison and
actual strategy application retain their existing execution paths.

The page explains configuration proposals, trusted deterministic execution,
independent validation and development ranking. The primary result shows mean
development distance, completion counts, recorded source counts and evaluated
LLM ancestry. An ancestry link is not causal proof of improvement. One development
trajectory chart remains visible; configurations, lineage, tokens, work,
rejections and exports are collapsed under **Technical details**.

An interactive random comparison is shown only for terminal, eligible winners
with identical complete configurations, software and problem panels in the same
browser session. It is explicitly a difference of selected development means,
not a paired unseen-case estimate. The separate research reports below provide
per-case paired analysis and uncertainty. Applying a strategy still creates a
scoped optimization job on the selected plan's matrix; training scores are never
used as application route distances.

## Provider behavior

The existing bounded loopback inventory endpoint now returns an additive status:
`available`, `model_missing`, `unreachable`, or `check_failed`. Missing/invalid
inventory fields fail closed. Connection failure cannot determine whether Ollama
is installed, and the UI says so. Responses never include raw exception bodies.

Choosing AI-guided or changing its model triggers a cancellable preflight.
Submission stays disabled until the exact model is available. Submission checks
again to catch a provider that disappeared. Random baseline needs no provider.
No UI action silently changes an AI request to random. Existing engine fallback
policy remains unchanged and is separately attributed to random proposals.

The local inventory probe on 2026-11-24 found **qwen3:1.7b available**. This alone
does not verify generation quality. Browser failure checks use explicit fixtures;
the separately recorded study uses real local model calls.

## Paired protocol and evidence

`examples/paired-strategy-study.json` fixes three matched proposal seeds
(3101, 3102, 3103), solver seed zero, 12 development cases and 12 separate
validation cases spanning 20/50/100/200 stops, all supported fleet sizes,
uniform/clustered/mixed-density and symmetric/directed problems. It reuses the
historical Phase 6B allocation without tuning from held-out outcomes:

- Population 6, three generations, two elites, 120 proposal attempts,
  six reserved model calls, 216 case evaluations per arm.
- 20,000 operations and 10 seconds per evaluation; 4,320,000 reserved
  operations and 600 seconds per arm. Provider time consumes the wall cap.
- Exact provider: qwen3:1.7b, temperature 0.3, timeout 20 seconds, one retry,
  2,048 output tokens and 65,536 response bytes.
- Both arms start with the same four authored strategies and seeded random
  fills. Arm order alternates by replicate. The AI arm also includes mutation
  and crossover; this compares mixed proposal policies, not an isolated LLM.
- Each development winner is frozen, then measured exactly once on each
  validation case. There is no feedback into evolution, retuning, or held-out
  evaluation path in the new runner. Existing held-out guards are untouched.

Commands (new output directories are required):

```powershell
python -B scripts/run_paired_strategy_study.py --protocol examples/paired-strategy-study.json --output runs/strategy-experiments-refinement/paired-live --live-local-ollama
python -B scripts/report_strategy_study.py --source runs/strategy-experiments-refinement/paired-live --output runs/strategy-experiments-refinement/paired-report
python -B scripts/audit_strategy_evidence.py --output runs/strategy-experiments-refinement/evidence
```

The last command only reads historical saved measurements. It never invokes a
solver or provider. It independently validated **2,324** archived rows against
matrix/problem fingerprints, feasibility and directed edge-sum costs. The
historical development paired percentages for seeds 2026/2027/2028 are
**+0.3120%, -2.0336%, 0%**; validation **-1.5533%, -2.8633%, 0%**.
The partial held-out comparison has **272/360** bounded pairs, **67 wins /
113 ties / 92 losses**, mean **-0.5652%** and **zero completed-only pairs**.
All **88 missing measurements remain missing**. No held-out case was rerun.

Positive differences mean random minus LLM. Percentages use the random distance
of each matched case, then take the mean/median. Both-zero distances yield zero;
positive LLM distance against a zero random reference is undefined and explicitly
counted. Ties use absolute/relative tolerance 1e-9. Reports separate completed
pairs from feasible bounded incomplete pairs and list missing case IDs.

Intervals use 2,000 seeded percentile bootstrap draws (seed 7301). Per-case
intervals condition on observed cases. Aggregate intervals resample whole
replicate means, avoiding the fiction that repeated seed-case rows are independent
instances. Three seeds give weak uncertainty estimates; development selection is
biased. Missing held-out cases may differ systematically. No superiority claim
is justified by these records. Equal allocated caps do not mean equal work or
hardware compute; model sampling is not guaranteed reproducible by a search seed.

## Verification

Commands are run from the repository root except npm commands, which run in `web`.
Vite wrappers disable environment-file loading. Backend tests use the external
HTTP/dotenv guard. Browser tests block external requests; road geometry and provider
failures are explicit fixtures. The real-backend smoke runs actual local routing
and strategy execution, independent cost validation and two-instance application.

```powershell
# web
npm.cmd test
node_modules/.bin/tsc.cmd --noEmit --incremental false
npm.cmd run build
npm.cmd run test:browser
# repository root
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_strategy_evidence.py tests/unit/test_phase9.py tests/unit/test_strategy_evolution.py tests/unit/test_strategy_api.py -q
python -B scripts/smoke_frontend_redesign.py
```

All raw research/browser artifacts are under
`runs/strategy-experiments-refinement/`; runs remain git-ignored and should be
archived separately if the evidence is to be shared.

## Measured outcome (2026-11-24)

All six new search arms finished their generation loops. Independently verified
**1,080** measured candidate-case rows: development **59 completed / 949
incomplete / 0 failed**, validation **0 completed / 72 incomplete / 0 failed**.
No reserved measurements were missing. A finished loop is not a completed search.

| Split | Paired seed-case observations | LLM win / tie / loss | Mean paired reduction vs random | Exploratory replicate bootstrap 95% interval |
|---|---:|---:|---:|---:|
| Development | 36 / 36 | 11 / 16 / 9 | -0.0409% | [-2.0003%, 1.6811%] |
| Validation | 36 / 36 | 8 / 20 / 8 | 0.3372% | [-0.6304%, 1.5306%] |

These are repeated observations of 12 cases across three seeds, not 36 independent
instances. **Completed-only pairs: zero in both splits.** Both intervals cross
zero. Nine actual local model calls returned nine schema-valid proposals; six
were unique, accepted and evaluated, three were duplicates, and zero were invalid.
There were 31,064 reported input/output tokens. Only seed 3101's winning ancestry
contained an evaluated LLM proposal. The other two winners cannot be attributed to
accepted LLM proposals. No superiority or causal LLM benefit is established.

Frozen protocol fingerprint:
`8f7985802e66ca559f77960c2742a4b3c6082342d1a5ebe28cd714d1babb218d`.
The runner froze this before execution. Checkpoints and frozen development winners
retain exact configurations. No model/schema/solver/baseline change was made to
improve the outcome. Light frontend verification overlapped the experiment;
runtime is descriptive, not a controlled hardware performance comparison.

Reports and measurements:

- New study: `runs/strategy-experiments-refinement/paired-report/report.md`,
  `report.json`, `per-case.csv`, `paired.csv`.
- Complete configurations, histories and checkpoints:
  `runs/strategy-experiments-refinement/paired-live/`.
- Historical read-only audit: `runs/strategy-experiments-refinement/evidence/`.
- Real-backend screenshots:
  `runs/strategy-experiments-refinement/product-browser/05-strategy-lab.png`
  (desktop), `05b-strategy-evidence.png` (result), and `07-lab-mobile.png` (mobile).

Verification: **62 frontend unit tests**, **98 targeted backend tests**, **19
mocked browser workflow checks**, **28 real-backend browser checks**, and **11
independent matrix/coverage audits** passed. TypeScript, production build and
Python AST parsing (**133 files**) passed. The API smoke verified clean local
startup/shutdown, cancellation and application on two different instances. It did
not call external road services or live LLMs; those provider/geometry failures were
explicit fixtures. Live LLM evidence comes only from the separate registered study.

Initial verification caught an outdated label expectation and mobile navigation
overflow. The expectation was updated to the required label and the navigation
was made to wrap. No test was deleted or weakened. Node initially failed to spawn
inside the Windows sandbox (EPERM); the same commands passed with approved process
permissions. One existing Starlette/httpx deprecation warning remains.

Exact AST command:

```powershell
@'
import ast
from pathlib import Path
excluded={'.git','venv','.venv','env','ENV','node_modules','__pycache__','dist','build','runs'}
files=[p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts)]
for p in files: ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
print('AST:',len(files),'passed')
'@ | python -B -
git diff --check
```

Final preservation checks match all **76 engine files** in the Phase 9 snapshot
and **96 protected historical research artifacts**. No `.env` file was accessed.
Historical held-out results and consumed guards remain unchanged.

## Exact source files changed

Modified:

- `api/routers/strategies.py`
- `scripts/smoke_frontend_redesign.py`
- `web/src/App.tsx`
- `web/src/components/CompareScreen.tsx`
- `web/src/components/StrategyLab.tsx`
- `web/src/services/api.ts`
- `web/src/types/api.ts`
- `web/src/watercolor.css`
- `web/tests/product-browser.mjs`
- `web/tests/product.cjs`
- `web/tests/workflow-browser.mjs`
- `web/tests/workflow.cjs`

Added:

- `docs/strategy-experiments-refinement.md`
- `examples/paired-strategy-study.json`
- `scripts/audit_strategy_evidence.py`
- `scripts/report_strategy_study.py`
- `scripts/run_paired_strategy_study.py`
- `tests/unit/test_strategy_evidence.py`
- `web/src/services/experiments.ts`
- `web/tests/experiments.cjs`

Remaining limitations: the interactive UI is still a two-case development demo;
the larger paired research study is a CLI workflow. Session comparisons/history
remain in memory. Historical held-out evidence remains incomplete, and no new
held-out sweep was attempted. Three replicates, low solver caps, non-deterministic
model sampling and mixed proposal sources limit scientific conclusions. More
experiments require a new prespecified protocol; this task does not tune one from
these outcomes or begin another feature phase.
