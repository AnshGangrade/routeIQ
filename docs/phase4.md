# Phase 4 reliability and readiness

This phase preserves the existing engine, API, frontend, and earlier changes.
No environment files were opened or changed, and no live LLM/OSRM calls were made.

## Implemented behavior

- Existing full UUID instance IDs remain intact. Regression tests prove equal-seed instances do not share cached route results. OSRM cache keys now include endpoint, provider, driving profile, annotations, and ordered coordinates; old cache entries are deliberately not reused. The default public endpoint uses HTTPS.
- API limits: synthetic 5–200 stops, road 5–99 stops plus depot, 1–20 drivers. Seeds accept zero and are bounded to leave room for training/held-out seed offsets. Layouts, matrix shapes, finite nonnegative distances, coordinate pairs, depot/stop indices, geometry, and durations are validated. Failed road requests never become synthetic successes. Zero-distance baseline comparisons return zero only for a zero/zero tie; otherwise improvement is unavailable.
- Full UUID run IDs, run-specific progress/cancellation, locked terminal transitions, and cancellation before client creation. Completed status is published after the winner fields are stored. Failed jobs expose fixed messages without tracebacks or provider response bodies. Held-out metrics remain separate from training fitness and applied-instance results.
- Requested model and temperature reach the client, including zero temperature and a model override without LLM_MODEL. Seed zero reaches instance generation. Seed controls instances, not guaranteed reproducibility of an external model provider.
- CLI uses the supported client factory, closes clients even if loop construction fails, reports nonzero exits for invalid/failed runs, and supports offline replay. API and CLI replay explicitly cycle the existing `simple_nearest` and `weighted_heuristic` fixtures. Replay is deterministic fixture reuse, not new LLM discovery. Direct replay requests without a configured sequence retain explicit fixture lookup semantics; responses are independent copies.
- Runtime configuration reads **process environment variables only**. It no longer implicitly loads `.env`. Configure live deployments through their process launcher; no live deployment was tested here.
- Error responses omit rejected input values, upstream bodies, raw exception text, and tracebacks. Logging uses fixed event names with structured `run_id`/`error_type` fields where available. LLM credential fields are excluded from string representations. Provider failures preserve useful safe categories/status codes.
- Blocking generation/routing stays in the thread pool; the connectivity diagnostic is synchronous so FastAPI dispatches it to the thread pool. Four shared expensive-request slots reject excess work with 429. Evolution admits at most two active jobs and 100 retained runs; instances are capped at 100. A run is capped at 100000 generation × candidate × training-instance × stop evaluations. Submitted heuristic code is capped at 50000 characters. Admission rejects excess work instead of evicting an instance/run the UI may still reference.
- Frontend road driver limits now match the API, input parsing rejects partial/empty coordinates and preserves seed zero, and optional polling signals cannot accidentally remove the default timeout. No visual redesign.

## Operational limits and deliberately deferred work

- Use **one Uvicorn worker**. Stores and admission locks are process-local. Restarting loses instances, jobs, progress, winners, and comparison results. Multiple workers cannot share run identities, cancellation, or quotas. No database, durable queue, automatic retention eviction, or restart recovery was introduced. At a retention limit, restart the local server after saving needed output; this clears all state.
- Cancellation remains cooperative at engine boundaries. An in-flight provider call or evaluation finishes/times out before cancellation becomes terminal. This is not immediate termination, and there is no whole-job wall-clock deadline or durable shutdown recovery. Existing subprocess timeout/kill/reap and missing-limit fail-closed tests remain part of regression verification.
- The Phase 3 interpreter is restricted-language execution with process/resource limits, not a general-purpose secure Python sandbox or OS permission boundary. POSIX resource-limit behavior was not verified on this Windows host. No security certification is claimed.
- Road/LLM failures were simulated offline; actual provider availability, account configuration, and road data quality remain unverified. The local smoke uses Vite module transformation, API proxying, and Uvicorn requests, not browser interaction or external map tiles/fonts. A production frontend bundle and public deployment were not verified.
- The on-disk road cache has no expiry or automatic size cleanup. Endpoint-aware keys prevent cross-provider reuse; freshness after a provider updates its road data remains a limitation. Client cleanup exceptions are logged without replacing terminal results; a failed underlying close operation cannot be guaranteed to have released provider resources.
- The frontend supports the selected instance and one displayed run. Comparisons retain the latest result per method for an instance, not a history of every applied winner. No database/history redesign was introduced.

