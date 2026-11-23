# Optimization upgrade Phase 2: Shared Fleet Problem Contract

Scope: problem definition, independent fleet validation, and compatibility
adapters only. No assignment algorithm, optimization operator, LLM evolution
policy, frontend, API request schema, or historical baseline was redesigned.
Earlier working-tree changes were retained. No environment files were accessed
and no external LLM/OSRM services were called.

## Contract

`engine/routing/problem.py` defines frozen Pydantic models with forbidden extra
fields and immutable nested tuples. `FleetProblem` v1 contains:

- `schema_version = "fleet-problem/v1"`.
- `depot_id`, ordered `stop_ids`; matrix order is depot followed by these stops.
  IDs need not be consecutive. Driver slots are indexed 0 through k-1.
- `distance_matrix`: square finite nonnegative float values; no symmetrization.
- `distance_units`: `map_units`, `meters`, or `kilometers`.
- `directed`: false requires exact matrix symmetry; true permits asymmetric
  or accidentally symmetric directed data. Road adapters always set true.
- `num_drivers` and explicit `workload.minimum_stops` / `maximum_stops` tuples.
  Defaults are floor(n/k) and ceil(n/k) for every driver. Explicit tighter bounds
  must remain inside those limits and admit a feasible total stop count.
- Optional `coordinates`, in identical node order, with `coordinate_system`
  (`cartesian` or `lon_lat`). Geographic ranges and finite pairs are validated.
- `matrix_provenance`: source (`euclidean`, `road`, `provided`), optional provider
  and dataset version. Arbitrary provider response metadata/credentials are not
  copied into this structure.
- `objective`: minimize `total_distance`; optional reported secondary metric
  `longest_route_distance` (enabled by default). This does not add a weighted
  objective or change existing tie-breaking.
- `instance_seed` and separate `search_seed`; zero remains valid. Search seed is
  carried as run metadata; no search algorithm or LLM randomness changed here.

`matrix_fingerprint` is SHA-256 of the normalized float matrix encoded as compact
JSON. `fingerprint` is SHA-256 of sorted-key compact JSON for the full validated
problem except `search_seed`. Thus matrix content, ordered IDs, drivers, bounds,
objective, units, coordinates, provenance, instance seed and schema version all
participate. Hashes are derived properties, recomputed after JSON loading; they
are not caller-supplied identities. Identical definitions have identical hashes.
Different search seeds deliberately identify the same routing problem.

`matrix_array()` returns a NumPy view backed by immutable bytes. Both element
assignment and re-enabling its write flag fail. Modifying a constructor input
matrix cannot mutate the stored problem.

## Independent feasibility and objective

`validate_fleet_solution(problem, routes)` accepts routes in driver-slot order
using problem IDs. It requires exactly k routes, depot endpoints, no interior
depot visits, exactly-once stop coverage, known integer IDs, and each driver's
workload bounds. It independently computes every route cost, D (fleet total),
and longest route, rejecting nonfinite totals even when individual edges are
finite. It does not trust solver-provided distance fields or lock feasibility
to the historical assignment territories.

An idle driver uses `[depot, depot]` and costs zero (no travel), including for
provided matrices with nonzero diagonal entries. With k > n the bounds become
0..1. With n = 0 every route is idle. Edge accumulation retains the historical
floating-point order to avoid changing baseline results by rounding artifacts.

## Integration and compatibility

- `InstanceGenerator.generate_problem()` returns a canonical synthetic problem;
  existing `generate()` and `generate_batch()` still return `DeliveryInstance`.
- `problem_from_instance()` is the explicit legacy bridge. A missing matrix
  selects synthetic Euclidean construction only. Provided matrices are preserved;
  road units/provenance without a matrix fail rather than fall back to Euclidean.
  Legacy depot 0/sequential-stop validation remains intact.
- `problem_from_road_result()` consumes a successful, already-fetched road result
  with metre units and directed semantics. It makes no network requests and
  rejects failed or invalid results.
- API instance creation stores one immutable `problem` and a read-only legacy
  matrix view. Routing uses this problem and rejects disagreements with legacy
  cache fields. Old in-memory records without `problem` use an explicit adapter.
  API request/response contracts and frontend types are unchanged.
- `FleetRouter(FleetProblem)` preserves the existing angular round-robin
  assignment and per-driver NN/2-Opt/scorer algorithms. ID/index translation
  supports arbitrary canonical IDs. Aggregation independently validates routes
  and recomputes all costs. The incumbent selector retains its stronger
  same-assignment comparison rule in addition to global feasibility.
