# Optimization upgrade Phase 3: trusted construction and fleet moves

This phase adds independently callable constructors and operators over the
existing FleetProblem. It does not change legacy baselines, API routes, frontend,
evolution, prompts, or the existing incumbent selection. There is no ILS, VNS,
ALNS, population management or automatic operator schedule.

## Contract and use

```python
from engine.routing.construction import cheapest_insertion
from engine.routing.operators import improve_cross_exchange

initial = cheapest_insertion(problem)
proposal = improve_cross_exchange(problem, initial.routes, max_moves=10_000)
assert proposal.total_distance <= initial.total_distance
```

Every result is a frozen `TrustedPlan` containing tuple routes in driver-slot
order, independently recomputed per-route costs, total distance, longest route,
problem fingerprint, method name and frozen `WorkCounters`. Every endpoint is
the problem's depot ID; arbitrary/nonsequential stop IDs work. Neither the
problem nor the caller's route lists are modified.

`checked_plan` delegates to Phase 2's independent fleet validator. Duplicate or
missing stops, missing depot returns, incorrect driver counts, and workload
violations fail explicitly. Costs always use the provided matrix. Idle routes
cost zero, including when supplied matrix diagonals are nonzero. Longest-route
distance is reported but does not change the total-distance objective.

## Constructors

| Callable | Behavior |
|---|---|
| `nearest_neighbor_starts(problem, attempts=4)` | Matrix-based fleet NN; allocate feasible quotas from minima, then distribute remaining capacity in driver order. Attempt zero starts at the nearest stop. Later attempts choose distinct alternative first stops in a local seeded permutation. Keep the shortest fully validated fleet; retain the earlier attempt on ties. |
| `cheapest_insertion(problem)` | Joint matrix-based assignment and cheapest insertion across eligible drivers. Reserve enough remaining stops to satisfy all minimum workloads. Directed insertion deltas include both incoming/outgoing arcs. Works without coordinates. |
| `contiguous_sweep(problem)` | For declared Euclidean, Cartesian, symmetric problems only: sort stops by polar angle and ID, partition into contiguous quota-sized groups, then use matrix NN within each group. No angular round-robin distribution. |
| `legacy_angular_round_robin(problem, method=...)` | Named adapter to the unchanged FleetRouter NN or 2-Opt baseline and its historical assignment. Retains the existing coordinate requirements and rejects unsupported methods. |

NN attempts must be an integer in 1..16, and at most n distinct first stops are
tried (one idle plan when n=0). Attempts are whole-fleet constructions, not a
Cartesian product of first choices for every driver. `search_seed`, including
zero, controls the local permutation; absent seed defaults to zero. Global random
state is untouched. Other constructors are deterministic without randomness.
Ties use explicit ordered stop ranks/driver slots/gaps, or angle then ID for
sweep. Increasing attempts preserves the previously considered prefix.

The matrix-based constructors address coordinate-free directed fleets and
tighter workload bounds without modifying the old comparator. They are new
methods, not replacements for historical baseline definitions. Standalone
constructors are not guaranteed to beat either baseline; the existing application
incumbent guard remains unchanged. Integrating them into a future solver/API
selection policy is deliberately deferred.

## Operators

Each of the five new neighborhood operators evaluates moves against the original
input fleet and returns the best verified strict improvement in one bounded
pass. It does not repeatedly optimize or invoke other operators.

- `improve_relocate`: move one stop to another position within its route.
- `improve_swap`: swap two positions, including adjacent positions.
- `improve_or_opt_2`: relocate an intact two-stop chain without reversing it.
- `improve_cross_relocate`: transfer one stop between drivers only when source
  minimum and destination maximum counts permit it.
- `improve_cross_exchange`: exchange one stop between drivers; counts stay fixed.
- `improve_two_opt`: adapt the unchanged directed-safe baseline to canonical IDs
  and full fleet validation. Default one baseline iteration per driver, with an
  allowed range of 1..100. This wrapper may accept a proposal for multiple drivers;
  it does not schedule other neighborhoods.

`Move(kind, driver, start, other_driver, target)` and `apply_move` support explicit
independent move application. Positions include the opening depot at zero.
For intra-route relocation, target is the insertion index **after removing** the
stop/chain. For cross-route relocation it is the destination's original insertion
index. Swap/exchange targets refer to the original stop positions. Depots cannot
be moved. Invalid positions, driver combinations and workloads raise ValueError.
Equal or worse valid moves return the original plan, with newly measured costs.

Directed relocation deltas remove/add boundary arcs and preserve chain direction.
Swap deltas deduplicate affected edge positions so adjacency is handled correctly.
Cross-route deltas account for both routes, including idle-route semantics. Each
delta takes constant arc lookups. Potential improvements undergo full independent
validation and actual fleet-cost recomputation before selection. Near-equal
floating-point estimates receive full checks using a roundoff guard; acceptance
still requires actual `new_total < old_total`, with no epsilon-based improvement
claim. Equal improving proposals retain the first one in stable driver/position
enumeration order.

## Bounds, counters and performance