## Exact verification commands

Final results: **429 passed, 0 failed, 1 deliberately deselected** in the broad offline run (408.59 seconds). Its JUnit report is `runs/phase4-offline.xml`. This includes Phase 1 (144), Phase 2 (73), Phase 3 (91), and Phase 4 (32) regression groups; these group counts are subsets, not additional tests. The focused Phase 4 command separately passed 32 tests. Frontend checks: 11 passed; local Vite/Uvicorn smoke: 9 passed; AST parsing: 88 passed; TypeScript: exit 0.

The first completed broad run had 425 passes and one failure: a legacy test incorrectly called a bare score dictionary valid and allowed HTTP 500. The test now supplies the documented scores envelope and requires HTTP 200 with the same route/cost as Nearest Neighbor; separate malformed-output and invalid-code checks require HTTP 400. All three focused routing checks passed before the final broad rerun. Earlier targeted road-error checks exposed two overly generic sanitized messages; useful fixed categories were restored, and the 42-test road-error/Phase 4 check passed. The only remaining test warning is Starlette's existing httpx TestClient deprecation.

Run from `D:\routeIQ` unless specified. The offline plugin blocks HTTP transports and dotenv loaders and removes inherited live LLM configuration from the test process. Live/manual modules are intentionally excluded from collection; the foundation test that opens `.env.example` is explicitly deselected.

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit/test_phase4.py -q
python -B -m pytest -o addopts= -p no:cacheprovider -p tests.offline_guard tests/unit tests/integration/test_api.py tests/test_foundation.py --deselect=tests/test_foundation.py::test_env_example_exists --junitxml=runs/phase4-offline.xml -q
node --test web/tests/phase3.cjs
python -B scripts/smoke_phase3.py
```

TypeScript, from `D:\routeIQ\web`:

```powershell
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
```

AST parsing, from repository root:

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

The broad command includes the 144-test Phase 1 suite, Phase 2 regressions/evolution/evaluation tests, and Phase 3 sandbox, timeout, road, lifecycle, winner-application, and held-out tests. Individual earlier suites can also be run with the same pytest flags and their file lists in `docs/phase3.md`.

## Files changed in Phase 4

- API: `api/main.py`, `api/models.py`, `api/storage.py`, `api/routers/evolution.py`, `api/routers/instances.py`, `api/routers/routing.py`, `api/routers/results.py`.
- Engine: `engine/llm/client.py`, `engine/llm/models.py`, `engine/llm/replay.py`, `engine/road/adapter.py`, `engine/road/models.py`, `engine/road/osrm.py`, `engine/routing/fleet.py`.
- CLI: `scripts/run_evolution.py`.
- Frontend: `web/src/components/ConfigPanel.tsx`, `web/src/services/api.ts`, new `web/src/services/inputs.ts`, `web/tests/phase3.cjs`.
- Tests: `tests/integration/test_api.py`, `tests/unit/test_llm_client.py`, new `tests/unit/test_phase4.py`, new `tests/offline_guard.py`.
- Documentation: `docs/phase4.md`.

Other dirty files predate Phase 4 and were preserved. Existing tests were strengthened to assert UUID instance identity, immediate rejection of missing live configuration, sanitized provider errors, valid score-contract execution with matching baseline routes, and rejection of malformed scores. No tests were removed or relaxed to accept failures.
