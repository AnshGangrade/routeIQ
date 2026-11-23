# Phase 3 execution and workflow boundaries

Candidate execution now uses a disposable `python -I -S -B` subprocess and JSON
messages. The child receives only the scoring source/context and a minimal
environment (Windows SYSTEMROOT only). Generated source is parsed and interpreted
as a limited language: it is never passed to Python exec/eval/compile. Full
Python, full NumPy, imports, indirect calls, decorators, private attributes and
arbitrary methods are deliberately unavailable. Unsupported syntax/capabilities
fail closed; there is no in-process or unrestricted execution fallback.

The worker installs CPU and 128 MiB memory limits before parsing input. On
Windows it requires a Job Object with one-process and kill-on-close limits; on
POSIX it requires address-space/CPU/file-size/core limits. Failure to install
limits refuses evaluation. The parent enforces a wall deadline, kills and reaps
timed-out workers. The interpreter additionally bounds operations, integer size
and collection allocations. No credentials or live services are needed for tests.

This is a constrained scoring-language runner, **not a general-purpose secure
Python sandbox**. The process still runs under the user's OS identity. Filesystem
and network capabilities are absent from the language; they are not isolated by
an AppContainer, container, seccomp policy or separate OS account. A security
review of the trusted interpreter is still needed before hostile/public use.
Arbitrary Python support and OS permission isolation are deliberately deferred.
Windows limits are tested locally; the POSIX branch needs CI on a POSIX host.

Supported operations include scalar arithmetic, comparisons, if/for/while,
collections and comprehensions, matrix indexing, selected built-ins and scalar
numerical helpers listed in the generation prompt. Matrix objects are copies;
even making a copy writable cannot change the trusted route cost.

Evolution reports preparation, current generation, completed candidate count,
completed generations, held-out evaluation and terminal status. Cancellation is
cooperative at candidate boundaries and before/after held-out evaluation; it does
not interrupt an in-flight LLM request or an entire candidate mid-evaluation.
The UI says cancellation is pending until the backend acknowledges a terminal
state. Polling retries visible errors, checks run identity and discards late
responses after cleanup. Jobs remain in-process/in-memory; restart recovery,
multi-worker shared state, authentication and job quotas are not added here.

Applying a winner sends its run ID and the selected instance ID to routing. The
server requires a completed run and recomputes fleet routes using its stored
winner. Comparisons use measured routes on that same instance. Training distance
and held-out single-driver synthetic metrics remain separately labelled. Failed
held-out comparisons are not published as improvements. The legacy
`validation_fitness` now contains held-out mean distance, `training_fitness` is
explicit, and structured `test_evaluation` carries the complete comparisons.

Synthetic distances use map units; OSRM distances use metres/kilometres. Missing
road geometry is disclosed as a preview while route distance continues to use
the OSRM matrix. Road mode accepts 5–99 stops plus a depot; malformed coordinates
and invalid matrices are rejected without a Euclidean fallback.

Offline checks:

```powershell
python -B -m pytest -o addopts= -p no:cacheprovider tests/unit/test_phase3.py tests/unit/test_sandbox.py tests/unit/test_executor_timeout.py tests/unit/test_road_routing.py tests/unit/test_road_error_handling.py -q
python -B -m pytest -o addopts= -p no:cacheprovider tests/unit/test_phase2_regressions.py tests/unit/test_evolution.py tests/unit/test_evaluation.py tests/integration/test_api.py::test_get_best_heuristic -q
python -B -m pytest -o addopts= -p no:cacheprovider tests/unit/test_baselines.py tests/unit/test_instances.py tests/unit/test_routing.py tests/unit/test_heuristics.py -q
node --test web/tests/phase3.cjs
python -B scripts/smoke_phase3.py
cd web
.\node_modules\.bin\tsc.cmd --noEmit --incremental false
```

The local serving smoke starts and shuts down Uvicorn and Vite on loopback,
disables Vite environment-file loading, blocks Python environment-file/external
HTTP access, and exercises only mock evolution and synthetic routes. It verifies
HTML/module serving, API proxying, baselines, held-out metrics, winner application
and comparison. It is not a visual browser walkthrough; external fonts and map
tiles are deliberately not fetched. The smoke exposed Windows CP1252 logging
failures from decorative checkmark/cross characters in evolution terminal logs;
those log messages now use ASCII, covered by success/failure regression tests.

## Verification after resuming (2026-10-25)

- Focused Phase 3 Python suite: 91 passed, 0 failed.
- Phase 2 suite: 73 passed, 0 failed.
- Phase 1 suite: 144 passed, 0 failed.
- Offline frontend suite: 9 passed, 0 failed.
- Local Vite/Uvicorn HTTP serving smoke: 9 passed, 0 failed.
- AST parsing: 86 project Python files passed.
- Frontend TypeScript no-emit check passed.

The resumed verification fixed two production defects: CP1252-incompatible
decorative terminal logs, and the UI's independent tie-breaking displaying a
different candidate from the server winner. Both have regression coverage.
Initial Node worker spawning was blocked by the tool sandbox (EPERM); the
approved offline rerun passed. Python suites still report the existing
Starlette/httpx TestClient deprecation warning. Tests were not weakened.

AST command from the repository root:

```powershell
@'
import ast
from pathlib import Path
excluded = {'.git', 'venv', '.venv', 'env', 'ENV', 'node_modules', '__pycache__', 'dist', 'build'}
files = sorted(p for p in Path('.').rglob('*.py') if not any(part in excluded for part in p.parts))
for path in files:
    ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
print(f'AST: {len(files)} passed, 0 failed')
'@ | python -B -
```