The new neighborhoods default to 10,000 evaluated moves, with a hard parameter
ceiling of 100,000. Invalid budgets are rejected, not silently clipped. When the
budget stops a neighborhood early, `work.truncated` is true; the output does not
claim to be the best move in the unexamined remainder or a local optimum.

`candidates_evaluated` counts NN next-stop comparisons, insertion alternatives,
or neighborhood deltas, depending on method. It is not a CPU instruction or
wall-time budget. `full_validations` counts boundary checks in the new layer;
`baseline_calls` separately counts delegated baseline calls, not their internal
edge checks. `attempts` records constructor attempts. For new neighborhoods,
`accepted_moves` is 0 or 1; for 2-Opt it counts accepted driver proposals, not
internal reversals. Input-size-bounded construction loops remove one remaining
stop at each step; NN additionally has the fixed attempt ceiling.

One local diagnostic used `InstanceGenerator(seed=42).generate_problem(100, 5,
search_seed=0)`. Constructors took approximately 0.006–0.050 seconds. These are
single-run development observations, not benchmark claims or service guarantees.
Cheapest insertion produced D=1315.227851 map units. Each following operator was
run independently on that same plan:

| Operator | Evaluated deltas | Full validations | Result D |
|---|---:|---:|---:|
| Relocate | 1900 | 3 | 1295.760817 |
| Swap | 950 | 2 | 1302.804686 |
| Or-Opt-2 | 1710 | 3 | 1308.280811 |
| Cross relocate | 0 | 1 | 1315.227851 |
| Cross exchange | 4000 | 4 | 1302.783988 |
| Existing 2-Opt wrapper | 5 baseline calls | 6 | 1300.242552 |

Cross relocation has no feasible moves in this example because all five drivers
must retain exactly 20 stops. Exchange remains available. The new delta-based
passes took approximately 0.005–0.035 seconds here. Cheapest insertion still has
cubic worst-case work in stop count; equal-cost neighborhoods can need full
validation of every move. Existing 2-Opt retains its full-route recomputation.
Nonfinite objective totals fail closed. No optimality or whole-job deadline is
claimed, and no advanced operators were introduced.

## Correctness tests

`tests/unit/test_trusted_routing.py` covers construction feasibility, tighter
bounds, coordinate-free directed matrices, contiguous territories versus the
legacy comparator, seed zero/global RNG isolation, caps and counters, arbitrary
IDs, idle drivers, nonzero matrix diagonals, immutable inputs/results, invalid
fleets/moves, ties, and fractional/large distances.

Neighborhood oracles enumerate all 24 four-stop single-driver permutations or
all 240 feasible five-stop two-driver fleets, for symmetric and directed
matrices with two seeds. They independently enumerate literal route edits,
compute complete costs, compare directed deltas to full-cost differences and
assert the selected objective equals the best feasible neighbor. Separate
hand-constructed examples require measurable gains for every new operator,
including adjacent/nonadjacent swaps and first/last-stop relocations. The existing
2-Opt wrapper is checked against independent first-improvement reversal oracles.
Cheapest insertion is also compared against an oracle that recomputes entire
partial-fleet costs rather than using the production insertion delta.

## Verification commands

Final results: **682 passed, 0 failed, 1 deliberately deselected**, in **275.52
seconds**, recorded in `runs/trusted-operators-offline.xml`. The focused command
below separately passed **308 tests**. The broad total includes **160 new trusted
routing tests**, **79 FleetProblem tests**, **144 Phase 1 tests**, **72 Phase 2
core tests** (plus its best-heuristic API regression), **91 Phase 3 regression
tests**, **32 Phase 4 tests**, and **14 incumbent tests**, along with the remaining
offline tests. These group counts are subsets, not additional to the total.

Python AST parsing: **99 files passed**. TypeScript: **exit 0**. Real local
Uvicorn/Vite smoke: **11 passed, 0 failed**, with clean shutdown. No test failure
occurred during this phase. The existing Starlette/httpx TestClient deprecation
warning remains. Final review found no trailing whitespace in the six new files.

From `D:\routeIQ`:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_trusted_routing.py tests/unit/test_fleet_problem.py tests/unit/test_baselines.py tests/unit/test_routing.py tests/unit/test_incumbent.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/trusted-operators-offline.xml -q
python -B scripts/smoke_phase3.py
```

The broad run includes Phase 1–4 regressions. Live/manual modules are outside the
offline suite. The existing environment-example test is excluded solely because
it reads an environment file, as in earlier phases; no test was weakened or
skipped to conceal failures. The guard blocks dotenv and external HTTP. The
smoke uses real local Uvicorn/Vite, synthetic instances and mock evolution, with
external services and environment-file loading disabled.

From `D:\routeIQ\web` (no shared API types changed):

```powershell
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
```

AST parsing from repository root:

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

## Exact files added

- `engine/routing/trusted.py`
- `engine/routing/construction.py`
- `engine/routing/operators/__init__.py`
- `engine/routing/operators/moves.py`
- `tests/unit/test_trusted_routing.py`
- `docs/trusted-routing-operators.md`

All pre-existing source files and modifications were preserved. No environment
files/secrets were read or modified, and no live LLM/OSRM requests were made.
