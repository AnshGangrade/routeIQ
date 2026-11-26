> Current contract (2026-11-26): the active product is the integrated planning
> workspace and canonical FleetProblem with trusted construction/VND/ILS, declarative
> strategy evolution and bounded native Ollama feedback (`qwen3:1.7b`). Historical
> executable-code guidance below applies only to legacy APIs. Preserve research
> records, independent validation, baseline definitions and split protection.
> README.md and docs/product-quality-pass.md describe the current workflow.

# RouteIQ Safety Guidelines

## Critical: Generated Code is Untrusted

LLM-generated heuristics are **untrusted code** that must be executed in a restricted environment.

## Multi-Layer Defense (All Required)

### 1. Extraction & Parsing
- Extract only code blocks from LLM response
- Reject responses with multiple functions or top-level statements
- Validate function name and signature match contract

### 2. Static AST Validation
- Parse without executing
- Whitelist allowed syntax: arithmetic, comparisons, loops, list/array operations
- **Reject**: `import`, `global`, `nonlocal`, `exec`, `eval`, `open`, `compile`, underscore-prefixed names
- **Reject**: calls to `getattr`, `setattr`, `globals`, `locals`, `__import__`
- Check length limits

### 3. Restricted Namespace
- Function runs with minimal built-ins: `abs`, `min`, `max`, `sum`, `len`, `range`, `enumerate`, `zip`, `sorted`, `float`, `int`, `round`
- Provide `np` (NumPy) but nothing else
- No access to filesystem, network, or system functions

### 4. Process Isolation
- **Run in separate child process** (never in main process)
- Apply wall-clock timeout (e.g., 5 seconds per evaluation)
- Limit output size
- Use temporary working directory
- **Critical**: Child process must NOT receive .env secrets or API keys

### 5. Smoke Test
- Run on tiny instance first
- Verify output is correct length, all finite numbers (no NaN, no infinity)

### 6. Trusted Route Building
- Heuristic only scores candidates, doesn't build routes
- Harness picks next stop and validates
- Candidate cannot corrupt route or fake costs

### 7. Logging
- Preserve bounded proposal evidence without logging secrets or private customer data
- Log validation verdicts and rejection reasons
- Track validity rate as a metric

## Honest Limitations

Python-level sandboxing is **defense in depth, not a security boundary**. For academic demo purposes, process isolation + timeout + no secrets is reasonable. Do NOT:
- Run on public servers
- Process untrusted user input beyond the LLM
- Claim this is production-ready
- Run without timeouts

## Required Safety Tests (Step 4)

Must include test cases for:
- Code attempting imports
- Code trying to read files
- Code with infinite loops
- Code allocating large memory
- Code returning wrong types (NaN, wrong length)
- Code with wrong function name
- Code attempting attribute tricks to escape

All must be safely rejected without crashing the test process.

## API Key Security

- **Never** commit .env to Git
- **Never** paste API keys in Kiro chat
- **Never** pass API keys to child processes running generated code
- **Never** log API keys
- Runtime LLM API key stays in .env and is read only by the LLM client module