- `HeuristicEvaluator` accepts FleetProblem batches and passes their matrix,
  units, driver count and bounds through the same fleet router as application
  routing. Results include fleet routes, problem fingerprint, driver count,
  units, total and longest distance. Failed evaluations retain problem metadata;
  incomplete comparisons do not become improvements. Mixed-unit aggregation
  raises an error.
- Legacy `DeliveryInstance` evaluation stays explicitly single-route with the
  original stop ordering and 100-iteration 2-Opt default. Canonical fleet
  evaluation defaults to the application's 1000 iterations per driver. An
  explicit iteration argument overrides either default. Old coordinate-only
  fingerprints are not silently treated as canonical fingerprints.

## Deliberate boundaries

The shared contract is usable by training, validation, held-out evaluation and
application. Tests supply canonical batches to the existing evolution loop and
verify training and held-out totals. **Default evolution dataset generation is
still the legacy synthetic single-driver workflow.** No new validation-split
management, road benchmark ingestion, strategy schema, population changes or
research protocol was introduced. This phase establishes shared inputs; it does
not claim all default research/application workflows have become identical.

Matrix-only problems are valid and independently verifiable. The existing
multi-driver angular assignment still requires coordinates for nonempty fleets;
its adapter fails explicitly if absent. Single-driver matrix-only routing works.
Tighter per-driver workload bounds can similarly make a historical fixed
assignment infeasible; the validator rejects it instead of inventing a new
assignment algorithm. These are future construction-layer tasks.

Road provenance cannot invent an OSRM dataset version that the provider does
not return. Matrix hashes pin actual content but do not certify freshness.
The API stores remain process-local and nondurable. Frozen models are data
integrity tools, not a security boundary against arbitrary host Python code.

## Verification commands

Run from `D:\routeIQ`:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_fleet_problem.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_baselines.py tests/unit/test_instances.py tests/unit/test_routing.py tests/unit/test_heuristics.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/fleet-problem-offline.xml -q
python -B scripts/smoke_phase3.py
```

The broad suite includes the 144-test Phase 1 group, Phase 2/3/4 regressions,
routing/baseline tests and later incumbent tests. Manual/live test modules are
excluded; the one foundation test that reads an environment example is
deliberately deselected. The offline plugin blocks external HTTP and dotenv.
The local smoke runs real Uvicorn/Vite on loopback with environment-file loading
disabled; it exercises only synthetic routes and mock evolution.

TypeScript (from `D:\routeIQ\web`):

```powershell
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
```

AST parsing (repository root):

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

## Files changed in this phase

- New: `engine/routing/problem.py`, `engine/routing/validation.py`,
  `engine/routing/adapters.py`, `tests/unit/test_fleet_problem.py`, this document.
- Updated: `engine/routing/__init__.py`, `engine/routing/fleet.py`,
  `engine/routing/incumbent.py`, `engine/instances/generator.py`,
  `engine/evaluation/evaluator.py`, `engine/evaluation/models.py`,
  `api/routers/instances.py`, `api/routers/routing.py`,
  `tests/unit/test_incumbent.py`.

The existing incumbent tie-case test now constructs its all-equal matrix before
creating the immutable router. Its assertions are unchanged. No test was deleted
or relaxed.

## Verification notes

Final broad offline run: **522 passed, 0 failed, 0 errors, 1 deliberately
deselected**, in **417.946 seconds**. The completed JUnit report is
`runs/fleet-problem-offline.xml`. This includes all Phase 1–4 regression files,
the existing incumbent tests, and the 79 new contract tests. Counts below are
subsets or separate focused runs, not additional tests in the broad total.

Focused contract tests: **79 passed**. The separate Phase 1 routing, baseline,
instance and heuristic suite: **144 passed**. AST parsing: **94 files passed**.
TypeScript: exit 0. Real local Uvicorn/Vite smoke: **11 passed, 0 failed**, with
clean server shutdown. Road integration tests use offline fixture matrices;
live OSRM, map tiles and LLM providers were not exercised.

During development, the first Phase 1/incumbent run had 155 passes and three
failures: two were floating-point accumulation differences, fixed by preserving
historical edge order, and one was the mutable tie fixture described above.
An initial new contract fixture incorrectly asserted a fleet lower bound for a
single driver; the test now uses exact hand-calculated totals (17, 33 and 37 for
1, 2 and 5 drivers) instead. The initial broad run had **514 passed, 1 failed,
1 deselected**: the failure required the legacy "Distance matrix shape" message.
That wording was restored without changing the existing test. The subsequent
contract/road check passed all 80 tests before the final full rerun.

The only test warning observed is the existing Starlette/httpx TestClient
deprecation. Scoped diff review also reports pre-existing trailing whitespace
in the already-modified API modules; unrelated formatting was left intact.
